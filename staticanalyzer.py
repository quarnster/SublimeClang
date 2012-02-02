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
import threading
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
        self.view.settings().set("result_file_regex", "^[ -]*(.+):([0-9]+):([0-9]+)")

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

    def get_view(self):
        return self.view


output_view = AnalyzerOutputView()


class Diagnostic:
    def __init__(self, data, files, line):
        self.data = data
        self.files = files
        self.lines = 0
        self.line = line

    def format_location(self, loc):
        return "%s:%d:%d" % (self.files[loc["file"]], loc["line"], loc["col"])

    def format_desc(self, desc):
        return desc.replace("&apos;", "'")

    def format(self):
        desc = self.data["description"]
        desc = self.format_desc(desc)

        output = "%s - %s\n" % (self.format_location(self.data["location"]), desc)
        eventCount = 0
        for path in self.data["path"]:
            if path["kind"] == "event":
                eventCount += 1

        if eventCount > 1:
            for path in self.data["path"]:
                if path["kind"] == "event":
                    output += "    - %s - %s\n" % (self.format_location(path["location"]), self.format_desc(path["extended_message"]))
        self.lines = output.count("\n")
        return output

    def get_ranges(self, row):
        if row == self.line:
            ret = []
            for path in self.data["path"]:
                if path["kind"] == "event":
                    for range in path["ranges"]:
                        ret.append(range)
            return ret
        else:
            i = self.line
            for path in self.data["path"]:
                if path["kind"] == "event":
                    i += 1
                if i == row:
                    return path["ranges"]
        return []


class Analyzer(Worker):
    def __init__(self):
        self.lock = threading.Lock()
        self.diags = []
        self.line = 0
        super(Analyzer, self).__init__()

    def clear(self):
        sublime.active_window().active_view().erase_regions("clang.analyzer")
        output_view.clear()
        self.lock.acquire()
        self.line = 0
        self.diags = []
        self.lock.release()

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

        p = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()

        res = parse(stdout)
        if res != None:
            self.lock.acquire()
            for diag in res["diagnostics"]:
                d = Diagnostic(diag, res["files"], self.line)
                self.diags.append(d)
                output_view.add_line(d.format())
                self.line += d.lines
            self.lock.release()

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

    def get_diagnostic_at_line(self, line):
        for i in range(len(self.diags)):
            if self.diags[i].line == line:
                return self.diags[i]
            elif self.diags[i].line > line:
                return self.diags[i - 1]
        if len(self.diags) > 0:
            return self.diags[len(self.diags)-1]


analyzer = Analyzer()


class ClangAnalyzeFile(sublime_plugin.TextCommand):
    def run(self, edit):
        analyzer.clear()
        fn = self.view.file_name()
        analyzer.analyze_file(fn)


class ClangAnalyzeProject(sublime_plugin.TextCommand):
    def run(self, edit):
        analyzer.clear()
        analyzer.analyze_project(self.view.window().folders())


class ClangAnalyzeEventListener(sublime_plugin.EventListener):
    def __init__(self):
        self.ranges = {}

    def prepare_ranges(self, ranges, lut):
        self.ranges = {}
        for range in ranges:
            f = lut[range[0]["file"]]
            if f not in self.ranges:
                self.ranges[f] = []
            self.ranges[f].append([(range[0]["line"], range[0]["col"]), (range[1]["line"], range[1]["col"])])

    def update_regions(self, f, v):
        regions = []
        for range in self.ranges[f]:
            start = range[0]
            end = range[1]
            regions.append(sublime.Region(v.text_point(start[0]-1, start[1]-1), v.text_point(end[0]-1, end[1])))
        v.show(regions[0])
        v.add_regions("clang.analyzer", regions, get_setting("marker_analyzer_scope", "invalid"), "", sublime.DRAW_OUTLINED)

    def on_load(self, view):
        f = view.file_name()
        if f in self.ranges:
            self.update_regions(f, view)

    def on_selection_modified(self, view):
        v = output_view.get_view()
        if not v is None and view.id() == v.id():
            region = v.full_line(v.sel()[0].a)
            v.add_regions("clang.analyze.selection", [region], get_setting("marker_analyzer_output_panel_scope", "invalid"), "", sublime.DRAW_OUTLINED)
            row, col = v.rowcol(v.sel()[0].a)
            diag = analyzer.get_diagnostic_at_line(row)
            self.prepare_ranges(diag.get_ranges(row), diag.files)
            for f in self.ranges:
                v = sublime.active_window().open_file(f, sublime.TRANSIENT)
                if not v.is_loading():
                    self.update_regions(f, v)
