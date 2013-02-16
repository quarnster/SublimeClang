import sublime
import sublime_plugin
from collections import defaultdict
try:
    from .internals.common import get_setting, sdecode, sencode
except:
    from internals.common import get_setting, sdecode, sencode


ERRORS = {}
WARNINGS = {}

ERROR = "error"
WARNING = "warning"
clang_view = None


class ClangNext(sublime_plugin.TextCommand):
    def run(self, edit):
        v = self.view
        fn = sencode(v.file_name())
        line, column = v.rowcol(v.sel()[0].a)
        gotoline = -1
        if fn in ERRORS:
            for errLine in ERRORS[fn]:
                if errLine > line:
                    gotoline = errLine
                    break
        if fn in WARNINGS:
            for warnLine in WARNINGS[fn]:
                if warnLine > line:
                    if gotoline == -1 or warnLine < gotoline:
                        gotoline = warnLine
                    break
        if gotoline != -1:
            v.window().open_file("%s:%d" % (fn, gotoline + 1), sublime.ENCODED_POSITION)
        else:
            sublime.status_message("No more errors or warnings!")


class ClangPrevious(sublime_plugin.TextCommand):
    def run(self, edit):
        v = self.view
        fn = sencode(v.file_name())
        line, column = v.rowcol(v.sel()[0].a)
        gotoline = -1
        if fn in ERRORS:
            for errLine in ERRORS[fn]:
                if errLine < line:
                    gotoline = errLine
        if fn in WARNINGS:
            for warnLine in WARNINGS[fn]:
                if warnLine < line:
                    if gotoline == -1 or warnLine > gotoline:
                        gotoline = warnLine
        if gotoline != -1:
            v.window().open_file("%s:%d" % (fn, gotoline + 1), sublime.ENCODED_POSITION)
        else:
            sublime.status_message("No more errors or warnings!")


class ClangErrorPanelFlush(sublime_plugin.TextCommand):
    def run(self, edit, data):
        self.view.erase(edit, sublime.Region(0, self.view.size()))
        self.view.insert(edit, 0, data)

class ClangErrorPanel(object):
    def __init__(self):
        self.view = None
        self.data = ""

    def set_data(self, data):
        self.data = sdecode(data)
        if get_setting("update_output_panel", True) and self.is_visible():
            self.flush()

    def get_view(self):
        return self.view

    def is_visible(self, window=None):
        ret = self.view != None and self.view.window() != None
        if ret and window:
            ret = self.view.window().id() == window.id()
        return ret

    def set_view(self, view):
        self.view = view

    def flush(self):
        self.view.set_read_only(False)
        self.view.set_scratch(True)
        self.view.run_command("clang_error_panel_flush", {"data": self.data})
        self.view.set_read_only(True)

    def open(self, window=None):
        if window == None:
            window = sublime.active_window()
        if not self.is_visible(window):
            self.view = window.get_output_panel("clang")
            self.view.settings().set("result_file_regex", "^(.+):([0-9]+),([0-9]+)")
            if get_setting("output_panel_use_syntax_file", False):
                fileName = get_setting("output_panel_syntax_file", None)
                if fileName is not None:
                    self.view.set_syntax_file(fileName)
        self.flush()

        window.run_command("show_panel", {"panel": "output.clang"})

    def close(self):
        sublime.active_window().run_command("hide_panel", {"panel": "output.clang"})

    def highlight_panel_row(self):
        if self.view is None:
            return
        view = sublime.active_window().active_view()
        row, col = view.rowcol(view.sel()[0].a)
        str = "%s:%d" % (view.file_name(), (row + 1))
        r = self.view.find(str.replace('\\','\\\\'), 0)
        panel_marker = get_setting("marker_output_panel_scope", "invalid")
        if r == None:
            self.view.erase_regions('highlightText')
        else:
            regions = [self.view.full_line(r)]
            self.view.add_regions('highlightText', regions, panel_marker, 'dot', sublime.DRAW_OUTLINED)


clang_error_panel = ClangErrorPanel()


def clear_error_marks():
    global ERRORS, WARNINGS

    listdict = lambda: defaultdict(list)
    ERRORS = defaultdict(listdict)
    WARNINGS = defaultdict(listdict)


def add_error_mark(severity, filename, line, message):
    if severity.lower() == ERROR:
        ERRORS[filename][line].append(message)
    else:
        WARNINGS[filename][line].append(message)


def show_error_marks(view):
    '''Adds error marks to view.'''
    erase_error_marks(view)
    if not get_setting("show_visual_error_marks", True):
        return
    fill_outlines = False
    gutter_mark = 'dot'
    outlines = {'warning': [], 'illegal': []}
    fn = sencode(view.file_name())
    markers = {'warning':  get_setting("marker_warning_scope", "comment"),
                'illegal': get_setting("marker_error_scope", "invalid")
                }

    for line in ERRORS[fn].keys():
        outlines['illegal'].append(view.full_line(view.text_point(line, 0)))
    for line in WARNINGS[fn].keys():
        outlines['warning'].append(view.full_line(view.text_point(line, 0)))

    for lint_type in outlines:
        if outlines[lint_type]:
            args = [
                'sublimeclang-outlines-{0}'.format(lint_type),
                outlines[lint_type],
                markers[lint_type],
                gutter_mark
            ]
            if not fill_outlines:
                args.append(sublime.DRAW_OUTLINED)
            view.add_regions(*args)


def erase_error_marks(view):
    '''erase all error marks from view'''
    view.erase_regions('sublimeclang-outlines-illegal')
    view.erase_regions('sublimeclang-outlines-warning')


def last_selected_lineno(view):
    return view.rowcol(view.sel()[0].end())[0]


def update_statusbar(view):
    fn = view.file_name()
    if fn is not None:
        fn = sencode(fn)
    lineno = last_selected_lineno(view)

    if fn in ERRORS and lineno in ERRORS[fn]:
        view.set_status('SublimeClang_line', "Error: %s" % '; '.join(ERRORS[fn][lineno]))
    elif fn in WARNINGS and lineno in WARNINGS[fn]:
        view.set_status('SublimeClang_line', "Warning: %s" % '; '.join(WARNINGS[fn][lineno]))
    else:
        view.erase_status('SublimeClang_line')


class SublimeClangStatusbarUpdater(sublime_plugin.EventListener):
    ''' This EventListener will show the error messages for the current
    line in the statusbar when the current line changes.
    '''

    def __init__(self):
        super(SublimeClangStatusbarUpdater, self).__init__()
        self.lastSelectedLineNo = -1

    def is_enabled(self):
        return True

    def on_selection_modified(self, view):
        if view.is_scratch():
            return

        # We only display errors in the status bar for the last line in the current selection.
        # If that line number has not changed, there is no point in updating the status bar.
        lastSelectedLineNo = last_selected_lineno(view)

        if lastSelectedLineNo != self.lastSelectedLineNo:
            self.lastSelectedLineNo = lastSelectedLineNo
            update_statusbar(view)
            clang_error_panel.highlight_panel_row()

    def has_errors(self, view):
        fn = view.file_name()
        if fn is None:
            return False
        return sencode(fn) in ERRORS or fn in WARNINGS

    def show_errors(self, view):
        if self.has_errors(view) and not get_setting("error_marks_on_panel_only", False, view):
            show_error_marks(view)

    def on_activated(self, view):
        self.show_errors(view)

    def on_load(self, view):
        self.show_errors(view)
