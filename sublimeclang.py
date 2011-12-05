"""
Copyright (c) 2011 Fredrik Ehnbom

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
from clang import cindex
import sublime_plugin
from sublime import Region
import sublime
import re
import threading
from errormarkers import clear_error_marks, add_error_mark, show_error_marks

translationUnits = {}
index = None


class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def __init__(self):
        s = sublime.load_settings("clang.sublime-settings")
        s.clear_on_change("options")
        s.add_on_change("options", self.load_settings)
        self.load_settings(s)
        self.auto_complete_active = False
        self.recompileTimer = None
        self.compilationLock = threading.Lock()
        self.languageRe = re.compile("(?<=source\.)[a-zA-Z0-9+#]+")
        self.memberRe = re.compile("[a-zA-Z]+[0-9_\(\)]*((\.)|(->))$")
        self.notCodeRe = re.compile("(string.)|(comment.)")

    def load_settings(self, s=None):
        global translationUnits
        translationUnits.clear()
        if s == None:
            s = sublime.load_settings("clang.sublime-settings")
        self.popupDelay = s.get("popupDelay", 500)
        self.dont_complete_startswith = s.get("dont_complete_startswith", ['operator', '~'])
        self.recompileDelay = s.get("recompileDelay", 1000)
        self.hide_clang_output = s.get("hide_output_when_empty", False)
        self.add_language_option = s.get("add_language_option", True)

    def parse_res(self, compRes, prefix):
        #print compRes.kind, compRes.string
        representation = ""
        insertion = ""
        returnType = ""
        start = False
        placeHolderCount = 0
        for chunk in compRes.string:
            if chunk.isKindTypedText():
                start = True
                if not chunk.spelling.startswith(prefix):
                    return (False, None, None)
                for test in self.dont_complete_startswith:
                    if chunk.spelling.startswith(test):
                        return (False, None, None)
            if chunk.isKindResultType():
                returnType = chunk.spelling
            else:
                representation = "%s%s" % (representation, chunk.spelling)
            if start and not chunk.isKindInformative():
                if chunk.isKindPlaceHolder():
                    placeHolderCount = placeHolderCount + 1
                    insertion = "%s${%d:%s}" % (insertion, placeHolderCount, chunk.spelling)
                else:
                    insertion = "%s%s" % (insertion, chunk.spelling)
        return (True, "%s - %s" % (representation, returnType), insertion)

    def get_translation_unit(self, filename):
        global translationUnits
        global index
        if index == None:
            index = cindex.Index.create()
        tu = None
        if filename not in translationUnits:
            s = sublime.load_settings("clang.sublime-settings")
            opts = []
            if s.has("options"):
                opts = s.get("options")
            if self.add_language_option:
                language = self.get_language(sublime.active_window().active_view())
                if language == "objc":
                    opts.append("-ObjC")
                elif language == "objc++":
                    opts.append("-ObjC++")
                else:
                    opts.append("-x")
                    opts.append(language)
            opts.append(filename)
            tu = index.parse(None, opts)
            if tu != None:
                translationUnits[filename] = tu
        else:
            tu = translationUnits[filename]
        return tu

    def get_language(self, view):
        caret = view.sel()[0].a
        language = self.languageRe.search(view.scope_name(caret))
        if language == None:
            return False
        return language.group(0)

    def is_supported_language(self, view):
        language = self.get_language(view)
        if language != "c++" and language != "c" and language != "objc" and language != "objc++":
            return False
        return True

    def is_member_completion(self, view, caret):
        line = view.substr(Region(view.line(caret).a, caret))
        if self.memberRe.search(line) != None:
            return True
        elif self.get_language(view).startswith("objc"):
            return re.search("[ \t]*\[[a-zA-Z0-9_]* $", line) != None
        return False

    def is_member_kind(self, kind):
        return  kind == cindex.CursorKind.CXX_METHOD or \
                kind == cindex.CursorKind.FIELD_DECL or \
                kind == cindex.CursorKind.OBJC_PROPERTY_DECL or \
                kind == cindex.CursorKind.OBJC_CLASS_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_INSTANCE_METHOD_DECL

    def on_query_completions(self, view, prefix, locations):
        if not self.is_supported_language(view):
            return []

        tu = self.get_translation_unit(view.file_name())
        if tu == None:
            return []
        row, col = view.rowcol(locations[0] - len(prefix))  # Getting strange results form clang if I don't remove prefix
        unsaved_files = []
        if view.is_dirty():
            unsaved_files.append((view.file_name(), str(view.substr(Region(0, view.size())))))

        self.compilationLock.acquire()
        try:
            res = tu.codeComplete(view.file_name(), row + 1, col + 1, unsaved_files, 3)
        finally:
            self.compilationLock.release()
        ret = []
        if res != None:
            #for diag in res.diagnostics:
            #    print diag
            #lastRes = res.results[len(res.results)-1].string
            #if "CurrentParameter" in str(lastRes):
            #    for chunk in lastRes:
            #        if chunk.isKindCurrentParameter():
            #            return [(chunk.spelling, "${1:%s}" % chunk.spelling)]
            #    return []
            onlyMembers = self.is_member_completion(view, locations[0])

            for compRes in res.results:
                if onlyMembers and not self.is_member_kind(compRes.kind):
                    continue
                add, representation, insertion = self.parse_res(compRes, prefix)
                if add:
                    #print compRes.kind, compRes.string
                    ret.append((representation, insertion))
        return sorted(ret)

    def complete(self):
        if self.auto_complete_active:
            self.auto_complete_active = False
            self.view.window().run_command("auto_complete")

    class CompilationThread(threading.Thread):
        def __init__(self, parent, tu, unsaved_files):
            threading.Thread.__init__(self)
            self.parent = parent
            self.tu = tu
            self.unsaved_files = unsaved_files

        def run(self):
            self.parent.compilationLock.acquire()
            try:
                self.tu.reparse(self.unsaved_files)
            finally:
                self.parent.compilationLock.release()
            sublime.set_timeout(self.parent.display_compilation_results, 0)


    def display_compilation_results(self):
        view = self.view
        tu = self.get_translation_unit(view.file_name())
        errString = ""
        show = False
        clear_error_marks()  # clear visual error marks
        if tu == None:
            return
        if len(tu.diagnostics):
            errString = ""
            for diag in tu.diagnostics:
                f = diag.location
                filename = ""
                if f.file != None:
                    filename = f.file.name

                err = "%s:%d,%d - %s - %s" % (filename, f.line, f.column, diag.severityName, diag.spelling)
                errString = "%s%s\n" % (errString, err)
                """
                for range in diag.ranges:
                    errString = "%s%s\n" % (errString, range)
                for fix in diag.fixits:
                    errString = "%s%s\n" % (errString, fix)
                """
                add_error_mark(
                    diag.severityName, filename, f.line - 1, diag.spelling)  # clear visual error marks
            show = True
        v = view.window().get_output_panel("clang")
        v.settings().set("result_file_regex", "^(...*?):([0-9]*):?([0-9]*)")
        view.window().get_output_panel("clang")
        v.set_read_only(False)
        v.set_scratch(True)
        v.set_name("sublimeclang.%s" % view.file_name())
        e = v.begin_edit()
        v.insert(e, 0, errString)
        v.end_edit(e)
        v.set_read_only(True)
        show_error_marks(view)
        if show:
            view.window().run_command("show_panel", {"panel": "output.clang"})
        elif self.hide_clang_output:
            view.window().run_command("hide_panel", {"panel": "output.clang"})

    def restartRecompileTimer(self, timeout):
        if self.recompileTimer != None:
            self.recompileTimer.cancel()
        self.recompileTimer = threading.Timer(timeout, sublime.set_timeout, [self.recompile, 0])
        self.recompileTimer.start()

    def recompile(self):
        view = self.view
        unsaved_files = [(view.file_name(), view.substr(Region(0, view.size())))]
        tu = self.get_translation_unit(view.file_name())
        if tu == None:
            return
        if self.compilationLock.locked():
            # Already compiling. Try again in a bit
            self.restartRecompileTimer(1)
        else:
            self.CompilationThread(self, tu, unsaved_files).start()

    def on_modified(self, view):
        if (self.popupDelay <= 0 and self.reparseDelay <= 0) or not self.is_supported_language(view):
            return

        if self.popupDelay > 0 :
            caret = view.sel()[0].a
            if self.notCodeRe.search(view.scope_name(caret)) == None:
                self.auto_complete_active = False
                line = view.substr(Region(view.word(caret).a, caret))
                if (self.is_member_completion(view, caret) or line.endswith("::")):
                    self.auto_complete_active = True
                    self.view = view
                    sublime.set_timeout(self.complete, self.popupDelay)

        if self.recompileDelay > 0:
            self.view = view
            self.restartRecompileTimer(self.recompileDelay/1000.0)
