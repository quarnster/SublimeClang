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
try:
    import sublime
    import ctypes
except:
    sublime.error_message("""\
Unfortunately ctypes can't be imported, so SublimeClang will not work.

There is a work around for this to get it to work, \
please see http://www.github.com/quarnster/SublimeClang for more details. """)

from clang import cindex
import sublime_plugin
from sublime import Region
import sublime
import os
import re
import threading
import time
import Queue
from errormarkers import clear_error_marks, add_error_mark, show_error_marks, \
                         update_statusbar, erase_error_marks

language_regex = re.compile("(?<=source\.)[\w+#]+")


def get_language(view):
    caret = view.sel()[0].a
    language = language_regex.search(view.scope_name(caret))
    if language == None:
        return None
    return language.group(0)


def get_settings():
    return sublime.load_settings("SublimeClang.sublime-settings")


class TranslationUnitCache:
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4

    class LockedVariable:
        def __init__(self, var):
            self.var = var
            self.l = threading.Lock()

        def lock(self):
            self.l.acquire()
            return self.var

        def unlock(self):
            self.l.release()

    def getCpuCount(self):
        cpus = 1
        try:
            import multiprocessing
            cpus = multiprocessing.cpu_count()
        except:
            pass
        return cpus

    def __init__(self):
        self.translationUnits = TranslationUnitCache.LockedVariable({})
        self.parsingList = TranslationUnitCache.LockedVariable([])
        self.busyList = TranslationUnitCache.LockedVariable([])
        self.index_parse_options = 13
        self.tasks = Queue.Queue()
        self.index = None
        for i in range(self.getCpuCount()):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

    def get_status(self, filename):
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        a = filename in tu
        b = filename in pl
        self.translationUnits.unlock()
        self.parsingList.unlock()
        if a and b:
            return TranslationUnitCache.STATUS_REPARSING
        elif a:
            return TranslationUnitCache.STATUS_READY
        elif b:
            return TranslationUnitCache.STATUS_PARSING
        else:
            return TranslationUnitCache.STATUS_NOT_IN_CACHE

    def add_busy(self, filename, task, data):
        bl = self.busyList.lock()
        test = filename in bl

        if test:
            self.busyList.unlock()
            # Another thread is already doing something with
            # this file, so try again later
            if self.tasks.empty():
                try:
                    time.sleep(1)
                except:
                    pass
            self.tasks.put((task, data))
            return True
        else:
            bl.append(filename)
            self.busyList.unlock()
        return False

    def remove_busy(self, filename):
        bl = self.busyList.lock()
        try:
            bl.remove(filename)
        finally:
            self.busyList.unlock()

    def task_parse(self, data):
        filename, opts, on_done = data
        if self.add_busy(filename, self.task_parse, data):
            return
        try:
            self.get_translation_unit(filename, opts)
        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.remove_busy(filename)
        sublime.set_timeout(on_done, 0)

    def task_reparse(self, data):
        filename, opts, unsaved_files, on_done = data
        if self.add_busy(filename, self.task_reparse, data):
            return
        try:
            tu = self.get_translation_unit(filename, opts, unsaved_files)
            if tu != None:
                tu.lock()
                try:
                    tu.var.reparse(unsaved_files)
                finally:
                    tu.unlock()
        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.remove_busy(filename)
        sublime.set_timeout(on_done, 0)

    def task_clear(self, data):
        tus = self.translationUnits.lock()
        try:
            tus.clear()
        finally:
            self.translationUnits.unlock()

    def task_remove(self, data):
        if self.add_busy(data, self.task_remove, data):
            return
        try:
            tus = self.translationUnits.lock()
            try:
                if data in tus:
                    del tus[data]
            finally:
                self.translationUnits.unlock()
        finally:
            self.remove_busy(data)

    def worker(self):
        try:
            # Just so we give time for the editor itself to start
            # up before we start doing work
            time.sleep(5)
        except:
            pass
        while True:
            task, data = self.tasks.get()
            try:
                task(data)
            except:
                import traceback
                traceback.print_exc()
            finally:
                self.tasks.task_done()

    def reparse(self, view, filename, unsaved_files=[], on_done=None):
        ret = False
        pl = self.parsingList.lock()
        if filename not in pl:
            ret = True
            pl.append(filename)
            self.tasks.put((
                self.task_reparse,
                (filename, self.get_opts(view), unsaved_files, on_done)))
        self.parsingList.unlock()
        return ret

    def add(self, view, filename, on_done):
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        if filename not in tu and filename not in pl:
            pl.append(filename)
            self.tasks.put((
                self.task_parse,
                (filename, self.get_opts(view), on_done)))
        self.translationUnits.unlock()
        self.parsingList.unlock()

    def get_opts(self, view):
        s = get_settings()
        opts = s.get("options", ["-Wall"])
        if s.get("add_language_option", True):
            language = get_language(view)
            if language == "objc":
                opts.append("-ObjC")
            elif language == "objc++":
                opts.append("-ObjC++")
            else:
                opts.append("-x")
                opts.append(language)
        self.index_parse_options = s.get("index_parse_options", 13)
        return opts

    def get_translation_unit(self, filename, opts=[], unsaved_files=[]):
        if self.index == None:
            self.index = cindex.Index.create()
        tu = None
        tus = self.translationUnits.lock()
        if filename not in tus:
            self.translationUnits.unlock()

            opts.append(filename)
            tu = self.index.parse(None, opts, unsaved_files,
                                  self.index_parse_options)
            if tu != None:
                # Apparently the options aren't used in the first parse,
                # so reparse to heat up the cache
                tu.reparse(unsaved_files)
                tus = self.translationUnits.lock()
                tus[filename] = tu = TranslationUnitCache.LockedVariable(tu)
                self.translationUnits.unlock()
        else:
            tu = tus[filename]
            self.translationUnits.unlock()
        return tu

    def remove(self, filename):
        self.tasks.put((self.task_remove, filename))

    def clear(self):
        self.tasks.put((self.task_clear, None))


def cache_warmed_up():
    sublime.status_message("Cache warmed up")


def warm_up_cache(view, filename=None):
    if filename == None:
        filename = view.file_name()
    stat = tuCache.get_status(filename)
    if stat == TranslationUnitCache.STATUS_NOT_IN_CACHE:
        tuCache.add(view, filename, cache_warmed_up)
        sublime.status_message("Warming up cache")
    return stat


def get_translation_unit(view, filename=None, blocking=False):
    if filename == None:
        filename = view.file_name()
    s = get_settings()
    if s.get("warm_up_in_separate_thread", True) and not blocking:
        stat = warm_up_cache(view, filename)
        if stat == TranslationUnitCache.STATUS_NOT_IN_CACHE:
            return None
        elif stat == TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Hold your horses, cache still warming up")
            return None
    return tuCache.get_translation_unit(filename, tuCache.get_opts(view))

tuCache = TranslationUnitCache()
navigation_stack = []


class ClangWarmupCache(sublime_plugin.TextCommand):
    def run(self, edit):
        stat = warm_up_cache(self.view)
        if stat == TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Cache is already warming up")
        elif stat != TranslationUnitCache.STATUS_NOT_IN_CACHE:
            sublime.status_message("Cache is already warmed up")


class ClangGoBackEventListener(sublime_plugin.EventListener):
    def on_close(self, view):
        s = get_settings()
        if not s.get("pop_on_close", True):
            return
        # If the view we just closed was last in the navigation_stack,
        # consider it "popped" from the stack
        fn = view.file_name()
        while True:
            if len(navigation_stack) == 0 or \
                    not navigation_stack[
                        len(navigation_stack) - 1][1].startswith(fn):
                break
            navigation_stack.pop()


class ClangGoBack(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(navigation_stack) > 0:
            self.view.window().open_file(
                navigation_stack.pop()[0], sublime.ENCODED_POSITION)


def format_cursor(cursor):
    return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line,
                         cursor.location.column)


def format_current_file(view):
    row, col = view.rowcol(view.sel()[0].a)
    return "%s:%d:%d" % (view.file_name(), row + 1, col + 1)


def dump_cursor(cursor):
    if cursor is None:
        print "None"
    else:
        print cursor.kind, cursor.displayname, cursor.spelling
        print format_cursor(cursor)


def open(view, target):
    navigation_stack.append((format_current_file(view), target))
    view.window().open_file(target, sublime.ENCODED_POSITION)


class ClangGotoImplementation(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        tu = get_translation_unit(view)
        if tu == None:
            return
        tu.lock()
        target = ""

        try:
            row, col = view.rowcol(view.sel()[0].a)
            cursor = cindex.Cursor.get(tu.var, view.file_name(),
                                       row + 1, col + 1)
            d = cursor.get_definition()
            if not d is None and cursor != d:
                target = format_cursor(d)
            elif d is None:
                if cursor.kind == cindex.CursorKind.DECL_REF_EXPR:
                    cursor = cursor.get_reference()
                if cursor.kind == cindex.CursorKind.CXX_METHOD or \
                        cursor.kind == cindex.CursorKind.FUNCTION_DECL:
                    f = cursor.location.file.name
                    if f.endswith(".h"):
                        endings = ["cpp", "c"]
                        for ending in endings:
                            f = "%s.%s" % (f[:-2], ending)
                            if os.access(f, os.R_OK):
                                tu2 = get_translation_unit(view, f, True)
                                if tu2 == None:
                                    continue
                                tu2.lock()
                                try:
                                    cursor2 = cindex.Cursor.get(
                                            tu2.var, cursor.location.file.name,
                                            cursor.location.line,
                                            cursor.location.column)
                                    if not cursor2 is None:
                                        d = cursor2.get_definition()
                                        if not d is None and cursor2 != d:
                                            target = format_cursor(d)
                                            break
                                finally:
                                    tu2.unlock()
        finally:
            tu.unlock()
        if len(target) > 0:
            open(self.view, target)
        else:
            sublime.status_message("Don't know where the implementation is!")


class ClangGotoDef(sublime_plugin.TextCommand):
    def quickpanel_on_done(self, idx):
        if idx == -1:
            return
        open(self.view, format_cursor(self.o[idx]))

    def quickpanel_format(self, cursor):
        return ["%s::%s" % (cursor.get_semantic_parent().spelling,
                            cursor.displayname), format_cursor(cursor)]

    def run(self, edit):
        view = self.view
        tu = get_translation_unit(view)
        if tu == None:
            return
        tu.lock()
        target = ""
        try:
            row, col = view.rowcol(view.sel()[0].a)
            cursor = cindex.Cursor.get(tu.var, view.file_name(),
                                       row + 1, col + 1)
            ref = cursor.get_reference()
            target = ""

            if not ref is None and cursor == ref:
                can = cursor.get_canonical_cursor()
                if not can is None and can != cursor:
                    target = format_cursor(can)
                else:
                    o = cursor.get_overridden()
                    if len(o) == 1:
                        target = format_cursor(o[0])
                    elif len(o) > 1:
                        self.o = o
                        opts = []
                        for i in range(len(o)):
                            opts.append(self.quickpanel_format(o[i]))
                        view.window().show_quick_panel(opts,
                                                       self.quickpanel_on_done)
            elif not ref is None:
                target = format_cursor(ref)
            elif cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
                f = cursor.get_included_file()
                if not f is None:
                    target = f.name
        finally:
            tu.unlock()
        if len(target) > 0:
            open(self.view, target)
        else:
            sublime.status_message("No parent to go to!")


class ClangClearCache(sublime_plugin.TextCommand):
    def run(self, edit):
        global tuCache
        tuCache.clear()
        sublime.status_message("Cache cleared!")


class ClangReparse(sublime_plugin.TextCommand):
    def reparse_done(self):
        sublime.status_message("reparse done")
        display_compilation_results(self.view)

    def run(self, edit):
        view = self.view
        unsaved_files = [(view.file_name(),
                          view.substr(Region(0, view.size())))]
        tuCache.reparse(view, view.file_name(), unsaved_files,
                        self.reparse_done)
        sublime.status_message("reparsing")


def display_compilation_results(view):
    tu = get_translation_unit(view)
    errString = ""
    show = False
    clear_error_marks()  # clear visual error marks
    erase_error_marks(view)
    if tu == None:
        return
    tu.lock()
    try:
        if len(tu.var.diagnostics):
            errString = ""
            for diag in tu.var.diagnostics:
                f = diag.location
                filename = ""
                if f.file != None:
                    filename = f.file.name

                err = "%s:%d,%d - %s - %s" % (filename, f.line, f.column,
                                              diag.severityName,
                                              diag.spelling)
                if diag.severity == cindex.Diagnostic.Fatal and \
                        "not found" in diag.spelling:
                    err = "%s\nDid you configure the include path used by clang properly?\n" \
                          "See http://github.com/quarnster/SublimeClang for more details on "\
                          "how to configure SublimeClang." % (err)
                errString = "%s%s\n" % (errString, err)
                """
                for range in diag.ranges:
                    errString = "%s%s\n" % (errString, range)
                for fix in diag.fixits:
                    errString = "%s%s\n" % (errString, fix)
                """
                add_error_mark(
                    diag.severityName, filename, f.line - 1, diag.spelling)
            show = True
    finally:
        tu.unlock()
    window = view.window()
    if not window is None:
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
    elif get_settings().get("hide_output_when_empty", False):
        view.window().run_command("hide_panel", {"panel": "output.clang"})


class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def __init__(self):
        s = get_settings()
        s.clear_on_change("options")
        s.add_on_change("options", self.load_settings)
        self.load_settings(s)
        self.recompile_timer = None
        self.complete_timer = None
        self.member_regex = re.compile("(([a-zA-Z_]+[0-9_]*)|([\)\]])+)((\.)|(->))$")
        self.not_code_regex = re.compile("(string.)|(comment.)")

    def load_settings(self, s=None):
        tuCache.clear()
        oldSettings = sublime.load_settings("clang.sublime-settings")
        if oldSettings.get("popup_delay") != None:
            sublime.error_message(
                "SublimeClang's configuration file name was changed from \
                'clang.sublime-settings' to 'SublimeClang.sublime-settings'. \
                Please move your settings over to this new file and delete \
                the old one.")
        if s == None:
            s = get_settings()
        if s.get("popupDelay") != None:
            sublime.error_message(
                "SublimeClang changed the 'popupDelay' setting to \
                'popup_delay, please edit your \
                SublimeClang.sublime-settings to match this")
        if s.get("recompileDelay") != None:
            sublime.error_message(
                "SublimeClang changed the 'recompileDelay' setting to \
                'recompile_delay, please edit your \
                SublimeClang.sublime-settings to match this")
        self.popup_delay = s.get("popup_delay", 500)
        self.dont_complete_startswith = s.get("dont_complete_startswith",
                                              ['operator', '~'])
        self.recompile_delay = s.get("recompile_delay", 1000)
        self.cache_on_load = s.get("cache_on_load", True)
        self.remove_on_close = s.get("remove_on_close", True)

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
                    insertion = "%s${%d:%s}" % (insertion, placeHolderCount,
                                                chunk.spelling)
                else:
                    insertion = "%s%s" % (insertion, chunk.spelling)
        return (True, "%s\t%s" % (representation, returnType), insertion)

    def is_supported_language(self, view):
        language = get_language(view)
        if language == None or (language != "c++" and
                                language != "c" and
                                language != "objc" and
                                language != "objc++"):
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
                kind == cindex.CursorKind.OBJC_INSTANCE_METHOD_DECL or \
                kind == cindex.CursorKind.FUNCTION_TEMPLATE

    def get_result_typedtext(self, result):
        for chunk in result.string:
            if chunk.isKindTypedText():
                return chunk.spelling.lower()

    def search_results(self, prefix, results, start, findStart):
        l = len(results)
        end = l - 1
        prefix = prefix.lower()
        while start <= end:
            mid = (start + end) / 2
            res1 = self.get_result_typedtext(results[mid])
            cmp1 = res1.startswith(prefix)

            cmp2 = False
            if mid + 1 < l:
                res2 = self.get_result_typedtext(results[mid + 1])
                cmp2 = res2.startswith(prefix)

            if findStart:
                if cmp2 and not cmp1:
                    # found the start position
                    return mid + 1
                elif cmp1 and mid == 0:
                    # the list starts with the item we're searching for
                    return mid
                elif res1 < prefix:
                    start = mid + 1
                else:
                    end = mid - 1
            else:
                if cmp1 and not cmp2:
                    #found the end position
                    return mid
                elif res1.startswith(prefix) or res1 < prefix:
                    start = mid + 1
                else:
                    end = mid - 1
        return -1

    def find_prefix_range(self, prefix, results):
        if len(prefix) == 0:
            return (0, len(results) - 1)
        start = self.search_results(prefix, results, 0, True)
        end = -1
        if start != -1:
            end = self.search_results(prefix, results, 0, False)
        return (start, end)

    def on_query_completions(self, view, prefix, locations):
        if not self.is_supported_language(view):
            return []

        tu = get_translation_unit(view)
        if tu == None:
            return []
        # Getting strange results form clang if I don't remove prefix
        row, col = view.rowcol(locations[0] - len(prefix))
        unsaved_files = []
        if view.is_dirty():
            unsaved_files.append((view.file_name(),
                                  view.substr(Region(0, view.size()))))

        tu.lock()
        res = None
        try:
            res = tu.var.codeComplete(view.file_name(), row + 1, col + 1,
                                      unsaved_files, 3)
        finally:
            tu.unlock()
        ret = []
        if res != None:
            res.sort()
            #for diag in res.diagnostics:
            #    print diag
            #lastRes = res.results[len(res.results)-1].string
            #if "CurrentParameter" in str(lastRes):
            #    for chunk in lastRes:
            #        if chunk.isKindCurrentParameter():
            #            return [(chunk.spelling, "${1:%s}" % chunk.spelling)]
            #    return []
            onlyMembers = self.is_member_completion(view,
                                                    locations[0] - len(prefix))
            s, e = self.find_prefix_range(prefix, res.results)
            if not (s == -1 or e == -1):
                for idx in range(s, e + 1):
                    compRes = res.results[idx]
                    if compRes.string.isAvailabilityNotAccessible() or (
                             onlyMembers and
                             not self.is_member_kind(compRes.kind)):
                        continue
                    add, representation, insertion = self.parse_res(
                                    compRes, prefix)
                    if add:
                        #print compRes.kind, compRes.string
                        ret.append((representation, insertion))
        return sorted(ret)

    def restart_complete_timer(self, view):
        if self.complete_timer != None:
            self.complete_timer.cancel()
            self.complete_timer = None
        caret = view.sel()[0].a
        if self.not_code_regex.search(view.scope_name(caret)) == None:
            line = view.substr(Region(view.word(caret).a, caret))
            if (self.is_member_completion(view, caret) or line.endswith("::")):
                stat = warm_up_cache(view)
                if not (stat == TranslationUnitCache.STATUS_NOT_IN_CACHE or
                        stat == TranslationUnitCache.STATUS_PARSING):
                    self.view = view
                    self.complete_timer = threading.Timer(
                            self.popup_delay / 1000.0,
                            sublime.set_timeout,
                            [self.complete, 0])
                    self.complete_timer.start()

    def complete(self):
        self.view.window().run_command("auto_complete")

    def reparse_done(self):
        display_compilation_results(self.view)

    def restart_recompile_timer(self, timeout):
        if self.recompile_timer != None:
            self.recompile_timer.cancel()
        self.recompile_timer = threading.Timer(timeout, sublime.set_timeout,
                                               [self.recompile, 0])
        self.recompile_timer.start()

    def recompile(self):
        view = self.view
        unsaved_files = [(view.file_name(),
                          view.substr(Region(0, view.size())))]
        if not tuCache.reparse(view, view.file_name(), unsaved_files,
                        self.reparse_done):
            # Already parsing so retry in a bit
            self.restart_recompile_timer(1)

    def on_modified(self, view):
        if (self.popup_delay <= 0 and self.reparse_delay <= 0) or \
                not self.is_supported_language(view):
            return

        if self.popup_delay > 0:
            self.restart_complete_timer(view)

        if self.recompile_delay > 0:
            self.view = view
            self.restart_recompile_timer(self.recompile_delay / 1000.0)

    def on_load(self, view):
        if self.cache_on_load and self.is_supported_language(view):
            warm_up_cache(view)

    def on_close(self, view):
        if self.remove_on_close and self.is_supported_language(view):
            tuCache.remove(view.file_name())

    def on_query_context(self, view, key, operator, operand, match_all):
        if key != "clang_supported_language":
            return None
        if view == None:
            view = sublime.active_window().active_view()
        return self.is_supported_language(view)
