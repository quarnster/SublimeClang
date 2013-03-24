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

import os
import sys

from .common import Worker, complete_path, expand_path, get_setting, get_path_setting,\
                    get_language, LockedVariable, run_in_main_thread, error_message,\
                    display_user_selection, get_cpu_count, status_message, bencode, bdecode,\
                    sencode, sdecode, are_we_there_yet, look_for_file
from .clang import cindex
from .parsehelp.parsehelp import *

try:
    import Queue
except:
    import queue as Queue


import time
import shlex
import subprocess
import sys
from ctypes import cdll, Structure, POINTER, c_char_p, c_void_p, c_uint, c_bool

import re
import threading

scriptpath = os.path.dirname(os.path.abspath(__file__))


def get_cache_library():
    import platform
    name = platform.system()
    filename = ''

    if name == 'Darwin':
        filename = 'libcache.dylib'
    elif name == 'Windows':
        filename = 'libcache_x64.dll' if cindex.isWin64 else 'libcache.dll'
    else:
        filename = 'libcache.so'

    filepath = look_for_file(filename, scriptpath, 3)
    if filepath:
        # Try loading with absolute path first
        return cdll.LoadLibrary(filepath)
    try:
        # See if there's one in the system path
        return cdll.LoadLibrary(filename)
    except:
        import traceback
        traceback.print_exc()
        error_message("""\
It looks like %s couldn't be loaded. On Linux you have to \
compile it yourself.

See http://github.com/quarnster/SublimeClang for more details.
""" % (filename))


class CacheEntry(Structure):
    _fields_ = [("cursor", cindex.Cursor), ("raw_insert", c_char_p), ("raw_display", c_char_p), ("access", c_uint), ("static", c_bool), ("baseclass", c_bool)]
    @property
    def insert(self):
        return bdecode(self.raw_insert)

    @property
    def display(self):
        return bdecode(self.raw_display)

class _Cache(Structure):
    def __del__(self):
        _deleteCache(self)

class CacheCompletionResults(Structure):
    @property
    def length(self):
        return self.__len__()

    def __len__(self):
        return completionResults_length(self)

    def __getitem__(self, key):
        if key >= self.length:
            raise IndexError
        return completionResults_getEntry(self, key)[0]

    def __del__(self):
        completionResults_dispose(self)


cachelib = get_cache_library()
if cachelib:
    try:
        import json
        _getVersion = cachelib.getVersion
        _getVersion.restype = c_char_p
        f = open("%s/../package.json" % scriptpath)
        data = json.load(f)
        f.close()
        json = data["packages"][0]["platforms"]["*"][0]["version"]
        lib = _getVersion().decode(sys.getdefaultencoding())
        print("Have SublimeClang package: %s" % json)
        print("Have SublimeClang libcache: %s" % lib)
        assert lib == json
    except:
        import traceback
        traceback.print_exc()
        error_message("Your SublimeClang libcache is out of date. Try restarting ST2 and if that fails, uninstall SublimeClang, restart ST2 and install it again.")

_createCache = cachelib.createCache
_createCache.restype = POINTER(_Cache)
_createCache.argtypes = [cindex.Cursor]
_deleteCache = cachelib.deleteCache
_deleteCache.argtypes = [POINTER(_Cache)]
cache_completeNamespace = cachelib.cache_completeNamespace
cache_completeNamespace.argtypes = [POINTER(_Cache), POINTER(c_char_p), c_uint]
cache_completeNamespace.restype = POINTER(CacheCompletionResults)
cache_complete_startswith = cachelib.cache_complete_startswith
cache_complete_startswith.argtypes = [POINTER(_Cache), c_char_p]
cache_complete_startswith.restype = POINTER(CacheCompletionResults)
completionResults_length = cachelib.completionResults_length
completionResults_length.argtypes = [POINTER(CacheCompletionResults)]
completionResults_length.restype = c_uint
completionResults_getEntry = cachelib.completionResults_getEntry
completionResults_getEntry.argtypes = [POINTER(CacheCompletionResults)]
completionResults_getEntry.restype = POINTER(CacheEntry)
completionResults_dispose = cachelib.completionResults_dispose
completionResults_dispose.argtypes = [POINTER(CacheCompletionResults)]
cache_findType = cachelib.cache_findType
cache_findType.argtypes = [POINTER(_Cache), POINTER(c_char_p), c_uint, c_char_p]
cache_findType.restype = cindex.Cursor
cache_completeCursor = cachelib.cache_completeCursor
cache_completeCursor.argtypes = [POINTER(_Cache), cindex.Cursor]
cache_completeCursor.restype = POINTER(CacheCompletionResults)
cache_clangComplete = cachelib.cache_clangComplete
cache_clangComplete.argtypes = [POINTER(_Cache), c_char_p, c_uint, c_uint, POINTER(cindex._CXUnsavedFile), c_uint, c_bool]
cache_clangComplete.restype = POINTER(CacheCompletionResults)


def remove_duplicates(data):
    if data == None:
        return None
    seen = {}
    ret = []
    for d in data:
        if d in seen:
            continue
        seen[d] = 1
        ret.append(d)
    return ret


class Cache:
    def __init__(self, tu, filename):
        self.cache = _createCache(tu.cursor)[0]
        assert self.cache != None
        self.tu = tu
        self.filename = filename

    def __del__(self):
        self.tu = None
        self.cache = None

    def get_native_namespace(self, namespace):
        nsarg = (c_char_p*len(namespace))()
        for i in range(len(namespace)):
            nsarg[i] = bencode(namespace[i])
        return nsarg

    def complete_namespace(self, namespace):
        ret = None
        if len(namespace):
            nsarg = self.get_native_namespace(namespace)
            comp = cache_completeNamespace(self.cache, nsarg, len(nsarg))
            if comp:
                ret = [(x.display, x.insert) for x in comp[0]]
        return ret

    def get_namespace_from_cursor(self, cursor):
        namespace = []
        while cursor != None and cursor.kind == cindex.CursorKind.NAMESPACE:
            namespace.insert(0, cursor.displayname)
            cursor = cursor.get_lexical_parent()
        return namespace

    def find_type(self, data, typename):
        extra = None
        idx = typename.rfind("::")
        if idx != -1:
            extra = typename[:idx]
            typename = typename[idx+2:]
        if "<" in typename:
            typename = typename[:typename.find("<")]
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
            cursor = cache_findType(self.cache, nsarg, nslen, bencode(typename))
            if cursor != None and not cursor.kind.is_invalid():
                if cursor.kind.is_reference():
                    cursor = cursor.get_referenced()
                break

        if (cursor != None and not cursor.kind.is_invalid()) or idx == -1:
            return cursor

        # Maybe it's a subtype?
        parent = self.find_type(data, extra)
        if parent != None and not parent.kind.is_invalid():
            for child in parent.get_children():
                if child.kind.is_declaration() and child.spelling == typename:
                    return child
        return None

    def solve_template_from_cursor(self, temp, member, template):
        found = False
        children = []
        for child in member.get_children():
            if not found:
                ref = child.get_reference()
                if ref != None and ref == temp:
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
        pointer = 0
        if member != None and not member.kind.is_invalid():
            temp = member.get_returned_cursor()
            pointer = member.get_returned_pointer_level()

            if temp != None and not temp.kind.is_invalid():
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
        if child == None or child.kind.is_invalid():
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

    def filter(self, ret, constr=False):
        if ret == None:
            return None
        if constr:
            match = "\t(namespace|constructor|class|typedef|struct)$"
        else:
            match = "\t(?!constructor)[^\t]+$"
        regex = re.compile(match)
        ret2 = []
        constrs = []
        for display, insert in ret:
            if not regex.search(display):
                continue
            if constr and display.endswith("constructor"):
                constrs.append(display[:display.find("(")])
            ret2.append((display, insert))
        if constr:
            for name in constrs:
                regex = re.compile(r"%s\t(class|typedef|struct)$" % name)
                ret2 = list(filter(lambda a: not regex.search(a[0]), ret2))
        return ret2


    def complete(self, data, prefix):
        line = extract_line_at_offset(data, len(data)-1)
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        ret = None
        if re.search(r"::$", before):
            constr = re.search(r"(\W|^)new\s+(\w+::)+$", before) != None

            ret = []
            match = re.search(r"([^\(\s,]+::)+$", before)
            if match == None:
                ret = None
                cached_results = cache_complete_startswith(self.cache, bencode(prefix))
                if cached_results:
                    ret = []
                    for x in cached_results[0]:
                        if x.cursor.kind != cindex.CursorKind.MACRO_DEFINITION and \
                                x.cursor.kind != cindex.CursorKind.CXX_METHOD:
                            ret.append((x.display, x.insert))
                return ret
            before = match.group(1)
            namespace = before.split("::")
            namespace.pop()  # the last item is going to be "prefix"
            ret = self.complete_namespace(namespace)

            if len(ret) == 0:
                typename = "::".join(namespace)
                c = self.find_type(data, typename)
                if c != None:
                    if c.kind == cindex.CursorKind.ENUM_DECL:
                        # It's not valid to complete enum::
                        c = None
                if c != None and not c.kind.is_invalid() and c.kind != cindex.CursorKind.NAMESPACE:
                    # It's going to be a declaration of some kind, so
                    # get the returned cursor
                    c = c.get_returned_cursor()
                    if c != None and c.kind == cindex.CursorKind.TYPEDEF_DECL:
                        # Too complex typedef to be able to complete, fall back to slow completions
                        c = None
                        ret = None
                if c != None and not c.kind.is_invalid():
                    if c.kind == cindex.CursorKind.NAMESPACE:
                        namespace = self.get_namespace_from_cursor(c)
                        return self.complete_namespace(namespace)
                    comp = cache_completeCursor(self.cache, c)

                    if comp:
                        inherits = False
                        clazz = extract_class_from_function(data)
                        if clazz == None:
                            clazz = extract_class(data)
                        if clazz != None:
                            c2 = self.find_type(data, clazz)
                            inherits = self.inherits(c, c2)

                        selfcompletion = clazz == c.spelling

                        for c in comp[0]:
                            if (selfcompletion and not c.baseclass) or \
                                    (inherits and not c.access == cindex.CXXAccessSpecifier.PRIVATE) or \
                                    (c.access == cindex.CXXAccessSpecifier.PUBLIC and \
                                     (
                                        c.static or \
                                        c.cursor.kind == cindex.CursorKind.TYPEDEF_DECL or \
                                        c.cursor.kind == cindex.CursorKind.CLASS_DECL or \
                                        c.cursor.kind == cindex.CursorKind.STRUCT_DECL or \
                                        c.cursor.kind == cindex.CursorKind.ENUM_CONSTANT_DECL or \
                                        c.cursor.kind == cindex.CursorKind.ENUM_DECL)):
                                ret.append((c.display, c.insert))
            ret = self.filter(ret, constr)
            return ret
        elif re.search(r"(\w+\]+\s+$|\[[\w\.\-\>]+\s+$|([^ \t]+)(\.|\->)$)", before):
            comp = data
            if len(prefix) > 0:
                comp = data[:-len(prefix)]
            typedef = get_type_definition(comp)
            if typedef == None:
                return None
            line, column, typename, var, tocomplete = typedef
            if typename == None:
                return None
            cursor = None
            template = solve_template(get_base_type(typename))
            pointer = get_pointer_level(typename)
            if var == "this":
                pointer = 1

            if var != None:
                if line > 0 and column > 0:
                    cursor = cindex.Cursor.get(self.tu, self.filename, line, column)
                if cursor == None or cursor.kind.is_invalid() or cursor.spelling != var:
                    cursor = self.find_type(data, template[0])
                else:
                    pointer = 0  # get the pointer level from the cursor instead
                if cursor != None and not cursor.kind.is_invalid() and \
                        cursor.spelling == typename and \
                        cursor.kind == cindex.CursorKind.VAR_DECL:
                    # We're trying to use a variable as a type.. This isn't valid
                    cursor = None
                    ret = []
                if cursor != None and not cursor.kind.is_invalid():
                    # It's going to be a declaration of some kind, so
                    # get the returned cursor
                    pointer += cursor.get_returned_pointer_level()
                    cursor = cursor.get_returned_cursor()
                    if cursor == None:
                        ret = []
            else:
                # Probably a member of the current class
                clazz = extract_class_from_function(data)
                if clazz == None:
                    clazz = extract_class(data)
                if clazz != None:
                    cursor = self.find_type(data, clazz)
                    if cursor != None and not cursor.kind.is_invalid():
                        func = False
                        if typename.endswith("()"):
                            func = True
                            typename = typename[:-2]
                        member = cursor.get_member(typename, func)
                        cursor, template, pointer = self.solve_member(data, cursor, member, template)
                        if member != None and (cursor == None or cursor.kind.is_invalid()):
                            ret = []
                if cursor == None or cursor.kind.is_invalid():
                    # Is it by any chance a struct variable or an ObjC class?
                    cursor = self.find_type(data, template[0])
                    if cursor == None or cursor.kind.is_invalid() or \
                            cursor.spelling != typename or \
                            (not tocomplete.startswith("::") and \
                                cursor.kind != cindex.CursorKind.VAR_DECL and \
                                cursor.kind != cindex.CursorKind.OBJC_INTERFACE_DECL) or \
                            (tocomplete.startswith("::") and \
                                not (cursor.kind == cindex.CursorKind.CLASS_DECL or \
                                     cursor.kind == cindex.CursorKind.STRUCT_DECL or \
                                     cursor.kind == cindex.CursorKind.OBJC_INTERFACE_DECL or \
                                     cursor.kind == cindex.CursorKind.CLASS_TEMPLATE)):
                        cursor = None
                    if cursor != None and not cursor.kind.is_invalid():
                        # It's going to be a declaration of some kind, so
                        # get the returned cursor
                        pointer = cursor.get_returned_pointer_level()
                        cursor = cursor.get_returned_cursor()
                        if cursor == None:
                            ret = []
                if cursor == None or cursor.kind.is_invalid():
                    # Is it a non-member function?
                    func = False
                    if typename.endswith("()"):
                        func = True
                        typename = typename[:-2]
                    cached_results = cache_complete_startswith(self.cache, bencode(typename))
                    if cached_results:
                        for x in cached_results[0]:
                            if x.cursor.spelling == typename:
                                if x.cursor.kind == cindex.CursorKind.VAR_DECL or \
                                        x.cursor.kind == cindex.CursorKind.FUNCTION_DECL:
                                    cursor = x.cursor
                                    pointer = cursor.get_returned_pointer_level()
                                    cursor = cursor.get_returned_cursor()
                                    if cursor == None:
                                        ret = []
                                    break

            if cursor != None and not cursor.kind.is_invalid():
                r = cursor
                m2 = None
                count = 0
                while len(tocomplete) and count < 10:
                    if r == None or \
                            not (r.kind == cindex.CursorKind.CLASS_DECL or \
                            r.kind == cindex.CursorKind.STRUCT_DECL or \
                            r.kind == cindex.CursorKind.UNION_DECL or \
                            r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL or \
                            r.kind == cindex.CursorKind.CLASS_TEMPLATE):
                        if r != None and not (r.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER or \
                                             (r.kind == cindex.CursorKind.TYPEDEF_DECL and len(r.get_children()))):
                            ret = []
                        r = None
                        break
                    count += 1
                    match = re.search(r"^([^\.\-\(:\[\]]+)?(\[\]|\(|\.|->|::)(.*)", tocomplete)
                    if match == None:
                        # probably Objective C code
                        match = re.search(r"^(\S+)?(\s+)(.*)", tocomplete)
                        if match == None:
                            break

                    if r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL:
                        pointer = 0
                    tocomplete = match.group(3)
                    count = 1
                    function = False
                    if match.group(2) == "(":
                        function = True
                        tocomplete = tocomplete[1:]

                    left = re.match(r"(\.|\->|::)?(.*)", tocomplete)
                    tocomplete = left.group(2)
                    if left.group(1) != None:
                        tocomplete = left.group(1) + tocomplete
                    nextm2 = match.group(2)

                    if match.group(1) == None and pointer == 0 and r.kind != cindex.CursorKind.OBJC_INTERFACE_DECL:
                        if match.group(2) == "->":
                            comp = r.get_member("operator->", True)
                            r, template, pointer = self.solve_member(data, r, comp, template)
                            if pointer > 0:
                                pointer -= 1
                            if comp == None or comp.kind.is_invalid():
                                ret = []
                        elif match.group(2) == "[]":
                            # TODO: different index types?
                            comp = r.get_member("operator[]", True)
                            r, template, pointer = self.solve_member(data, r, comp, template)
                            if comp == None or comp.kind.is_invalid():
                                ret = []
                    elif match.group(1) == None and pointer > 0:
                        if (nextm2 == "->" or nextm2 == "[]"):
                            pointer -= 1
                        elif nextm2 == ".":
                            # Trying to dot-complete a pointer, this is invalid
                            # so there can be no completions
                            ret = []
                            r = None
                            break

                    if match.group(1):
                        member = match.group(1)
                        if "[" in member:
                            member = get_base_type(member)
                        if "]" in member:
                            member = member[:member.find("]")]
                        if m2 == " ":
                            function = True
                        member = r.get_member(member, function)
                        r, template, pointer = self.solve_member(data, r, member, template)
                        if r == None and member != None:
                            # This can't be completed as a cursor object isn't returned
                            # from this member
                            ret = []
                        if match.group(2) != "(":
                            tocomplete = match.group(2) + tocomplete
                    m2 = nextm2

                if r != None and not r.kind.is_invalid() and (pointer == 0 or r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL):
                    clazz = extract_class_from_function(data)
                    if clazz == None:
                        clazz = extract_class(data)
                    selfcompletion = clazz == r.spelling
                    comp = cache_completeCursor(self.cache, r)
                    replaces = []
                    if template[1] != None:
                        tempnames = []
                        for child in r.get_children():
                            if child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                                tempnames.append(child.spelling)
                        count = min(len(template[1]), len(tempnames))
                        for i in range(count):
                            s = template[1][i][0]
                            if isinstance(s, cindex.Cursor):
                                s = s.spelling
                            replaces.append((r"(^|,|\(|\d:|\s+)(%s)($|,|\s+|\))" % tempnames[i], r"\1%s\3" % s))
                    if comp:
                        ret = []
                        if r.kind == cindex.CursorKind.OBJC_INTERFACE_DECL:
                            isStatic = var == None
                            if m2 == ".":
                                for c in comp[0]:
                                    add = True
                                    if c.cursor.kind == cindex.CursorKind.OBJC_IVAR_DECL:
                                        continue
                                    for child in c.cursor.get_children():
                                        if child.kind == cindex.CursorKind.PARM_DECL:
                                            add = False
                                            break
                                    if add:
                                        ret.append((c.display, c.insert))
                            elif m2 == "->":
                                for c in comp[0]:
                                    if c.cursor.kind != cindex.CursorKind.OBJC_IVAR_DECL:
                                        continue
                                    ret.append((c.display, c.insert))
                            else:
                                for c in comp[0]:
                                    if c.static == isStatic and c.cursor.kind != cindex.CursorKind.OBJC_IVAR_DECL:
                                        ret.append((c.display, c.insert))
                        else:
                            for c in comp[0]:
                                if not c.static and c.cursor.kind != cindex.CursorKind.ENUM_CONSTANT_DECL and \
                                        c.cursor.kind != cindex.CursorKind.ENUM_DECL and \
                                        c.cursor.kind != cindex.CursorKind.TYPEDEF_DECL and \
                                        c.cursor.kind != cindex.CursorKind.CLASS_DECL and \
                                        c.cursor.kind != cindex.CursorKind.STRUCT_DECL and \
                                        c.cursor.kind != cindex.CursorKind.CLASS_TEMPLATE and \
                                        (c.access == cindex.CXXAccessSpecifier.PUBLIC or \
                                            (selfcompletion and not (c.baseclass and c.access == cindex.CXXAccessSpecifier.PRIVATE))):
                                    disp = c.display
                                    ins = c.insert
                                    for r in replaces:
                                        disp = re.sub(r[0], r[1], disp)
                                        ins = re.sub(r[0], r[1], ins)
                                    add = (disp, ins)
                                    ret.append(add)
            ret = self.filter(ret)
            return remove_duplicates(ret)
        else:
            constr = re.search(r"(^|\W)new\s+$", before) != None
            cached_results = cache_complete_startswith(self.cache, bencode(prefix))
            if cached_results:
                ret = [(x.display, x.insert) for x in cached_results[0]]
            variables = extract_variables(data) if not constr else []
            var = [("%s\t%s" % (v[1], re.sub(r"(^|\b)\s*static\s+", "", v[0])), v[1]) for v in variables]
            if len(var) and ret == None:
                ret = []
            for v in var:
                if v[1].startswith(prefix):
                    ret.append(v)
            clazz = extract_class_from_function(data)
            if clazz == None:
                clazz = extract_class(data)
            if clazz != None:
                c = self.find_type(data, clazz)
                if c != None and not c.kind.is_invalid():
                    comp = cache_completeCursor(self.cache, c)
                    if comp:
                        for c in comp[0]:
                            if not c.static and \
                                    not (c.baseclass and c.access == cindex.CXXAccessSpecifier.PRIVATE):
                                add = (c.display, c.insert)
                                ret.append(add)
            namespaces = extract_used_namespaces(data)
            ns = extract_namespace(data)
            if ns:
                namespaces.append(ns)
            for ns in namespaces:
                ns = ns.split("::")
                add = self.complete_namespace(ns)
                if add:
                    ret.extend(add)
            ret = self.filter(ret, constr)
        return remove_duplicates(ret)

    def clangcomplete(self, filename, row, col, unsaved_files, membercomp):
        ret = None
        unsaved = None
        if len(unsaved_files):
            unsaved = (cindex._CXUnsavedFile * len(unsaved_files))()
            for i, (name, value) in enumerate(unsaved_files):
                if not isinstance(value, str):
                    value = value.encode("ascii", "ignore")
                value = bencode(value)
                unsaved[i].name = bencode(name)
                unsaved[i].contents = value
                unsaved[i].length = len(value)
        comp = cache_clangComplete(self.cache, bencode(filename), row, col, unsaved, len(unsaved_files), membercomp)

        if comp:
            ret = [(c.display, c.insert) for c in comp[0]]
        return ret

def format_cursor(cursor):
    return "%s:%d:%d" % (cursor.location.file.name, cursor.location.line,
                         cursor.location.column)

def get_cursor_spelling(cursor):
    cursor_spelling = None
    if cursor != None:
        cursor_spelling = cursor.spelling or cursor.displayname
        cursor_spelling = re.sub(r"^(enum\s+|(class|struct)\s+(\w+::)*)", "", cursor_spelling)
    return cursor_spelling

searchcache = {}

class ExtensiveSearch:

    def quickpanel_extensive_search(self, idx):
        if idx == 0:
            for cpu in range(get_cpu_count()):
                t = threading.Thread(target=self.worker)
                t.start()
            self.queue.put((0, "*/+"))
        elif len(self.options) > 2:
            self.found_callback(self.options[idx][1])

    def __init__(self, cursor, spelling, found_callback, folders, opts, opts_script, name="", impl=True, search_re=None, file_re=None):
        self.name = name
        if impl:
            self.re = re.compile(r"\w+[\*&\s]+(?:\w+::)?(%s\s*\([^;\{]*\))(?:\s*const)?(?=\s*\{)" % re.escape(spelling))
            self.impre = re.compile(r"(\.cpp|\.c|\.cc|\.m|\.mm)$")
        else:
            self.re = re.compile(r"\w+[\*&\s]+(?:\w+::)?(%s\s*\([^;\{]*\))(?:\s*const)?(?=\s*;)" % re.escape(spelling))
            self.impre = re.compile(r"(\.h|\.hpp)$")
        if search_re != None:
            self.re = search_re
        if file_re != None:
            self.impre = file_re
        self.spelling = spelling
        self.folders = folders
        self.opts = opts
        self.opts_script = opts_script
        self.impl = impl
        self.target = ""
        self.cursor = None
        if cursor:
            self.cursor = format_cursor(cursor)
        self.queue = Queue.PriorityQueue()
        self.candidates = Queue.Queue()
        self.lock = threading.RLock()
        self.timer = None
        self.status_count = 0
        self.found_callback = found_callback
        self.options = [["Yes", "Do extensive search"], ["No", "Don't do extensive search"]]
        k = self.key()
        if k in searchcache:
            self.options = [["Redo search", "Redo extensive search"], ["Don't redo", "Don't redo extensive search"]]
            targets = searchcache[k]
            if isinstance(targets, str):
                # An exact match is known, we're done here
                found_callback(targets)
                return
            elif targets != None:
                self.options.extend(targets)
        display_user_selection(self.options, self.quickpanel_extensive_search)

    def key(self):
        return str((self.cursor, self.spelling, self.impre.pattern, self.re.pattern, self.impl, str(self.folders)))

    def done(self):
        cache = None
        if len(self.target) > 0:
            cache = self.target
        elif not self.candidates.empty():
            cache = []
            while not self.candidates.empty():
                name, function, line, column = self.candidates.get()
                pos = "%s:%d:%d" % (name, line, column)
                cache.append([function, pos])
                self.candidates.task_done()
        searchcache[self.key()] = cache
        self.found_callback(cache)

    def do_message(self):
        try:
            self.lock.acquire()
            run_in_main_thread(lambda: status_message(self.status))
            self.status_count = 0
            self.timer = None
        finally:
            self.lock.release()

    def set_status(self, message):
        try:
            self.lock.acquire()
            self.status = message
            if self.timer:
                self.timer.cancel()
                self.timer = None
            self.status_count += 1
            if self.status_count == 30:
                self.do_message()
            else:
                self.timer = threading.Timer(0.1, self.do_message)
        finally:
            self.lock.release()

    def worker(self):
        try:
            while len(self.target) == 0:
                prio, name = self.queue.get(timeout=60)
                if name == "*/+":
                    run_in_main_thread(lambda: status_message("Searching for %s..." % ("implementation" if self.impl else "definition")))
                    name = os.path.basename(self.name)
                    for folder in self.folders:
                        for dirpath, dirnames, filenames in os.walk(folder):
                            for filename in filenames:
                                full_path = os.path.join(dirpath, filename)
                                ok = not "./src/build" in full_path and not "\\src\\build" in full_path
                                if not ok:
                                    full_path = os.path.abspath(full_path)
                                    ok = not "SublimeClang" in full_path and not "Y:\\src\\build" in full_path
                                if ok and self.impre.search(filename) != None:
                                    score = 1000
                                    for i in range(min(len(filename), len(name))):
                                        if filename[i] == name[i]:
                                            score -= 1
                                        else:
                                            break
                                    self.queue.put((score, full_path))
                    for i in range(get_cpu_count()-1):
                        self.queue.put((1001, "*/+++"))

                    self.queue.put((1010, "*/++"))
                    self.queue.task_done()
                    continue
                elif name == "*/++":
                    run_in_main_thread(self.done)
                    break
                elif name == "*/+++":
                    self.queue.task_done()
                    break

                remove = tuCache.get_status(name) == TranslationUnitCache.STATUS_NOT_IN_CACHE
                fine_search = not remove

                self.set_status("Searching %s" % name)

                # try a regex search first
                f = open(name, "r")
                data = f.read()
                f.close()
                fine_cands = []
                for match in self.re.finditer(data):
                    fine_search = True
                    loc = match.start()
                    for i in range(len(match.groups())+1):
                        m = match.group(i)
                        if self.spelling in m:
                            loc = match.start(i)

                    line, column = get_line_and_column_from_offset(data, loc)
                    fine_cands.append((name, line, column))
                    self.candidates.put((name, match.group(0), line, column))

                if fine_search and self.cursor and self.impl:
                    tu2 = tuCache.get_translation_unit(name, self.opts, self.opts_script)
                    if tu2 != None:
                        tu2.lock()
                        try:
                            for cand in fine_cands:
                                cursor2 = cindex.Cursor.get(
                                        tu2.var, cand[0],
                                        cand[1],
                                        cand[2])
                                if cursor2 != None:
                                    d = cursor2.get_canonical_cursor()
                                    if d != None and cursor2 != d:
                                        if format_cursor(d) == self.cursor:
                                            self.target = format_cursor(cursor2)
                                            run_in_main_thread(self.done)
                                            break
                        finally:
                            tu2.unlock()
                        if remove:
                            tuCache.remove(name)
                self.queue.task_done()
        except Queue.Empty as e:
            pass
        except:
            import traceback
            traceback.print_exc()


class LockedTranslationUnit(LockedVariable):
    def __init__(self, var, fn):
        LockedVariable.__init__(self, var)
        self.cache = Cache(var, fn)
        self.fn = fn

    def quickpanel_format(self, cursor):
        return ["%s::%s" % (cursor.get_semantic_parent().spelling,
                            cursor.displayname), format_cursor(cursor)]

    def get_impdef_prep(self, data, offset):
        row, col = get_line_and_column_from_offset(data, offset)
        cursor = cindex.Cursor.get(self.var, self.fn,
                                       row, col)
        cursor_spelling = get_cursor_spelling(cursor)
        word_under_cursor = extract_word_at_offset(data, offset)
        if word_under_cursor == "" and cursor != None:
            # Allow a parenthesis, brackets and some other non-name characters right after the name
            match = re.search(r"(\w+)[\(\[\&\+\-\*\/]*$", extract_line_until_offset(data, offset))
            if match:
                word_under_cursor = match.group(1)
        return cursor, cursor_spelling, word_under_cursor

    def get_implementation(self, data, offset, found_callback, folders):
        target = None
        try:
            self.lock()
            self.var.reparse([(self.fn, data)])
            cursor, cursor_spelling, word_under_cursor = self.get_impdef_prep(data, offset)
            if len(word_under_cursor) == 0:
                found_callback(None)
                return
            if cursor == None or cursor.kind.is_invalid() or cursor_spelling != word_under_cursor:
                if cursor == None or cursor.kind.is_invalid():
                    cursor = None
                ExtensiveSearch(cursor, word_under_cursor, found_callback, folders, self.opts, self.opts_script)
                return
            d = cursor.get_definition()
            if d != None and cursor != d:
                target = format_cursor(d)
            elif d != None and cursor == d and \
                    (cursor.kind == cindex.CursorKind.VAR_DECL or \
                    cursor.kind == cindex.CursorKind.PARM_DECL or \
                    cursor.kind == cindex.CursorKind.FIELD_DECL):
                for child in cursor.get_children():
                    if child.kind == cindex.CursorKind.TYPE_REF:
                        d = child.get_definition()
                        if d != None:
                            target = format_cursor(d)
                        break
            elif cursor.kind == cindex.CursorKind.CLASS_DECL:
                for child in cursor.get_children():
                    if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                        d = child.get_definition()
                        if d != None:
                            target = format_cursor(d)
            elif d == None:
                if cursor.kind == cindex.CursorKind.DECL_REF_EXPR or \
                        cursor.kind == cindex.CursorKind.MEMBER_REF_EXPR or \
                        cursor.kind == cindex.CursorKind.CALL_EXPR:
                    cursor = cursor.get_reference()

                if cursor.kind == cindex.CursorKind.CXX_METHOD or \
                        cursor.kind == cindex.CursorKind.FUNCTION_DECL or \
                        cursor.kind == cindex.CursorKind.CONSTRUCTOR or \
                        cursor.kind == cindex.CursorKind.DESTRUCTOR:
                    f = cursor.location.file.name
                    if f.endswith(".h"):
                        endings = ["cpp", "c", "cc", "m", "mm"]
                        for ending in endings:
                            f = "%s.%s" % (f[:f.rfind(".")], ending)
                            if f != self.fn and os.access(f, os.R_OK):
                                tu2 = tuCache.get_translation_unit(f, self.opts, self.opts_script)
                                if tu2 == None:
                                    continue
                                tu2.lock()
                                try:
                                    cursor2 = cindex.Cursor.get(
                                            tu2.var, cursor.location.file.name,
                                            cursor.location.line,
                                            cursor.location.column)
                                    if cursor2 != None:
                                        d = cursor2.get_definition()
                                        if d != None and cursor2 != d:
                                            target = format_cursor(d)
                                            break
                                finally:
                                    tu2.unlock()
                    if not target:
                        ExtensiveSearch(cursor, word_under_cursor, found_callback, folders, self.opts, self.opts_script)
                        return
            else:
                target = format_cursor(d)
        finally:
            self.unlock()
        found_callback(target)

    def get_definition(self, data, offset, found_callback, folders):
        target = None
        try:
            self.lock()
            self.var.reparse([(self.fn, data)])
            cursor, cursor_spelling, word_under_cursor = self.get_impdef_prep(data, offset)
            if len(word_under_cursor) == 0:
                found_callback(None)
                return
            ref = cursor.get_reference()
            target = None

            if ref != None:
                target = format_cursor(ref)
            elif cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
                f = cursor.get_included_file()
                if not f is None:
                    target = f.name
        finally:
            self.unlock()

        found_callback(target)



class TranslationUnitCache(Worker):
    STATUS_PARSING      = 1
    STATUS_REPARSING    = 2
    STATUS_READY        = 3
    STATUS_NOT_IN_CACHE = 4



    def __init__(self):
        workerthreadcount = get_setting("worker_threadcount", -1)
        self.as_super = super(TranslationUnitCache, self)
        self.as_super.__init__(workerthreadcount)
        self.translationUnits = LockedVariable({})
        self.parsingList = LockedVariable([])
        self.busyList = LockedVariable([])
        self.index_parse_options = 13
        self.index = None
        self.debug_options = False
        self.__options_cache = LockedVariable({})

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
        if on_done != None:
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
        if on_done != None:
            run_in_main_thread(on_done)

    def task_clear(self, data):
        tus = self.translationUnits.lock()
        try:
            tus.clear()
            searchcache.clear()
        finally:
            self.translationUnits.unlock()
        cache = self.__options_cache.lock()
        try:
            cache.clear()
        finally:
            self.__options_cache.unlock()

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
            cache = self.__options_cache.lock()
            try:
                if data in cache:
                    del cache[data]
            finally:
                self.__options_cache.unlock()
        finally:
            self.remove_busy(data)

    def reparse(self, view, filename, unsaved_files=[], on_done=None):
        ret = False
        pl = self.parsingList.lock()
        try:
            if filename not in pl:
                ret = True
                pl.append(filename)
                self.tasks.put((
                    self.task_reparse,
                    (filename, self.get_opts(view), self.get_opts_script(view), unsaved_files, on_done)))
        finally:
            self.parsingList.unlock()
        return ret

    def add_ex(self, filename, opts, opts_script, on_done=None):
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        try:
            if filename not in tu and filename not in pl:
                pl.append(filename)
                self.tasks.put((
                    self.task_parse,
                    (filename, opts, opts_script, on_done)))
        finally:
            self.translationUnits.unlock()
            self.parsingList.unlock()

    def add(self, view, filename, on_done=None):
        ret = False
        tu = self.translationUnits.lock()
        pl = self.parsingList.lock()
        try:
            if filename not in tu and filename not in pl:
                ret = True
                opts = self.get_opts(view)
                opts_script = self.get_opts_script(view)
                pl.append(filename)
                self.tasks.put((
                    self.task_parse,
                    (filename, opts, opts_script, on_done)))
        finally:
            self.translationUnits.unlock()
            self.parsingList.unlock()
        return ret

    def get_opts_script(self, view):
        return expand_path(get_setting("options_script", "", view), view.window())

    def check_opts(self, view):
        key = view.file_name()
        opts = get_setting("options", [], view)
        cache = self.__options_cache.lock()
        try:
            if opts != cache[key][0]:
                view.settings().clear_on_change("sublimeclang.opts")
                del cache[key]
        except KeyError:
            view.settings().clear_on_change("sublimeclang.opts")
        finally:
            self.__options_cache.unlock()

    def get_opts(self, view):
        key = view.file_name()
        cache = self.__options_cache.lock()
        try:
            if key in cache:
                return list(cache[key][1])
        finally:
            self.__options_cache.unlock()

        opts = get_path_setting("options", [], view)
        if not get_setting("dont_prepend_clang_includes", False, view):
            opts.insert(0, "-I%s/clang/include" % scriptpath)
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
            if language in additional_language_options:
                opts.extend(additional_language_options[language] or [])
        self.debug_options = get_setting("debug_options", False)
        self.index_parse_options = get_setting("index_parse_options", 13, view)
        if view.window() != None:
            # At startup it's possible that the window is None and thus path expansion
            # might be wrong.
            cache = self.__options_cache.lock()
            try:
                cache[key] = (get_setting("options", [], view), opts)
            finally:
                self.__options_cache.unlock()
                view.settings().add_on_change("sublimeclang.opts", lambda: run_in_main_thread(lambda: self.check_opts(view)))
        return list(opts)

    def get_translation_unit(self, filename, opts=[], opts_script=None, unsaved_files=[]):
        if self.index == None:
            self.index = cindex.Index.create()
        tu = None
        tus = self.translationUnits.lock()
        if filename not in tus:
            self.translationUnits.unlock()
            pre_script_opts = list(opts)
            opts2 = []
            for option in opts:
                opts2.extend(complete_path(option))
            opts = opts2

            if opts_script:
                # shlex.split barfs if fed with an unicode strings
                args = shlex.split(sencode(opts_script)) + [filename]
                process = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                output = process.communicate()
                if process.returncode:
                    print("The options_script failed with code [%s]" % process.returncode)
                    print(output[1])
                else:
                    opts += shlex.split(bdecode(output[0]))

            if self.debug_options:
                print("Will compile file %s with the following options:\n%s" % (filename, opts))

            opts.append(filename)
            tu = self.index.parse(None, opts, unsaved_files,
                                  self.index_parse_options)
            if tu != None:
                tu = LockedTranslationUnit(tu, filename)
                tu.opts = pre_script_opts
                tu.opts_script = opts_script
                tus = self.translationUnits.lock()
                tus[filename] = tu
                self.translationUnits.unlock()
            else:
                print("tu is None...")
        else:
            tu = tus[filename]
            recompile = tu.opts != opts or tu.opts_script != opts_script

            if recompile:
                del tus[filename]
            self.translationUnits.unlock()

            if recompile:
                self.set_status("Options change detected. Will recompile %s" % filename)
                self.add_ex(filename, opts, opts_script, None)
        return tu

    def remove(self, filename):
        self.tasks.put((self.task_remove, filename))

    def clear(self):
        self.tasks.put((self.task_clear, None))

tuCache = None
try:
    # Dirty hack for ST3...
    def init_tu():
        global tuCache
        tuCache = TranslationUnitCache()
    are_we_there_yet(init_tu)
except:
    tuCache = TranslationUnitCache()
