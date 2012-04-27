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
from common import Worker, get_setting, get_path_setting, get_language, LockedVariable, run_in_main_thread, error_message
from clang import cindex
import time
from ctypes import cdll, Structure, POINTER, c_char_p, c_void_p, c_uint
from parsehelp import *
import re


def get_cache_library():
    import platform
    name = platform.system()
    if name == 'Darwin':
        return cdll.LoadLibrary('libcache.dylib')
    elif name == 'Windows':
        if cindex.isWin64:
            return cdll.LoadLibrary("libcache_x64.dll")
        return cdll.LoadLibrary('libcache.dll')
    else:
        try:
            # Try loading with absolute path first
            import os
            path = os.path.dirname(os.path.abspath(__file__))
            return cdll.LoadLibrary('%s/libcache.so' % path)
        except:
            try:
                # See if there's one in the system path
                return cdll.LoadLibrary("libcache.so")
            except:
                import traceback
                traceback.print_exc()
                error_message("""\
It looks like libcache.so couldn't be loaded. On Linux you have to \
compile it yourself.

See http://github.com/quarnster/SublimeClang for more details.
""")


class CacheEntry(Structure):
    _fields_ = [("cursor", cindex.Cursor), ("insert", c_char_p), ("display", c_char_p)]


class CacheCompletionResults(Structure):
    _fields_ = [("entries", POINTER(POINTER(CacheEntry))), ("length", c_uint)]

    def __len__(self):
        return self.length

    def __getitem__(self, key):
        if key >= self.length:
            raise IndexError
        return self.entries[key][0]


cachelib = get_cache_library()
_createCache = cachelib.createCache
_createCache.restype = c_void_p
_createCache.argtypes = [cindex.Cursor]
_deleteCache = cachelib.deleteCache
_deleteCache.argtypes = [c_void_p]
cache_completeNamespace = cachelib.cache_completeNamespace
cache_completeNamespace.argtypes = [c_void_p, POINTER(c_char_p), c_uint]
cache_completeNamespace.restype = POINTER(CacheCompletionResults)
cache_complete_startswith = cachelib.cache_complete_startswith
cache_complete_startswith.argtypes = [c_void_p, c_char_p]
cache_complete_startswith.restype = POINTER(CacheCompletionResults)
cache_disposeCompletionResults = cachelib.cache_disposeCompletionResults
cache_disposeCompletionResults.argtypes = [POINTER(CacheCompletionResults)]


class Cache:
    def __init__(self, tu):
        self.cache = _createCache(tu.cursor)
        if self.cache == None:
            raise Exception("cache is None")
        self.tu = tu

    def __del__(self):
        if self.cache:
            _deleteCache(self.cache)

    def complete(self, data, prefix):
        line = extract_line_at_offset(data, len(data)-1)
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        ret = None
        if re.search("::$", before):
            # TODO
            namespace = ["std"]
            nsarg = (c_char_p*len(namespace))()
            for i in range(len(namespace)):
                nsarg[i] = namespace[i]
            comp = cache_completeNamespace(self.cache, nsarg, len(nsarg))
            if comp:
                ret = [(x.display, x.insert) for x in comp[0]]
                cache_disposeCompletionResults(comp)
            return ret
        elif re.search("([^ \t]+)(\.|\->)$", before):
            # TODO
            return None
        else:
            cached_results = cache_complete_startswith(self.cache, prefix)
            if cached_results:
                ret = [(x.display, x.insert) for x in cached_results[0]]
                cache_disposeCompletionResults(cached_results)
            variables = extract_variables(data)
            var = [("%s\t%s" % (v[1], v[0]), v[1]) for v in variables]
            if len(var) and ret == None:
                ret = []
            for v in var:
                if v[1].startswith(prefix) and not v in ret:
                    ret.append(v)
        return ret


class TranslationUnitCache(Worker):
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4

    class LockedTranslationUnit(LockedVariable):
        def __init__(self, var):
            LockedVariable.__init__(self, var)
            self.cache = Cache(var)

    def __init__(self):
        self.as_super = super(TranslationUnitCache, self)
        self.as_super.__init__()
        self.translationUnits = LockedVariable({})
        self.parsingList = LockedVariable([])
        self.busyList = LockedVariable([])
        self.index_parse_options = 13
        self.index = None

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

    def display_status(self):
        if get_setting("parse_status_messages", True):
            self.as_super.display_status()

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
            self.set_status("Parsing %s" % filename)
            self.get_translation_unit(filename, opts)
            self.set_status("Parsing %s done" % filename)
        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.remove_busy(filename)
        if not on_done is None:
            run_in_main_thread(on_done)

    def task_reparse(self, data):
        filename, opts, unsaved_files, on_done = data
        if self.add_busy(filename, self.task_reparse, data):
            return
        try:
            self.set_status("Reparsing %s" % filename)
            tu = self.get_translation_unit(filename, opts, unsaved_files)
            if tu != None:
                tu.lock()
                try:
                    tu.var.reparse(unsaved_files)
                    tu.cache = Cache(tu.var)
                    self.set_status("Reparsing %s done" % filename)
                finally:
                    tu.unlock()
        finally:
            l = self.parsingList.lock()
            try:
                l.remove(filename)
            finally:
                self.parsingList.unlock()
                self.remove_busy(filename)
        if not on_done is None:
            run_in_main_thread(on_done)

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
                    tus.pop(data)
            finally:
                self.translationUnits.unlock()
        finally:
            self.remove_busy(data)

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

    def add(self, view, filename, on_done=None):
        ret = False
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        if filename not in tu and filename not in pl:
            ret = True
            pl.append(filename)
            self.tasks.put((
                self.task_parse,
                (filename, self.get_opts(view), on_done)))
        self.translationUnits.unlock()
        self.parsingList.unlock()
        return ret

    def get_opts(self, view):
        opts = get_path_setting("options", [], view)
        if get_setting("add_language_option", True, view):
            language = get_language(view)
            if language == "objc":
                opts.append("-ObjC")
            elif language == "objc++":
                opts.append("-ObjC++")
            else:
                opts.append("-x")
                opts.append(language)
            additional_language_options = get_setting("additional_language_options", {}, view)
            if additional_language_options.has_key(language):
                opts.extend(additional_language_options[language] or [])
        if get_setting("debug_options", False):
            print "Will compile file %s with the following options:\n%s" % (view.file_name(), opts)
        self.index_parse_options = get_setting("index_parse_options", 13, view)
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
                tu = TranslationUnitCache.LockedTranslationUnit(tu)
                tus = self.translationUnits.lock()
                tus[filename] = tu
                self.translationUnits.unlock()
        else:
            tu = tus[filename]
            self.translationUnits.unlock()
        return tu

    def remove(self, filename):
        self.tasks.put((self.task_remove, filename))

    def clear(self):
        self.tasks.put((self.task_clear, None))

tuCache = TranslationUnitCache()
