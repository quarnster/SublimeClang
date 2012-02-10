import sublime
import threading
import time
import Queue
import os, re


class Worker(object):
    def __init__(self):
        self.tasks = Queue.Queue()
        for i in range(get_cpu_count()):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

    def display_status(self):
        sublime.status_message(self.status)

    def set_status(self, msg):
        self.status = msg
        sublime.set_timeout(self.display_status, 0)

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


def get_settings():
    return sublime.load_settings("SublimeClang.sublime-settings")


def get_setting(key, default=None):
    try:
        s = sublime.active_window().active_view().settings()
        if s.has("sublimeclang_%s" % key):
            return s.get("sublimeclang_%s" % key)
    except:
        pass
    return get_settings().get(key, default)


def expand_path(value):
    value = value % ({'home': os.getenv('HOME')})

    get_existing_files = \
        lambda m: [ path \
            for f in sublime.active_window().folders() \
            for path in [os.path.join(f, m.group('file'))] \
            if os.path.exists(path) \
        ]
    value = re.sub(r'\${project_path:(?P<file>[^}]+)}', lambda m: len(get_existing_files(m)) > 0 and get_existing_files(m)[0] or m.group('file'), value)
    value = re.sub(r'\${folder:(?P<file>.*)}', lambda m: os.path.dirname(m.group('file')), value)

    return value

def complete_path(value):
    path_init, path_last = os.path.split(value)
    if path_init[:2] == "-I" and (path_last == "**" or path_last == "*") :
      starting_path = expand_path(path_init[2:])
      include_paths = []
      if os.path.exists(starting_path):
        if path_last == "*":
          for dirname in os.listdir(starting_path):
              if not dirname.startswith("."): # skip directories that begin with .
                include_paths.append("-I" + os.path.join(starting_path, dirname))
        elif path_last == "**":
          for dirpath, dirs, files in os.walk(starting_path):
            for dirname in list(dirs):
              if dirname.startswith("."): # skip directories that begin with .
                dirs.remove(dirname)
            if dirpath != starting_path:
              include_paths.append("-I" + dirpath)
        else:
          include_paths.append("-I" + starting_path)
      else:
        pass # perhaps put some error here?
      return include_paths
    else:
      return [expand_path(value)]

def get_path_setting(key, default=None):
    value = get_setting(key, default)
    opts = []
    if isinstance(value, str) or isinstance(value, unicode):
        opts.extend(complete_path(value))
    else:
        for v in value:
          opts.extend(complete_path(v))
    return opts


def get_cpu_count():
    cpus = 1
    try:
        import multiprocessing
        cpus = multiprocessing.cpu_count()
    except:
        pass
    return cpus
