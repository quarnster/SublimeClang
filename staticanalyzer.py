"""
Copyright (c) 2011-2012 Fredrik Ehnbom

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

   1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.

   2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.

   3. This notice may not be removed or altered from any source
   distribution.
"""

import os
import subprocess
import sublime
import sublime_plugin
import time
from common import get_setting, Worker


def parse(l):
    start = 0
    i = 0
    contents = ""
    key = ""
    pos = -1
    containerList = []
    keyList = []
    result = None
    indent = ""

    while i < len(l):
        c = l[i]
        if c == "<":
            contents = l[start:i]
            start = i + 1
        elif c == ">":
            tag = l[start:i]
            if tag[0] != "/":
                indent += "\t"
            if tag[0] == "/":
                indent = indent[:-1]

            start = i + 1
            if tag == "/integer":
                contents = int(contents)
                if len(key) > 0:
                    containerList[pos][key] = contents
                else:
                    containerList[pos].append(contents)
                key = ""
            elif tag == "/string":
                if len(key) > 0:
                    containerList[pos][key] = contents
                else:
                    containerList[pos].append(contents)
                key = ""
            elif tag == "/key":
                key = contents
            elif tag == "dict":
                containerList.append({})
                keyList.append(key)
                key = ""
                pos += 1
            elif tag == "array":
                containerList.append([])
                keyList.append(key)
                key = ""
                pos += 1
            elif tag == "/array" or tag == "/dict":
                pos -= 1
                cont = containerList.pop()
                cur = None if pos == -1 else containerList[pos]
                key = keyList.pop()

                if len(containerList) == 0:
                    result = cont
                else:
                    if len(key) > 0:
                        cur[key] = cont
                        key = ""
                    else:
                        cur.append(cont)
        i += 1
    return result


class Analyzer(Worker):

    def update_settings(self):
        cmdline = get_setting("analyzer_commandline", ["clang", "--analyze", "-o", "-"])
        opts = get_setting("options")
        for setting in opts:
            cmdline.append(setting)
        self.cmdline = cmdline
        self.extensions = get_setting("analyzer_extensions")

    def analyze_file(self, filename):
        self.update_settings()
        self.tasks.put((self.do_analyze_file, filename))

    def analyze_project(self, folders):
        self.update_settings()
        self.tasks.put((self.do_analyze_project, folders))

    def display_status(self):
        sublime.status_message(self.status)

    def set_status(self, msg):
        self.status = msg
        sublime.set_timeout(self.display_status, 0)

    def do_analyze_file(self, filename):
        cmdline = self.cmdline
        cmdline.append(filename)

        p = subprocess.Popen(cmdline, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()
        self.set_status("Analyzing %s" % filename)

        res = parse(stdout)
        if res != None:
            for diag in res["diagnostics"]:
                loc = diag["location"]
                desc = diag["description"]
                desc = desc.replace("&apos;", "'")
                print "%s:%d:%d - %s" % (res["files"][loc["file"]], loc["line"], loc["col"], desc)
        self.set_status("Analyzing %s done" % filename)

    def do_analyze_project(self, folders):
        for dir in folders:
            for dirpath, dirnames, filenames in os.walk(dir):
                for file in filenames:
                    if "." in file:
                        extension = file[file.rfind(".") + 1:]
                        if extension in self.extensions:
                            self.tasks.put((self.do_analyze_file, "%s/%s" % (dirpath, file)))
        while not self.tasks.empty():
            time.sleep(0.25)
        self.tasks.put((self.set_status, "Project analyzed"))


analyzer = Analyzer()


class ClangAnalyzeFile(sublime_plugin.TextCommand):
    def run(self, edit):
        fn = self.view.file_name()
        analyzer.analyze_file(fn)


class ClangAnalyzeProject(sublime_plugin.TextCommand):
    def run(self, edit):
        analyzer.analyze_project(self.view.window().folders())
