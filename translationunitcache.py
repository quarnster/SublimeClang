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
from common import Worker, expand_path, get_setting, get_path_setting, get_language, LockedVariable, run_in_main_thread, error_message
from clang import cindex
import time
import shlex
import subprocess
from ctypes import cdll, Structure, POINTER, c_char_p, c_void_p, c_uint, c_bool
from parsehelp.parsehelp import *
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
    _fields_ = [("cursor", cindex.Cursor), ("insert", c_char_p), ("display", c_char_p), ("access", c_uint), ("static", c_bool), ("baseclass", c_bool)]


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
cache_findType = cachelib.cache_findType
cache_findType.argtypes = [c_void_p, POINTER(c_char_p), c_uint, c_char_p]
cache_findType.restype = cindex.Cursor
cache_completeCursor = cachelib.cache_completeCursor
cache_completeCursor.argtypes = [c_void_p, cindex.Cursor]
cache_completeCursor.restype = POINTER(CacheCompletionResults)
cache_clangComplete = cachelib.cache_clangComplete
cache_clangComplete.argtypes = [c_void_p, c_char_p, c_uint, c_uint, POINTER(cindex._CXUnsavedFile), c_uint, c_bool]
cache_clangComplete.restype = POINTER(CacheCompletionResults)


class Cache:
    def __init__(self, tu, filename):
        self.cache = _createCache(tu.cursor)
        if self.cache == None:
            raise Exception("cache is None")
        self.tu = tu
        self.filename = filename

    def __del__(self):
        if self.cache:
            _deleteCache(self.cache)

    def get_native_namespace(self, namespace):
        nsarg = (c_char_p*len(namespace))()
        for i in range(len(namespace)):
            nsarg[i] = namespace[i]
        return nsarg

    def complete_namespace(self, namespace):
        ret = None
        nsarg = self.get_native_namespace(namespace)
        comp = cache_completeNamespace(self.cache, nsarg, len(nsarg))
        if comp:
            ret = [(x.display, x.insert) for x in comp[0]]
            cache_disposeCompletionResults(comp)
        return ret

    def find_type(self, data, typename):
        extra = None
        idx = typename.rfind("::")
        if idx != -1:
            extra = typename[:idx]
            typename = typename[idx+2:]
        namespaces = extract_used_namespaces(data)
        namespaces.insert(0, None)
        namespaces.insert(1, extract_namespace(data))
        cursor = None
        for ns in namespaces:
            nsarg = None
            nslen = 0
            if extra:
                if ns:
                    ns = ns + "::" + extra
                else:
                    ns = extra
            if ns:
                nsarg = self.get_native_namespace(ns.split("::"))
                nslen = len(nsarg)
            cursor = cache_findType(self.cache, nsarg, nslen, typename)
            if not cursor is None and not cursor.kind.is_invalid():
                if cursor.kind.is_reference():
                    cursor = cursor.get_referenced()
                break
        return cursor

    def get_template_type_count(self, temp):
        ret = []
        for child in temp.get_children():
            if child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                ret.append(child)
        return len(ret)

    def solve_template_from_cursor(self, temp, member, template):
        found = False
        children = []
        for child in member.get_children():
            if not found:
                if child.get_reference() == temp:
                    found = True
                continue
            if child.kind == cindex.CursorKind.TEMPLATE_REF:
                # Don't support nested templates for now
                children = []
                break
            elif child.kind == cindex.CursorKind.TYPE_REF:
                children.append((child.get_resolved_cursor(), None))
        return temp, children

    def solve_member(self, data, typecursor, member, template):
        temp = None
        pointer = False
        if not member is None and not member.kind.is_invalid():
            temp = member.get_returned_cursor()
            pointer = member.result_type.kind == cindex.TypeKind.POINTER

            if not temp is None and not temp.kind.is_invalid():
                if temp.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                    off = 0
                    for child in typecursor.get_children():
                        if child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                            if child == temp:
                                break
                            off += 1
                    if template[1] and off < len(template[1]):
                        template = template[1][off]
                        if isinstance(template[0], cindex.Cursor):
                            temp = template[0]
                        else:
                            temp = self.find_type(data, template[0])
                elif temp.kind == cindex.CursorKind.CLASS_TEMPLATE:
                    template = self.solve_template_from_cursor(temp, member, template)

        return temp, template, pointer

    def inherits(self, parent, child):
        if child is None or child.kind.is_invalid():
            return False
        if parent == child:
            return True
        for c in child.get_children():
            if c.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                for c2 in c.get_children():
                    if c2.kind == cindex.CursorKind.TYPE_REF:
                        c2 = c2.get_reference()
                        return self.inherits(parent, c2)
        return False

    def complete(self, data, prefix):
        line = extract_line_at_offset(data, len(data)-1)
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        ret = None
        if re.search("::$", before):
            match = re.search("([^\(\\s,]+::)+$", before)
            if match == None:
                ret = None
                cached_results = cache_complete_startswith(self.cache, prefix)
                if cached_results and len(cached_results[0]):
                    ret = []
                    for x in cached_results[0]:
                        if x.cursor.kind != cindex.CursorKind.MACRO_DEFINITION and \
                                x.cursor.kind != cindex.CursorKind.CXX_METHOD:
                            ret.append((x.display, x.insert))
                    cache_disposeCompletionResults(cached_results)
                return ret
            before = match.group(1)
            namespace = before.split("::")
            namespace.pop()  # the last item is going to be "prefix"
            ret = self.complete_namespace(namespace)

            if len(ret) == 0:
                ret = None
                typename = namespace.pop()
                c = self.find_type(data, typename)
                if not c is None and not c.kind.is_invalid():
                    comp = cache_completeCursor(self.cache, c)
                    if comp and len(comp[0]):
                        inherits = False
                        ret = []
                        clazz = extract_class_from_function(data)
                        if clazz == None:
                            clazz = extract_class(data)
                        if clazz != None:
                            c2 = self.find_type(data, clazz)
                            inherits = self.inherits(c, c2)

                        for c in comp[0]:
                            if (inherits and c.access != cindex.CXXAccessSpecifier.PRIVATE) or c.static or c.cursor.kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
                                ret.append((c.display, c.insert))
                        cache_disposeCompletionResults(comp)
            return ret
        elif re.search("([^ \t]+)(\.|\->)$", before):
            comp = data
            if len(prefix) > 0:
                comp = data[:-len(prefix)]
            typedef = get_type_definition(comp)
            if typedef == None:
                return None
            line, column, typename, var, tocomplete = typedef
            print typedef
            if typename == None:
                return None
            cursor = None
            template = solve_template(get_base_type(typename))
            pointer = is_pointer(typename)
            if not var is None:
                if line > 0 and column > 0:
                    cursor = cindex.Cursor.get(self.tu, self.filename, line, column)
                if cursor is None or cursor.kind.is_invalid() or cursor.spelling != var:
                    cursor = self.find_type(data, template[0])
                else:
                    # It's going to be a declaration of some kind, so
                    # get the returned cursor
                    cursor = cursor.get_returned_cursor()
            else:
                # Probably a member of the current class
                clazz = extract_class_from_function(data)
                if clazz == None:
                    clazz = extract_class(data)
                if clazz != None:
                    cursor = self.find_type(data, clazz)
                    if not cursor is None and not cursor.kind.is_invalid():
                        func = False
                        if typename.endswith("()"):
                            func = True
                            typename = typename[:-2]
                        member = cursor.get_member(typename, func)
                        cursor, template, pointer = self.solve_member(data, cursor, member, template)

            if not cursor is None and not cursor.kind.is_invalid():
                r = cursor
                count = 0
                while len(tocomplete) and count < 10:
                    if r is None or \
                            not (r.kind == cindex.CursorKind.CLASS_DECL or \
                            r.kind == cindex.CursorKind.STRUCT_DECL or \
                            r.kind == cindex.CursorKind.CLASS_TEMPLATE):
                        r = None
                        break
                    count += 1
                    match = re.search(r"([^\.\-\(:]+)?(\(|\.|->|::)(.*)", tocomplete)
                    if match == None:
                        break

                    tocomplete = match.group(3)
                    count = 1
                    function = False
                    if match.group(2) == "(":
                        function = True
                        tocomplete = tocomplete[1:]
                    elif match.group(2) == "[":
                        # TODO: operator[]
                        tocomplete = tocomplete[1:]

                    left = re.match(r"(\.|\->|::)?(.*)", tocomplete)
                    tocomplete = left.group(2)
                    if left.group(1) != None:
                        tocomplete = left.group(1) + tocomplete
                    if match.group(1) == None and match.group(2) == "->" and not pointer:
                        comp = r.get_member("operator->", True)
                        r, template, pointer = self.solve_member(data, r, comp, template)

                    if match.group(1):
                        member = match.group(1)
                        if "[" in member:
                            member = get_base_type(member)
                        member = r.get_member(member, function)
                        r, template, pointer = self.solve_member(data, r, member, template)

                if not r is None and not r.kind.is_invalid():
                    clazz = extract_class_from_function(data)
                    if clazz == None:
                        clazz = extract_class(data)
                    selfcompletion = clazz == r.spelling
                    comp = cache_completeCursor(self.cache, r)
                    if comp and len(comp[0]):
                        ret = []
                        for c in comp[0]:
                            if not c.static and c.cursor.kind != cindex.CursorKind.ENUM_CONSTANT_DECL and \
                                    c.cursor.kind != cindex.CursorKind.ENUM_DECL and \
                                    c.cursor.kind != cindex.CursorKind.TYPEDEF_DECL and \
                                    c.cursor.kind != cindex.CursorKind.CLASS_DECL and \
                                    c.cursor.kind != cindex.CursorKind.STRUCT_DECL and \
                                    c.cursor.kind != cindex.CursorKind.CLASS_TEMPLATE and \
                                    (c.access == cindex.CXXAccessSpecifier.PUBLIC or selfcompletion):
                                add = (c.display, c.insert)
                                if add not in ret:
                                    ret.append(add)
                        cache_disposeCompletionResults(comp)
            return ret
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
            clazz = extract_class_from_function(data)
            if clazz == None:
                clazz = extract_class(data)
            if clazz != None:
                ns = extract_namespace(data)
                c = None
                if ns == None:
                    c = cache_findType(self.cache, None, 0, clazz)
                else:
                    ns = ns.split("::")
                    nsarg = (c_char_p * len(ns))()
                    for i in range(len(ns)):
                        nsarg[i] = ns[i]
                    c = cache_findType(self.cache, nsarg, len(ns), clazz)
                if not c is None and not c.kind.is_invalid():
                    comp = cache_completeCursor(self.cache, c)
                    if comp:
                        for c in comp[0]:
                            if not c.static and not c.cursor.kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
                                add = (c.display, c.insert)
                                if add not in ret:
                                    ret.append(add)
                        cache_disposeCompletionResults(comp)
            namespaces = extract_used_namespaces(data)
            ns = extract_namespace(data)
            if ns:
                namespaces.append(ns)
            for ns in namespaces:
                ns = ns.split("::")
                add = self.complete_namespace(ns)
                if add:
                    ret.extend(add)
        return ret

    def clangcomplete(self, filename, row, col, unsaved_files, membercomp):
        ret = None
        unsaved = None
        if len(unsaved_files):
            unsaved = (cindex._CXUnsavedFile * len(unsaved_files))()
            for i, (name, value) in enumerate(unsaved_files):
                if not isinstance(value, str):
                    value = value.encode("ascii", "ignore")
                unsaved[i].name = name
                unsaved[i].contents = value
                unsaved[i].length = len(value)
        comp = cache_clangComplete(self.cache, filename, row, col, unsaved, len(unsaved_files), membercomp)

        if comp:
            ret = [(c.display, c.insert) for c in comp[0]]
            cache_disposeCompletionResults(comp)
        return ret

class TranslationUnitCache(Worker):
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4

    class LockedTranslationUnit(LockedVariable):
        def __init__(self, var, fn):
            LockedVariable.__init__(self, var)
            self.cache = Cache(var, fn)

    def __init__(self):
        self.as_super = super(TranslationUnitCache, self)
        self.as_super.__init__()
        self.translationUnits = LockedVariable({})
        self.parsingList = LockedVariable([])
        self.busyList = LockedVariable([])
        self.index_parse_options = 13
        self.index = None
        self.debug_options = False

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
        filename, opts, opts_script, on_done = data
        if self.add_busy(filename, self.task_parse, data):
            return
        try:
            self.set_status("Parsing %s" % filename)
            self.get_translation_unit(filename, opts, opts_script)
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
        filename, opts, opts_script, unsaved_files, on_done = data
        if self.add_busy(filename, self.task_reparse, data):
            return
        try:
            self.set_status("Reparsing %s" % filename)
            tu = self.get_translation_unit(filename, opts, opts_script, unsaved_files)
            if tu != None:
                tu.lock()
                try:
                    tu.var.reparse(unsaved_files)
                    tu.cache = Cache(tu.var, filename)
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
                (filename, self.get_opts(view), self.get_opts_script(view), unsaved_files, on_done)))
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
                (filename, self.get_opts(view), self.get_opts_script(view), on_done)))
        self.translationUnits.unlock()
        self.parsingList.unlock()
        return ret

    def get_opts_script(self, view):
        return expand_path(get_setting("options_script", None, view), view.window())

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
        self.debug_options = get_setting("debug_options", False)
        self.index_parse_options = get_setting("index_parse_options", 13, view)
        return opts

    def get_translation_unit(self, filename, opts=[], opts_script=None, unsaved_files=[]):
        if self.index == None:
            self.index = cindex.Index.create()
        tu = None
        tus = self.translationUnits.lock()
        if filename not in tus:
            self.translationUnits.unlock()

            if opts_script:
                # shlex.split barfs if fed with an unicode strings
                args = shlex.split(opts_script.encode()) + [filename]
                process = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                output = process.communicate()
                if process.returncode:
                    print "The options_script failed with code [%s]" % process.returncode
                    print output[1]
                else:
                    opts += shlex.split(output[0])

            if self.debug_options:
                print "Will compile file %s with the following options:\n%s" % (filename, opts)

            opts.append(filename)
            tu = self.index.parse(None, opts, unsaved_files,
                                  self.index_parse_options)
            if tu != None:
                # Apparently the options aren't used in the first parse,
                # so reparse to heat up the cache
                tu.reparse(unsaved_files)
                tu = TranslationUnitCache.LockedTranslationUnit(tu, filename)
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
