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

import threading
import time
import Queue
import os
import re


try:
    import sublime
    def run_in_main_thread(func):
        sublime.set_timeout(func, 0)


    def error_message(msg):
        sublime.error_message(msg)

    language_regex = re.compile("(?<=source\.)[\w+#]+")


    def get_language(view):
        caret = view.sel()[0].a
        language = language_regex.search(view.scope_name(caret))
        if language == None:
            return None
        return language.group(0)


    def is_supported_language(view):
        if view.is_scratch() or not get_setting("enabled", True, view) or view.file_name() == None:
            return False
        language = get_language(view)
        if language == None or (language != "c++" and
                                language != "c" and
                                language != "objc" and
                                language != "objc++"):
            return False
        return True

    def status_message(msg):
        sublime.status_message(msg)

    def get_settings():
        return sublime.load_settings("SublimeClang.sublime-settings")


    def get_setting(key, default=None, view=None):
        try:
            if view == None:
                view = sublime.active_window().active_view()
            s = view.settings()
            if s.has("sublimeclang_%s" % key):
                return s.get("sublimeclang_%s" % key)
        except:
            pass
        return get_settings().get(key, default)

    def expand_path(value, window):
        if window == None:
            # Views can apparently be window less, in most instances getting
            # the active_window will be the right choice (for example when
            # previewing a file), but the one instance this is incorrect
            # is during Sublime Text 2 session restore. Apparently it's
            # possible for views to be windowless then too and since it's
            # possible that multiple windows are to be restored, the
            # "wrong" one for this view might be the active one and thus
            # ${project_path} will not be expanded correctly.
            #
            # This will have to remain a known documented issue unless
            # someone can think of something that should be done plugin
            # side to fix this.
            window = sublime.active_window()

        get_existing_files = \
            lambda m: [ path \
                for f in window.folders() \
                for path in [os.path.join(f, m.group('file'))] \
                if os.path.exists(path) \
            ]
        view = window.active_view()
        value = re.sub(r'\${project_path:(?P<file>[^}]+)}', lambda m: len(get_existing_files(m)) > 0 and get_existing_files(m)[0] or m.group('file'), value)
        value = re.sub(r'\${env:(?P<variable>[^}]+)}', lambda m: os.getenv(m.group('variable')) if os.getenv(m.group('variable')) else "%s_NOT_SET" % m.group('variable'), value)
        value = re.sub(r'\${home}', os.getenv('HOME') if os.getenv('HOME') else "HOME_NOT_SET", value)
        value = re.sub(r'\${folder:(?P<file>[^}]+)}', lambda m: os.path.dirname(m.group('file')), value)
        value = value.replace('${this_file_path}', os.path.dirname(view.file_name()) if view and view.file_name() else "FILE_NOT_ON_DISK")
        value = value.replace('\\', '/')

        return value
except:
    # Just used for unittesting

    def error_message(msg):
        print msg

    def get_setting(key, default=None, view=None):
        return default

    def get_language(view):
        return "c++"

    def run_in_main_thread(func):
        func()

    def status_message(msg):
        print msg

    def expand_path(value, window):
        return value


class LockedVariable:
    def __init__(self, var):
        self.var = var
        self.l = threading.Lock()

    def try_lock(self):
        return self.l.acquire(False)

    def lock(self):
        self.l.acquire()
        return self.var

    def unlock(self):
        self.l.release()


class Worker(object):
    def __init__(self, threadcount=-1):
        if threadcount < 1:
            threadcount = get_cpu_count()
        self.tasks = Queue.Queue()
        for i in range(threadcount):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

    def display_status(self):
        status_message(self.status)

    def set_status(self, msg):
        self.status = msg
        run_in_main_thread(self.display_status)

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


def complete_path(value, window):
    path_init, path_last = os.path.split(value)
    if path_init[:2] == "-I" and (path_last == "**" or path_last == "*"):
        starting_path = expand_path(path_init[2:], window)
        include_paths = []
        if os.path.exists(starting_path):
            if path_last == "*":
                for dirname in os.listdir(starting_path):
                    if not dirname.startswith("."):  # skip directories that begin with .
                        include_paths.append("-I" + os.path.join(starting_path, dirname))
            elif path_last == "**":
                for dirpath, dirs, files in os.walk(starting_path):
                    for dirname in list(dirs):
                        if dirname.startswith("."):  # skip directories that begin with .
                            dirs.remove(dirname)
                    if dirpath != starting_path:
                        include_paths.append("-I" + dirpath)
            else:
                include_paths.append("-I" + starting_path)
        else:
            pass  # perhaps put some error here?
        return include_paths
    else:
        return [expand_path(value, window)]


def get_path_setting(key, default=None, view=None):
    value = get_setting(key, default, view)
    opts = []
    if isinstance(value, str) or isinstance(value, unicode):
        opts.extend(complete_path(value, view.window()))
    else:
        for v in value:
            opts.extend(complete_path(v, view.window()))
    return opts


def get_cpu_count():
    cpus = 1
    try:
        import multiprocessing
        cpus = multiprocessing.cpu_count()
    except:
        pass
    return cpus
