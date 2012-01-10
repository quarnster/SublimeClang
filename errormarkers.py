import sublime
import sublime_plugin
from collections import defaultdict
from common import get_settings

ERRORS = {}
WARNINGS = {}

ERROR = "error"
WARNING = "warning"
clang_view = None


# Apparently get_output_panel clears the output view so we'll have
# to do this for now.
# See http://www.sublimetext.com/forum/viewtopic.php?f=6&t=2044
def set_clang_view(view):
    global clang_view
    clang_view = view


def highlight_panel_row():
    v = clang_view
    view = sublime.active_window().active_view()
    row, col = view.rowcol(view.sel()[0].a)
    str = "%s:%d" % (view.file_name(), (row + 1))
    r = v.find(str, 0)
    panel_marker = get_settings().get("marker_output_panel_scope", "invalid")
    if r == None:
        v.erase_regions('highlightText')
    else:
        regions = [v.full_line(r)]
        v.add_regions('highlightText', regions, panel_marker, 'dot', sublime.DRAW_OUTLINED)


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
    if not sublime.load_settings("SublimeClang.sublime-settings").get("show_visual_error_marks", True):
        return
    fill_outlines = False
    gutter_mark = 'dot'
    outlines = {'warning': [], 'illegal': []}
    fn = view.file_name()
    markers = {'warning':  get_settings().get("marker_warning_scope", "comment"),
                'illegal': get_settings().get("marker_error_scope", "invalid")
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
    lineno = last_selected_lineno(view)

    if fn in ERRORS and lineno in ERRORS[fn]:
        view.set_status('SublimeClang', '; '.join(ERRORS[fn][lineno]))
    elif fn in WARNINGS and lineno in WARNINGS[fn]:
        view.set_status('SublimeClang', '; '.join(WARNINGS[fn][lineno]))
    else:
        view.erase_status('SublimeClang')


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
            highlight_panel_row()

    def has_errors(self, view):
        fn = view.file_name()
        return fn in ERRORS or fn in WARNINGS

    def on_activated(self, view):
        if self.has_errors(view):
            show_error_marks(view)

    def on_load(self, view):
        if self.has_errors(view):
            show_error_marks(view)
