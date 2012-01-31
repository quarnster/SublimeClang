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
import traceback
import Queue
from common import get_setting, get_cpu_count, Worker


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


class AnalyzerOutputView:
    def __init__(self):
        self.view = None
        self.queue = Queue.Queue()

    def do_clear(self, data=None):
        self.view = sublime.active_window().get_output_panel("clang_static_analyzer")
        self.view.settings().set("result_file_regex", "^(.+):([0-9]+):([0-9]+)")

    def do_show(self, data=None):
        sublime.active_window().run_command("show_panel", {"panel": "output.clang_static_analyzer"})

    def do_add_line(self, line):
        self.view.set_read_only(False)
        e = self.view.begin_edit()
        self.view.insert(e, self.view.size(), line)
        self.view.end_edit(e)
        self.view.set_read_only(True)

    def add_task(self, task, data=None):
        self.queue.put((task, data))
        sublime.set_timeout(self.run_tasks, 0)

    def clear(self):
        self.add_task(self.do_clear)

    def show(self):
        self.add_task(self.do_show)

    def add_line(self, line):
        self.add_task(self.do_add_line, line)

    def run_tasks(self):
        try:
            while True:
                task, data = self.queue.get_nowait()
                task(data)
                self.queue.task_done()
        except Queue.Empty:
            pass
        except:
            traceback.print_exc()


output_view = AnalyzerOutputView()


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
        if get_setting("analyzer_status_messages", True):
            super(Analyzer, self).display_status()

    def do_analyze_file(self, filename):
        self.set_status("Analyzing %s" % filename)

        cmdline = list(self.cmdline)
        cmdline.append(filename)

        p = subprocess.Popen(cmdline, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()

        res = parse(stdout)
        if res != None:
            for diag in res["diagnostics"]:
                loc = diag["location"]
                desc = diag["description"]
                desc = desc.replace("&apos;", "'")
                output_view.add_line("%s:%d:%d - %s\n" % (res["files"][loc["file"]], loc["line"], loc["col"], desc))
            if len(res["diagnostics"]) > 0:
                output_view.show()
        self.set_status("Analyzing %s done" % filename)

    def do_analyze_project(self, folders):
        for dir in folders:
            for dirpath, dirnames, filenames in os.walk(dir):
                for file in filenames:
                    if "." in file:
                        extension = file[file.rfind(".") + 1:]
                        if extension in self.extensions:
                            self.tasks.put((self.do_analyze_file, "%s/%s" % (dirpath, file)))
        if get_cpu_count() > 1:
            while not self.tasks.empty():
                time.sleep(0.25)
        self.tasks.put((self.set_status, "Project analyzed"))


analyzer = Analyzer()


class ClangAnalyzeFile(sublime_plugin.TextCommand):
    def run(self, edit):
        output_view.clear()
        fn = self.view.file_name()
        analyzer.analyze_file(fn)


class ClangAnalyzeProject(sublime_plugin.TextCommand):
    def run(self, edit):
        output_view.clear()
        analyzer.analyze_project(self.view.window().folders())
