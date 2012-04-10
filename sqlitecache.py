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
import sqlite3
import os.path
from clang import cindex
import time
import re
import sublime
from common import parse_res
from parsehelp import *
import translationunitcache
import threading

scriptdir = os.path.dirname(os.path.abspath(__file__))
enableCache = True


class SQLiteCache:
    def __init__(self):
        self.createDB()
        self.cacheCursor = None
        self.cache = None
        self.tuCache = translationunitcache.TranslationUnitCache()

    def createDB(self):
        self.cache = sqlite3.connect("%s/cache.db" % scriptdir)
        self.cacheCursor = self.cache.cursor()
        self.cacheCursor.execute("""create table if not exists source(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cacheCursor.execute("""create table if not exists type(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT)""")
        self.cacheCursor.execute("""create table if not exists dependency(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sourceId INTEGER,
            dependencyId INTEGER,
            FOREIGN KEY(sourceId) REFERENCES source(id),
            FOREIGN KEY(dependencyId) REFERENCES source(id))""")
        self.cacheCursor.execute("""create table if not exists namespace(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
            )""")
        self.cacheCursor.execute("""create table if not exists inheritance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classId INTEGER,
            parentId INTEGER)""")
        self.cacheCursor.execute("""create table if not exists class(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespaceId INTEGER,
            definitionSourceId INTEGER,
            definitionLine INTEGER,
            definitionColumn INTEGER,
            name TEXT,
            FOREIGN KEY(namespaceId) REFERENCES namespace(id),
            FOREIGN KEY(definitionSourceId) REFERENCES source(id)
            )""")
        self.cacheCursor.execute("""create table if not exists member(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classId INTEGER,
            returnId INTEGER,
            definitionSourceId INTEGER,
            definitionLine INTEGER,
            definitionColumn INTEGER,
            implementationSourceId INTEGER,
            implementationLine INTEGER,
            implementationColumn INTEGER,
            typeId INTEGER,
            name TEXT,
            insertionText TEXT,
            displayText TEXT,
            FOREIGN KEY(classId) REFERENCES class(id),
            FOREIGN KEY(returnId) REFERENCES class(id),
            FOREIGN KEY(definitionSourceId) REFERENCES source(id),
            FOREIGN KEY(implementationSourceId) REFERENCES source(id),
            FOREIGN KEY(typeId) REFERENCES type(id))
            """
        )

    """
    def get_type_db_name(self, c2, t=None):
        if t == None:
            t = c2.type
            if c2.kind == cindex.CursorKind.FUNCTION_DECL or c2.kind == cindex.CursorKind.CXX_METHOD:
                t = c2.result_type

        if t.kind == cindex.TypeKind.UNEXPOSED or t.kind == cindex.TypeKind.RECORD:
            return self.cursor_to_db_name(c2)
        elif t.kind == cindex.TypeKind.TYPEDEF:
            return self.get_type_db_name(c2, t.get_canonical())
        elif t.kind == cindex.TypeKind.POINTER:
            pointee = t.get_pointee()
            c3 = pointee.get_declaration()
            if not c3 is None and not c3.kind.is_invalid():
                c2 = c3
                pointee = c2.type
            return self.get_type_db_name(c2, pointee)
        else:
            return t.kind.name

    def get_absolute_path(self, c2):
        c3 = c2.get_lexical_parent()
        add = ""
        while not c3 is None and not c3.kind.is_invalid():
            #print "         %s, %s, %s, %s, %s" % (c3.kind, c3.type.kind, c3.displayname, c3.get_usr(), c3.spelling)
            if len(c3.displayname):
                print "here"
                add += "%s::" % (c3.displayname)
            c3 = c3.get_lexical_parent()
        return add
    """

    """
    def cursor_to_db_name(self, c2):
        print "%s, %s, %s, %s, %s, %s " % (c2.kind, c2.type.kind, c2.result_type.kind, c2.displayname, c2.get_usr(), c2.spelling)
        # if c2.kind == cindex.CursorKind.VAR_DECL:
        #     print c2.spelling
        #     self.dump_cursor(c2.get_definition())
        #     self.dump_cursor(c2.get_reference())
        #     self.dump_cursor(c2.get_canonical_cursor())
        #     self.dump_cursor(c2.get_lexical_parent())
        #     self.dump_cursor(c2.get_semantic_parent())
        if c2.type.kind == cindex.TypeKind.RECORD and not c2.kind == cindex.CursorKind.VAR_DECL:
            return self.get_absolute_path(c2) + c2.spelling
        else:
            ret = ""
            children = c2.get_children()
            for c3 in children:
                add = ""
                #print "child - %s, %s, %s, %s, %s" % (c3.kind, c3.type.kind, c3.displayname, c3.get_usr(), c3.spelling)
                if c3.kind == cindex.CursorKind.NAMESPACE_REF:
                    # The namespace is looked up later instead
                    continue
                elif c3.kind.is_reference():
                    c4 = c3.get_reference()
                    #print "     %s, %s, %s, %s, %s" % (c4.kind, c4.type.kind, c4.displayname, c4.get_usr(), c4.spelling)
                    add = self.get_absolute_path(c4)
                    if c3.kind == cindex.CursorKind.TYPE_REF:
                        add += c4.displayname
                    else:
                        add += c3.displayname
                    if c3.kind == cindex.CursorKind.TEMPLATE_REF:
                        add += "<"
                ret += add
            for c3 in children:
                if c3.kind == cindex.CursorKind.TEMPLATE_REF:
                    if ret[-1] == ">":
                        ret += " "
                    ret += ">"
            return ret

    def recurse(self, cursor, symbol, count=0):
        if cursor is None or cursor.kind.is_invalid() or count > 2:
            return None
        if cursor.kind.is_reference():
            c2 = cursor.get_reference()
            if not c2 is None and not c2.kind.is_invalid() and not c2 == cursor:
                ret = self.recurse(c2, symbol, count+1)
                if not ret is None:
                    return ret
        elif cursor.displayname == symbol and (\
                        cursor.kind == cindex.CursorKind.VAR_DECL or
                        cursor.kind == cindex.CursorKind.FIELD_DECL):
            return cursor
        else:
            for child in cursor.get_children():
                ret = self.recurse(child, symbol, count+1)
                if not ret is None:
                    return ret
        return None

    def backtrack(self, tu, cursor, loc):
        cursor2 = cindex.Cursor.get(tu, loc.file.name, loc.line-1, 1)
        count = 0
        LIMIT = 2
        while (cursor2 is None or cursor2.kind.is_invalid) and count < LIMIT:
            cursor2 = cindex.Cursor.get(tu, loc.file.name, loc.line-1-count-1, 1)
            count += 1
        if cursor2 is None or cursor2.kind.is_invalid():
            cursor2 = None
        return cursor2

    def find_type(self, cursor, symbol, tu=None, count=0):
        type = self.recurse(cursor, symbol)
        if not type is None:
            return type

        # if the type isn't found in the current block of code,
        # try searching in nearby blocks
        RECURSE_DEPTH = 5
        if not tu is None and count < RECURSE_DEPTH:
            cursor2 = self.backtrack(tu, cursor, cursor.extent.start)
            if not cursor2 is None and not cursor2.kind.is_invalid():
                type = self.find_type(cursor2, symbol, tu, count+1)
            if not type is None:
                return type
            cursor2 = self.backtrack(tu, cursor, cursor.extent.end)
            if not cursor2 is None and not cursor2.kind.is_invalid():
                type = self.find_type(cursor2, symbol, tu, count+1)
        return type
    """

    def get_completion_cursors(self, tu, filename, data, before):
        typedef = get_type_definition(data, before)
        if typedef == None:
            return (None, None)
        line, column, typename, var, tocomplete = typedef

        start = time.time()
        type = cindex.Cursor.get(tu, filename, line, column)
        print type.kind
        print type.displayname
        if type is None or type.kind.is_invalid() or type.displayname != var:
            # TODO: should fall back to a cached version of the class
            # If the displayname is wrong, it probably means that the translation unit
            # is out of date.
            return (None, None)
        print "resolving"
        type = type.get_resolved_cursor()
        if type is None or type.kind.is_invalid() or type.kind == cindex.CursorKind.CLASS_TEMPLATE:
            # templates are scary, lets not go there right now
            return (None, None)
        print "base type is:"
        type.dump_self()
        member = None

        end = time.time()
        print "took: %f ms" % ((end-start)*1000)
        count = 0
        while len(tocomplete) and count < 100 and not type is None:
            count += 1
            match = re.search("([^\.\-\(]+)(\(|\.|->)(.*)", tocomplete)
            if match == None:
                break

            tocomplete = match.group(3)
            count = 1
            function = False
            if match.group(2) == "(":
                function = True
                for i in range(len(tocomplete)):
                    if tocomplete[i] == '(':
                        count += 1
                    elif tocomplete[i] == ')':
                        count -= 1
                        if count == 0:
                            tocomplete = tocomplete[i+1:]
                            break
            tocomplete = re.match("(\.|\->)?(.*)", tocomplete).group(2)
            member = type.get_member(match.group(1), function)
            if member is None or member.kind.is_invalid():
                type = None
                break
            type = member.get_returned_cursor()
        if not type is None:
            print "type is"
            type.dump_self()
        return (member, type)

    """
    def walk(self, tu, cursor):
        #print cursor.kind
        #print cursor.displayname
        kind = cursor.kind

        #print "%s, %s, %s" % (cursor.displayname, cursor.kind, cursor.spelling)
        if kind.is_declaration():
            #print "%s, %s, %s" % (child.displayname, child.kind, child.spelling)
            if kind == cindex.CursorKind.FUNCTION_DECL or kind == cindex.CursorKind.FIELD_DECL or \
                        kind == cindex.CursorKind.VAR_DECL or kind == cindex.CursorKind.CXX_METHOD:
                #self.dump(child)
                parent = cursor.get_semantic_parent()
                pstr = ""
                skip = False
                while not parent is None and not parent.kind.is_invalid() and not parent.kind == cindex.CursorKind.UNEXPOSED_DECL:
                    if parent.kind == cindex.CursorKind.CLASS_TEMPLATE:
                        skip = True
                        break
                    #print "parent: %s, %s" % (parent.spelling, parent.kind)
                    pstr = "%s::%s" % (parent.spelling, pstr)
                    parent = parent.get_semantic_parent()
                if skip:
                    return
                t = cursor.type
                if kind == cindex.CursorKind.FUNCTION_DECL or kind == cindex.CursorKind.CXX_METHOD:
                    t = cursor.result_type

                type = self.get_type_db_name(cursor, t)
                print "%s %s, %s -> %s, %s, %s, %s" % (pstr, cursor.spelling, cursor.kind, type, cursor.result_type.kind, cursor.type.kind, None)
            elif kind == cindex.CursorKind.NAMESPACE or kind == cindex.CursorKind.CLASS_DECL:
                print "%s, %s" % (cursor.kind, cursor.spelling)
                for child in cursor.get_children():
                    self.walk(tu, child)
        elif kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
            self.walk(tu, cursor.get_definition())
            #self.dump_cursor(cursor.get_definition())
            #self.dump_cursor(cursor.get_reference())

        # elif kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
        #     self.dump_cursor(cursor.get_canonical_cursor())
        #     self.dump_cursor(cursor.get_semantic_parent())
        #     self.dump_cursor(cursor.get_lexical_parent())
        #     for child in cursor.get_children():
        #         self.dump(child)


    def recache(self, tu):
        start = time.time()
        self.walk(tu, tu.cursor)
        end = time.time()
        print "recache took %f ms" % ((end-start)*1000)

    def walk_file(self, tu, view):
        start = time.time()
        row, col = view.rowcol(view.size())
        line = 0
        cursor = None
        count = 0
        while (cursor is None or cursor.kind.is_invalid()) and line < row:
            line += 1
            #print "line: %d, row: %d" % (line, row)
            cursor = cindex.Cursor.get(tu, view.file_name(), line, 1)
        if cursor is None or cursor.kind.is_invalid():
            return

        sourceLoc = cursor.extent.end

        while True and count < 330:
            if line > row:
                break

            while cursor is None or cursor.kind.is_invalid() and line < row:
                line += 1
                cursor = cindex.Cursor.get(tu, view.file_name(), line, 1)

            if not cursor is None and not cursor.kind.is_invalid():
                sourceLoc = cursor.extent.end
                #print "%s, %s" % (cursor.extent.start, sourceLoc)
                self.walk(tu, cursor)
                line = sourceLoc.line+1
                cursor = cindex.Cursor.get(tu, view.file_name(), line, 1)
            else:
                break
            count += 1
        end = time.time()
        print "took: %f ms" % ((end-start)*1000)
    """

    def complete(self, cursor, prefix, ret):
        for child in cursor.get_children():
            print "%s, %s, %d" % (child.kind, child.displayname, child.availability)
            if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                self.complete(child.get_reference(), prefix, ret)
            elif child.kind == cindex.CursorKind.CXX_ACCESS_SPEC_DECL:
                access = child.get_cxx_access_specifier()
                print "%s, %d, %d, %d" % (access, access.is_public(), access.is_protected(), access.is_private())
                child.dump()
            if not (child.kind == cindex.CursorKind.CXX_METHOD or child.kind == cindex.CursorKind.FIELD_DECL):
                continue
            add, representation, insertion = parse_res(child.get_completion_string(), prefix)
            if add:
                ret.append((representation, insertion))
                print "adding: %s" % (representation)

    def indexthread(self, filename, opts=[]):
        tu = self.tuCache.get_translation_unit(filename, opts)
        tu.lock()

        def visitor(child, parent, data):
            if child == cindex.Cursor_null():
                return 0
            child.dump_self()
            data[0] = data[0] + 1
            if data[0] > 2000:
                print "returning 0"
                return 0
            if child.kind == cindex.CursorKind.FUNCTION_DECL:
                return 2
            return 1  # continue
        cindex.Cursor_visit(tu.var.cursor, cindex.Cursor_visit_callback(visitor), [0])
        tu.unlock()

    def index(self, view):
        t = threading.Thread(target=self.indexthread, args=(view.file_name(), self.tuCache.get_opts(view),))
        t.start()

    def test(self, tu, view, line, prefix, locations):
        self.index(view)
        #self.walk(tu.cursor)

        start = time.time()
        data = view.substr(sublime.Region(0, locations[0]))
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]
        print before
        if re.search("[ \t]+$", before):
            before = ""
        elif re.search("([^ \t]+)(\.|\->)$", before):
            row, col = view.rowcol(view.sel()[0].a)
            member_cursor, type_cursor = self.get_completion_cursors(tu, view.file_name(), data, before)
            if not type_cursor is None and not type_cursor.kind.is_invalid() and \
                            not type_cursor.kind == cindex.CursorKind.CLASS_TEMPLATE:
                ret = []
                self.complete(type_cursor, prefix, ret)
                end = time.time()
                print "%f ms" % ((end-start)*1000)
                return sorted(ret)
            else:
                return None
        return None


sqlCache = SQLiteCache()

