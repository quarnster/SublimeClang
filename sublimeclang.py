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
from errormarkers import clear_error_marks, add_error_mark, show_error_marks, update_statusbar, erase_error_marks

language_regex = re.compile("(?<=source\.)[\w+#]+")
translationUnits = {}
index = None

def get_language(view):
    caret = view.sel()[0].a
    language = language_regex.search(view.scope_name(caret))
    if language == None:
        return None
    return language.group(0)

def get_translation_unit(filename):
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
        if s.get("add_language_option", True):
            language = get_language(sublime.active_window().active_view())
            if language == "objc":
                opts.append("-ObjC")
            elif language == "objc++":
                opts.append("-ObjC++")
            else:
                opts.append("-x")
                opts.append(language)
        opts.append(filename)
        tu = index.parse(None, opts, [], s.get("index_parse_options", 0x1))
        if tu != None:
            translationUnits[filename] = tu
    else:
        tu = translationUnits[filename]
    return tu

navigation_stack = []

class ClangGoBackEventListener(sublime_plugin.EventListener):
    def on_close(self, view):
        # If the view we just closed was last in the navigation_stack,
        # consider it "popped" from the stack
        fn = view.file_name()
        while True:
            if len(navigation_stack) == 0 or not navigation_stack[len(navigation_stack)-1][1].startswith(fn):
                break
            navigation_stack.pop()


class ClangGoBack(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(navigation_stack) > 0:
            self.view.window().open_file(navigation_stack.pop()[0], sublime.ENCODED_POSITION)


class ClangGotoDef(sublime_plugin.TextCommand):
    def dump(self, cursor):
        if cursor is None:
            print "None"
        else:
            print cursor.kind, cursor.displayname, cursor.spelling
            print self.format_cursor(cursor)

    def format_cursor(self, cursor):
        return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line, cursor.location.column)

    def format_current_file(self):
        row, col = self.view.rowcol(self.view.sel()[0].a)
        return "%s:%d:%d" % (self.view.file_name(), row+1, col+1)

    def open(self, target):
        navigation_stack.append((self.format_current_file(), target))
        self.view.window().open_file(target, sublime.ENCODED_POSITION)

    def quickpanel_on_done(self, idx):
        if idx == -1:
            return
        self.open(self.format_cursor(self.o[idx]))

    def quickpanel_format(self, cursor):
        return ["%s::%s" % (cursor.get_semantic_parent().spelling, cursor.displayname), self.format_cursor(cursor)]

    def run(self, edit):
        view = self.view
        tu = get_translation_unit(view.file_name())
        row, col = view.rowcol(view.sel()[0].a)
        cursor = cindex.Cursor.get(tu, view.file_name(), row+1, col+1)
        ref = cursor.get_reference()
        target = ""
        d = cursor.get_definition()

        if not d is None and cursor != d:
            target = self.format_cursor(d)
        elif not ref is None and cursor == ref:
            can = cursor.get_canonical_cursor()
            if not can is None and can != cursor:
                target = self.format_cursor(can)
            else:
                o = cursor.get_overridden()
                if len(o) == 1:
                    target = self.format_cursor(o[0])
                elif len(o) > 1:
                    self.o = o
                    opts = []
                    for i in range(len(o)):
                        opts.append(self.quickpanel_format(o[i]))
                    view.window().show_quick_panel(opts, self.quickpanel_on_done)
        elif not ref is None:
            target = self.format_cursor(ref)
        elif cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
            f = cursor.get_included_file()
            if not f is None:
                target = f.name
        if len(target) > 0:
            self.open(target)
        else:
            sublime.status_message("No parent to go to!")

class ClangClearCache(sublime_plugin.TextCommand):
    def run(self, edit):
        global translationUnits
        translationUnits.clear()
        sublime.status_message("Cache cleared!")

class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def __init__(self):
        s = sublime.load_settings("clang.sublime-settings")
        s.clear_on_change("options")
        s.add_on_change("options", self.load_settings)
        self.load_settings(s)
        self.auto_complete_active = False
        self.recompile_timer = None
        self.compilation_lock = threading.Lock()
        self.member_regex = re.compile("[a-zA-Z]+[0-9_\(\)]*((\.)|(->))$")
        self.not_code_regex = re.compile("(string.)|(comment.)")

    def load_settings(self, s=None):
        global translationUnits
        translationUnits.clear()
        if s == None:
            s = sublime.load_settings("clang.sublime-settings")
        if s.get("popupDelay") != None:
            sublime.error_message("SublimeClang changed the 'popupDelay' setting to 'popup_delay, please edit your clang.sublime-settings to match this")
        if s.get("recompileDelay") != None:
            sublime.error_message("SublimeClang changed the 'recompileDelay' setting to 'recompile_delay, please edit your clang.sublime-settings to match this")
        self.popup_delay = s.get("popup_delay", 500)
        self.dont_complete_startswith = s.get("dont_complete_startswith", ['operator', '~'])
        self.recompile_delay = s.get("recompile_delay", 1000)
        self.hide_clang_output = s.get("hide_output_when_empty", False)

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


    def is_supported_language(self, view):
        language = get_language(view)
        if language == None or (language != "c++" and language != "c" and language != "objc" and language != "objc++"):
            return False
        return True

    def is_member_completion(self, view, caret):
        line = view.substr(Region(view.line(caret).a, caret))
        if self.member_regex.search(line) != None:
            return True
        elif get_language(view).startswith("objc"):
            return re.search("[ \t]*\[[\w]+ $", line) != None
        return False

    def is_member_kind(self, kind):
        return  kind == cindex.CursorKind.CXX_METHOD or \
                kind == cindex.CursorKind.FIELD_DECL or \
                kind == cindex.CursorKind.OBJC_PROPERTY_DECL or \
                kind == cindex.CursorKind.OBJC_CLASS_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_INSTANCE_METHOD_DECL

    def get_result_typedtext(self, result):
        for chunk in result.string:
            if chunk.isKindTypedText():
                return chunk.spelling.lower()

    def search_results(self, prefix, results, start, findStart):
        l = len(results)
        end = l-1
        prefix = prefix.lower()
        while start <= end:
            mid = (start+end)/2
            res1 = self.get_result_typedtext(results[mid])
            cmp1 = res1.startswith(prefix)

            cmp2 = False
            if mid+1 < l:
                res2 = self.get_result_typedtext(results[mid+1])
                cmp2 = res2.startswith(prefix)

            if findStart:
                if cmp2 and not cmp1:
                    # found the start position
                    return mid+1
                elif cmp1 and mid == 0:
                    # the list starts with the item we're searching for
                    return mid
                elif res1 < prefix:
                    start = mid+1
                else:
                    end = mid-1
            else:
                if cmp1 and not cmp2:
                    #found the end position
                    return mid
                elif res1.startswith(prefix) or res1 < prefix:
                    start = mid+1
                else:
                    end = mid-1
        return -1

    def find_prefix_range(self, prefix, results):
        if len(prefix) == 0:
            return (0, len(results)-1)
        start = self.search_results(prefix, results, 0, True)
        end = -1
        if start != -1:
            end = self.search_results(prefix, results, 0, False)
        return (start,end)

    def on_query_completions(self, view, prefix, locations):
        if not self.is_supported_language(view):
            return []

        tu = get_translation_unit(view.file_name())
        if tu == None:
            return []
        row, col = view.rowcol(locations[0] - len(prefix))  # Getting strange results form clang if I don't remove prefix
        unsaved_files = []
        if view.is_dirty():
            unsaved_files.append((view.file_name(), view.substr(Region(0, view.size()))))

        self.compilation_lock.acquire()
        try:
            res = tu.codeComplete(view.file_name(), row + 1, col + 1, unsaved_files, 3)
        finally:
            self.compilation_lock.release()
        res.sort()
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
            onlyMembers = self.is_member_completion(view, locations[0]-len(prefix))
            s,e = self.find_prefix_range(prefix, res.results)
            if not (s == -1 or e == -1):
                for idx in range(s,e+1):
                    compRes = res.results[idx]
                    if compRes.string.isAvailabilityNotAccessible() or (onlyMembers and not self.is_member_kind(compRes.kind)):
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
            self.parent.compilation_lock.acquire()
            try:
                self.tu.reparse(self.unsaved_files)
            finally:
                self.parent.compilation_lock.release()
            sublime.set_timeout(self.parent.display_compilation_results, 0)


    def display_compilation_results(self):
        view = self.view
        tu = get_translation_unit(view.file_name())
        errString = ""
        show = False
        clear_error_marks()  # clear visual error marks
        erase_error_marks(view)
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
                    diag.severityName, filename, f.line - 1, diag.spelling)  # add visual error marks
            show = True
        v = view.window().get_output_panel("clang")
        v.settings().set("result_file_regex", "^(.+):([0-9]+),([0-9]+)")
        view.window().get_output_panel("clang")
        v.set_read_only(False)
        v.set_scratch(True)
        v.set_name("sublimeclang.%s" % view.file_name())
        e = v.begin_edit()
        v.insert(e, 0, errString)
        v.end_edit(e)
        v.set_read_only(True)
        show_error_marks(view)
        update_statusbar(view)
        if show:
            view.window().run_command("show_panel", {"panel": "output.clang"})
        elif self.hide_clang_output:
            view.window().run_command("hide_panel", {"panel": "output.clang"})

    def restart_recompile_timer(self, timeout):
        if self.recompile_timer != None:
            self.recompile_timer.cancel()
        self.recompile_timer = threading.Timer(timeout, sublime.set_timeout, [self.recompile, 0])
        self.recompile_timer.start()

    def recompile(self):
        view = self.view
        unsaved_files = [(view.file_name(), view.substr(Region(0, view.size())))]
        tu = get_translation_unit(view.file_name())
        if tu == None:
            return
        if self.compilation_lock.locked():
            # Already compiling. Try again in a bit
            self.restart_recompile_timer(1)
        else:
            self.CompilationThread(self, tu, unsaved_files).start()

    def on_modified(self, view):
        if (self.popup_delay <= 0 and self.reparse_delay <= 0) or not self.is_supported_language(view):
            return

        if self.popup_delay > 0 :
            caret = view.sel()[0].a
            if self.not_code_regex.search(view.scope_name(caret)) == None:
                self.auto_complete_active = False
                line = view.substr(Region(view.word(caret).a, caret))
                if (self.is_member_completion(view, caret) or line.endswith("::")):
                    self.auto_complete_active = True
                    self.view = view
                    sublime.set_timeout(self.complete, self.popup_delay)

        if self.recompile_delay > 0:
            self.view = view
            self.restart_recompile_timer(self.recompile_delay/1000.0)

    def on_query_context(self, view, key, operator, operand, match_all):
        if key != "clang_supported_language":
            return None
        if view == None:
            view = sublime.active_window().active_view()
        return self.is_supported_language(view)
