import sublime
import threading
import time
import Queue


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


def get_cpu_count():
    cpus = 1
    try:
        import multiprocessing
        cpus = multiprocessing.cpu_count()
    except:
        pass
    return cpus
