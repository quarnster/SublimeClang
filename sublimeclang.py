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
try:
    import sublime
    import ctypes
except:
    sublime.error_message("""\
Unfortunately ctypes can't be imported, so SublimeClang will not work.

There is a work around for this to get it to work, \
please see http://www.github.com/quarnster/SublimeClang for more details. """)
import os
import sys

try:
    import Queue
    from internals.clang import cindex
    from errormarkers import clear_error_marks, add_error_mark, show_error_marks, \
                             update_statusbar, erase_error_marks, clang_error_panel
    from internals.common import get_setting, get_settings, is_supported_language, \
                                    get_language,get_cpu_count, run_in_main_thread, \
                                    status_message, sencode, are_we_there_yet, plugin_loaded
    from internals import translationunitcache
    from internals.parsehelp import parsehelp
    plugin_loaded()
except ImportError:
    import queue as Queue
    from .internals.clang import cindex
    from .errormarkers import clear_error_marks, add_error_mark, show_error_marks, \
                             update_statusbar, erase_error_marks, clang_error_panel
    from .internals.common import get_setting, get_settings, is_supported_language, \
                                    get_language,get_cpu_count, run_in_main_thread, \
                                    status_message, sencode, are_we_there_yet, plugin_loaded
    from .internals import translationunitcache
    from .internals.parsehelp import parsehelp

import sublime_plugin
from sublime import Region
import sublime
import re
import threading
import time
import traceback

def warm_up_cache(view, filename=None):
    if filename == None:
        filename = sencode(view.file_name())
    stat = translationunitcache.tuCache.get_status(filename)
    if stat == translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
        translationunitcache.tuCache.add(view, filename)
    return stat


def get_translation_unit(view, filename=None, blocking=False):
    if filename == None:
        filename = sencode(view.file_name())
    if get_setting("warm_up_in_separate_thread", True, view) and not blocking:
        stat = warm_up_cache(view, filename)
        if stat == translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
            return None
        elif stat == translationunitcache.TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Hold your horses, cache still warming up")
            return None
    return translationunitcache.tuCache.get_translation_unit(filename, translationunitcache.tuCache.get_opts(view), translationunitcache.tuCache.get_opts_script(view))

navigation_stack = []
clang_complete_enabled = True
clang_fast_completions = True


class ClangTogglePanel(sublime_plugin.WindowCommand):
    def run(self, **args):
        show = args["show"] if "show" in args else None
        aview = sublime.active_window().active_view()
        error_marks = get_setting("error_marks_on_panel_only", False, aview)

        if show or (show == None and not clang_error_panel.is_visible(self.window)):
            clang_error_panel.open(self.window)
            if error_marks:
                show_error_marks(aview)
        else:
            clang_error_panel.close()
            if error_marks:
                erase_error_marks(aview)


class ClangToggleCompleteEnabled(sublime_plugin.TextCommand):
    def run(self, edit):
        global clang_complete_enabled
        clang_complete_enabled = not clang_complete_enabled
        sublime.status_message("Clang complete is %s" % ("On" if clang_complete_enabled else "Off"))


class ClangToggleFastCompletions(sublime_plugin.TextCommand):
    def run(self, edit):
        global clang_fast_completions
        clang_fast_completions = not clang_fast_completions
        sublime.status_message("Clang fast completions are %s" % ("On" if clang_fast_completions else "Off"))


class ClangWarmupCache(sublime_plugin.TextCommand):
    def run(self, edit):
        stat = warm_up_cache(self.view)
        if stat == translationunitcache.TranslationUnitCache.STATUS_PARSING:
            sublime.status_message("Cache is already warming up")
        elif stat != translationunitcache.TranslationUnitCache.STATUS_NOT_IN_CACHE:
            sublime.status_message("Cache is already warmed up")


class ClangGoBackEventListener(sublime_plugin.EventListener):
    def on_close(self, view):
        if not get_setting("pop_on_close", True, view):
            return
        # If the view we just closed was last in the navigation_stack,
        # consider it "popped" from the stack
        fn = view.file_name()
        if fn == None:
            return
        fn = sencode(fn)
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

    def is_enabled(self):
        return is_supported_language(sublime.active_window().active_view()) and len(navigation_stack) > 0

    def is_visible(self):
        return is_supported_language(sublime.active_window().active_view())


def format_current_file(view):
    row, col = view.rowcol(view.sel()[0].a)
    return "%s:%d:%d" % (sencode(view.file_name()), row + 1, col + 1)


def open(view, target):
    navigation_stack.append((format_current_file(view), target))
    view.window().open_file(target, sublime.ENCODED_POSITION)


class ClangGotoBase(sublime_plugin.TextCommand):

    def get_target(self, tu, data, offset, found_callback, folders):
        pass

    def found_callback(self, target):
        if target == None:
            sublime.status_message("Don't know where the %s is!" % self.goto_type)
        elif not isinstance(target, list):
            open(self.view, target)
        else:
            self.targets = target
            self.view.window().show_quick_panel(target, self.open_file)

    def open_file(self, idx):
        if idx >= 0:
            target = self.targets[idx]
            if isinstance(target, list):
                target = target[1]
            open(self.view, target)

    def run(self, edit):
        view = self.view
        tu = get_translation_unit(view)
        if tu == None:
            return

        offset = view.sel()[0].a
        data = view.substr(sublime.Region(0, view.size()))
        self.get_target(tu, data, offset, self.found_callback, self.view.window().folders())


    def is_enabled(self):
        return is_supported_language(sublime.active_window().active_view())

    def is_visible(self):
        return is_supported_language(sublime.active_window().active_view())


class ClangGotoImplementation(ClangGotoBase):
    def get_target(self, tu, data, offset, found_callback, folders):
        self.goto_type = "implementation"
        return tu.get_implementation(data, offset, found_callback, folders)


class ClangGotoDef(ClangGotoBase):
    def get_target(self, tu, data, offset, found_callback, folders):
        self.goto_type = "definition"
        return tu.get_definition(data, offset, found_callback, folders)


class ClangClearCache(sublime_plugin.TextCommand):
    def run(self, edit):
        translationunitcache.tuCache.clear()
        sublime.status_message("Cache cleared!")


class ClangReparse(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        unsaved_files = []
        if view.is_dirty():
            unsaved_files.append((sencode(view.file_name()),
                          view.substr(Region(0, view.size()))))
        translationunitcache.tuCache.reparse(view, sencode(view.file_name()), unsaved_files)


def ignore_diagnostic(path, ignoreDirs):
    normalized_path = os.path.abspath(os.path.normpath(os.path.normcase(path)))
    for d in ignoreDirs:
        if normalized_path.startswith(d):
            return True
    return False


def display_compilation_results(view):
    tu = get_translation_unit(view)
    errString = ""
    show = False
    clear_error_marks()  # clear visual error marks
    erase_error_marks(view)
    if tu == None:
        return

    if not tu.try_lock():
        return
    try:
        errorCount = 0
        warningCount = 0
        ignoreDirs = [os.path.abspath(os.path.normpath(os.path.normcase(d))) for d in get_setting("diagnostic_ignore_dirs", [], view)]
        ignore_regex_str = get_setting("diagnostic_ignore_regex", "pragma once in main file")
        if ignore_regex_str:
            ignore_regex = re.compile(ignore_regex_str)
        else:
            ignore_regex = None

        if len(tu.var.diagnostics):
            errString = ""
            for diag in tu.var.diagnostics:
                f = diag.location
                filename = ""
                if f.file != None:
                    filename = f.file.name

                if ignore_diagnostic(filename, ignoreDirs):
                    continue

                err = "%s:%d,%d - %s - %s" % (filename, f.line, f.column,
                                              diag.severityName,
                                              diag.spelling)

                if ignore_regex and ignore_regex.search(err):
                    continue

                try:
                    if len(diag.disable_option) > 0:
                        err = "%s [Disable with %s]" % (err, diag.disable_option)
                except AttributeError:
                    pass
                if diag.severity == cindex.Diagnostic.Fatal and \
                        "not found" in diag.spelling:
                    err = "%s\nDid you configure the include path used by clang properly?\n" \
                          "See http://github.com/quarnster/SublimeClang for more details on "\
                          "how to configure SublimeClang." % (err)
                errString = "%s%s\n" % (errString, err)
                if diag.severity == cindex.Diagnostic.Warning:
                    warningCount += 1
                elif diag.severity >= cindex.Diagnostic.Error:
                    errorCount += 1
                """
                for range in diag.ranges:
                    errString = "%s%s\n" % (errString, range)
                for fix in diag.fixits:
                    errString = "%s%s\n" % (errString, fix)
                """
                add_error_mark(
                    diag.severityName, filename, f.line - 1, diag.spelling)
            show = errString and get_setting("show_output_panel", True, view)
    finally:
        tu.unlock()
    if (errorCount > 0 or warningCount > 0) and get_setting("show_status", True, view):
        statusString = "Clang Status: "
        if errorCount > 0:
            statusString = "%s%d Error%s" % (statusString, errorCount, "s" if errorCount != 1 else "")
        if warningCount > 0:
            statusString = "%s%s%d Warning%s" % (statusString, ", " if errorCount > 0 else "",
                                                 warningCount, "s" if warningCount != 1 else "")
        view.set_status("SublimeClang", statusString)
    else:
        view.erase_status("SublimeClang")
    window = view.window()
    clang_error_panel.set_data(errString)
    update_statusbar(view)
    if not get_setting("error_marks_on_panel_only", False, view):
        show_error_marks(view)
    if not window is None:
        if show:
            window.run_command("clang_toggle_panel", {"show": True})
        elif get_setting("hide_output_when_empty", False, view):
            if clang_error_panel.is_visible():
                window.run_command("clang_toggle_panel", {"show": False})

member_regex = re.compile(r"(([a-zA-Z_]+[0-9_]*)|([\)\]])+)((\.)|(->))$")


def is_member_completion(view, caret):
    line = view.substr(Region(view.line(caret).a, caret))
    if member_regex.search(line) != None:
        return True
    elif get_language(view).startswith("objc"):
        return re.search(r"\[[\.\->\s\w\]]+\s+$", line) != None
    return False


class ClangComplete(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        regions = [a for a in self.view.sel()]
        self.view.sel().clear()
        for region in reversed(regions):
            pos = 0
            region.end() + len(characters)
            if region.size() > 0:
                self.view.replace(edit, region, characters)
                pos = region.begin() + len(characters)
            else:
                self.view.insert(edit, region.end(), characters)
                pos = region.end() + len(characters)

            self.view.sel().add(sublime.Region(pos, pos))
        caret = self.view.sel()[0].begin()
        line = self.view.substr(sublime.Region(self.view.word(caret-1).a, caret))
        if is_member_completion(self.view, caret) or line.endswith("::") or re.search("(^|\W)new\s+\w*$", line):
            self.view.run_command("hide_auto_complete")
            sublime.set_timeout(self.delayed_complete, 1)

    def delayed_complete(self):
        self.view.run_command("auto_complete")


class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def __init__(self):
        s = get_settings()
        s.clear_on_change("options")
        s.add_on_change("options", self.load_settings)
        are_we_there_yet(lambda: self.load_settings())
        self.recompile_timer = None
        self.not_code_regex = re.compile("(string.)|(comment.)")

    def load_settings(self):
        translationunitcache.tuCache.clear()
        self.dont_complete_startswith = get_setting("dont_complete_startswith",
                                              ['operator', '~'])
        self.recompile_delay = get_setting("recompile_delay", 1000)
        self.cache_on_load = get_setting("cache_on_load", True)
        self.remove_on_close = get_setting("remove_on_close", True)
        self.time_completions = get_setting("time_completions", False)

    def is_member_kind(self, kind):
        return  kind == cindex.CursorKind.CXX_METHOD or \
                kind == cindex.CursorKind.FIELD_DECL or \
                kind == cindex.CursorKind.OBJC_PROPERTY_DECL or \
                kind == cindex.CursorKind.OBJC_CLASS_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_INSTANCE_METHOD_DECL or \
                kind == cindex.CursorKind.OBJC_IVAR_DECL or \
                kind == cindex.CursorKind.FUNCTION_TEMPLATE or \
                kind == cindex.CursorKind.NOT_IMPLEMENTED

    def return_completions(self, comp, view):
        if get_setting("inhibit_sublime_completions", True, view):
            return (comp, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
        return comp

    def on_query_completions(self, view, prefix, locations):
        global clang_complete_enabled
        if not is_supported_language(view) or not clang_complete_enabled or \
                not view.match_selector(locations[0], '-string -comment -constant'):
            return []

        line = view.substr(sublime.Region(view.line(locations[0]).begin(), locations[0]))
        match = re.search(r"[,\s]*(\w+)\s+\w+$", line)
        if match != None:
            valid = ["new", "delete", "return", "goto", "case", "const", "static", "class", "struct", "typedef", "union"]
            if match.group(1) not in valid:
                # Probably a variable or function declaration
                # There's no point in trying to complete
                # a name that hasn't been typed yet...
                return self.return_completions([], view)

        timing = ""
        tot = 0
        start = time.time()
        tu = get_translation_unit(view)
        if tu == None:
            return self.return_completions([], view)
        ret = None
        tu.lock()
        try:
            if self.time_completions:
                curr = (time.time() - start)*1000
                tot += curr
                timing += "TU: %f" % (curr)
                start = time.time()

            cached_results = None
            if clang_fast_completions and get_setting("enable_fast_completions", True, view):
                data = view.substr(sublime.Region(0, locations[0]))
                try:
                    cached_results = tu.cache.complete(data, prefix)
                except:
                    traceback.print_exc()
            if cached_results != None:
                # print("found fast completions")
                ret = cached_results
            else:
                # print("doing slow completions")
                row, col = view.rowcol(locations[0] - len(prefix))
                unsaved_files = []
                if view.is_dirty():
                    unsaved_files.append((sencode(view.file_name()),
                                      view.substr(Region(0, view.size()))))
                ret = tu.cache.clangcomplete(sencode(view.file_name()), row+1, col+1, unsaved_files, is_member_completion(view, locations[0] - len(prefix)))
            if self.time_completions:
                curr = (time.time() - start)*1000
                tot += curr
                timing += ", Comp: %f" % (curr)
                start = time.time()

            if len(self.dont_complete_startswith) and ret:
                i = 0
                while i < len(ret):
                    disp = ret[i][0]
                    pop = False
                    for comp in self.dont_complete_startswith:
                        if disp.startswith(comp):
                            pop = True
                            break

                    if pop:
                        ret.pop(i)
                    else:
                        i += 1

            if self.time_completions:
                curr = (time.time() - start)*1000
                tot += curr
                timing += ", Filter: %f" % (curr)
                timing += ", Tot: %f ms" % (tot)
                print(timing)
                sublime.status_message(timing)
        finally:
            tu.unlock()

        if not ret is None:
            return self.return_completions(ret, view)
        return self.return_completions([], view)

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
        unsaved_files = []
        if view.is_dirty() and get_setting("reparse_use_dirty_buffer", False, view):
            unsaved_files.append((sencode(view.file_name()),
                                  view.substr(Region(0, view.size()))))
        if not translationunitcache.tuCache.reparse(view, sencode(view.file_name()), unsaved_files,
                        self.reparse_done):

            # Already parsing so retry in a bit
            self.restart_recompile_timer(1)

    def on_activated(self, view):
        if is_supported_language(view) and get_setting("reparse_on_activated", True, view):
            self.view = view
            self.restart_recompile_timer(0.1)

    def on_post_save(self, view):
        if is_supported_language(view) and get_setting("reparse_on_save", True, view):
            self.view = view
            self.restart_recompile_timer(0.1)

    def on_modified(self, view):
        if (self.recompile_delay <= 0) or not is_supported_language(view):
            return

        self.view = view
        self.restart_recompile_timer(self.recompile_delay / 1000.0)

    def on_load(self, view):
        if self.cache_on_load and is_supported_language(view):
            warm_up_cache(view)

    def on_close(self, view):
        if self.remove_on_close and is_supported_language(view):
            translationunitcache.tuCache.remove(sencode(view.file_name()))

    def on_query_context(self, view, key, operator, operand, match_all):
        if key == "clang_supported_language":
            if view == None:
                view = sublime.active_window().active_view()
            return is_supported_language(view)
        elif key == "clang_is_code":
            return self.not_code_regex.search(view.scope_name(view.sel()[0].begin())) == None
        elif key == "clang_complete_enabled":
            return clang_complete_enabled
        elif key == "clang_automatic_completion_popup":
            return get_setting("automatic_completion_popup", True, view)
        elif key == "clang_panel_visible":
            return clang_error_panel.is_visible()
