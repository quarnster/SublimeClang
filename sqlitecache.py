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

scriptdir = os.path.dirname(os.path.abspath(__file__))
enableCache = True


def createDB(cursor):
    cursor.execute("""create table if not exists source(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""create table if not exists type(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT)""")
    cursor.execute("""create table if not exists dependency(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sourceId INTEGER,
        dependencyId INTEGER,
        FOREIGN KEY(sourceId) REFERENCES source(id),
        FOREIGN KEY(dependencyId) REFERENCES source(id))""")
    cursor.execute("""create table if not exists namespace(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parentId INTEGER,
        name TEXT,
        FOREIGN KEY(parentId) REFERENCES namespace(id)
        )""")
    cursor.execute("""create table if not exists inheritance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classId INTEGER,
        parentId INTEGER)""")
    cursor.execute("""create table if not exists class(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        namespaceId INTEGER,
        definitionSourceId INTEGER,
        definitionLine INTEGER,
        definitionColumn INTEGER,
        name TEXT,
        FOREIGN KEY(namespaceId) REFERENCES namespace(id),
        FOREIGN KEY(definitionSourceId) REFERENCES source(id)
        )""")
    cursor.execute("""create table if not exists member(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classId INTEGER,
        namespaceId INTEGER,
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
        FOREIGN KEY(namespaceId) REFERENCES namespace(id),
        FOREIGN KEY(returnId) REFERENCES class(id),
        FOREIGN KEY(definitionSourceId) REFERENCES source(id),
        FOREIGN KEY(implementationSourceId) REFERENCES source(id),
        FOREIGN KEY(typeId) REFERENCES type(id))
        """
    )


class SQLiteCache:
    def __init__(self):
        self.cache = None
        self.cacheCursor = None
        self.newCache = None

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

    def index(self, cursor):
        start = time.time()

        class IndexData:
            def __init__(self):
                self.count = 0
                self.parents = []
                self.cache = sqlite3.connect(":memory:", check_same_thread=False)
                self.cacheCursor = self.cache.cursor()
                createDB(self.cacheCursor)
                self.namespace = []
                self.classes = []

            def get_namespace_id(self):
                if len(self.namespace) > 0:
                    return data.namespace[-1]
                return "null"

            def get_namespace_id_query(self):
                ns = self.get_namespace_id()
                if ns == "null":
                    return " is null"
                return "=%d" % ns

            def get_source_id(self, source):
                sql = "select id from source where name='%s'" % source
                self.cacheCursor.execute(sql)
                id = self.cacheCursor.fetchone()
                if id == None:
                    self.cacheCursor.execute("insert into source (name) values ('%s')" % source)
                    self.cacheCursor.execute(sql)
                    id = self.cacheCursor.fetchone()
                return id[0]

        def visitor(child, parent, data):
            if child == cindex.Cursor_null():
                return 0

            data.count = data.count + 1
            if data.count > 2000:
                print "returning 0"
                return 0

            while len(data.parents) > 0 and data.parents[-1] != parent:
                oldparent = data.parents.pop()
                #child.dump_self()
                if oldparent.kind == cindex.CursorKind.NAMESPACE:
                    data.namespace.pop()
                elif oldparent.kind == cindex.CursorKind.CLASS_DECL:
                    data.classes.pop()

            recurse = False
            if child.kind == cindex.CursorKind.NAMESPACE:
                sql = "select id from namespace where name='%s' and parentId %s" % (child.spelling, data.get_namespace_id_query())

                #print sql
                data.cacheCursor.execute(sql)
                idx = data.cacheCursor.fetchone()
                if idx == None:
                    sql2 = "insert into namespace (name, parentId) VALUES ('%s', %s)" % (child.spelling, "null" if len(data.namespace) == 0 else data.namespace[-1])
                    data.cacheCursor.execute(sql2)
                    #data.cache.commit()
                    data.cacheCursor.execute(sql)
                    idx = data.cacheCursor.fetchone()
                idx = idx[0]
                data.namespace.append(idx)
                recurse = True
            elif child.kind == cindex.CursorKind.CLASS_DECL:
                sql = "select id from class where name='%s' and namespaceId %s" % (child.spelling, data.get_namespace_id_query())
                idx = data.cacheCursor.fetchone()
                if idx == None:
                    recurse = True
                    sql2 = """insert into class (name, namespaceId,
                                definitionSourceId, definitionLine, definitionColumn) VALUES ('%s', %s, %d, %d, %d)""" % \
                            (child.spelling, data.get_namespace_id(), \
                             data.get_source_id(child.location.file.name), child.location.line, child.location.column)
                    data.cacheCursor.execute(sql2)
                    data.cacheCursor.execute(sql)
                    idx = data.cacheCursor.fetchone()
                    idx = idx[0]
                    data.classes.append(idx)
                else:
                    # TODO: update definition if needed
                    pass
            elif child.kind == cindex.CursorKind.CXX_METHOD or child.kind == cindex.CursorKind.FUNCTION_DECL or child.kind == cindex.CursorKind.FIELD_DECL:
                classId = "null"
                if len(data.classes) > 0:
                    classId = data.classes[-1]
                returnId = "null"  # TODO
                ret = parse_res(child.get_completion_string(), "")
                data.cacheCursor.execute("""select id from member where name='%s' and definitionSourceId=%d and definitionLine=%d and definitionColumn=%d""" % \
                    (child.spelling, data.get_source_id(child.location.file.name), child.location.line, child.location.column))
                if data.cacheCursor.fetchone():
                    # TODO. what?
                    pass
                else:
                    sql = """insert into member (namespaceId, classId, returnId, definitionSourceId, definitionLine, definitionColumn, name, displayText, insertionText) values (%s, %s, %s, %s, %d, %d, '%s', '%s', '%s')""" % \
                        (data.get_namespace_id(), classId, returnId, \
                         data.get_source_id(child.location.file.name), child.location.line, child.location.column, \
                         child.spelling, ret[1], ret[2])
                    data.cacheCursor.execute(sql)

            if recurse:
                data.parents.append(child)
                return 2

            return 1  # continue
        data = IndexData()
        cindex.Cursor_visit(cursor, cindex.Cursor_visit_callback(visitor), data)
        data.cache.commit()
        data.cacheCursor.close()

        end = time.time()
        self.newCache = data.cache
        print "indexing took %s ms" % ((end-start)*1000)

    def test(self, tu, view, line, prefix, locations):
        if self.newCache != None:
            if self.cacheCursor:
                self.cacheCursor.close()
                self.cache.close()
                self.cacheCursor = None
                self.cache = None
            self.cache = self.newCache
            self.cacheCursor = self.cache.cursor()
            self.newCache = None
        if self.cacheCursor == None:
            return []

        start = time.time()
        data = view.substr(sublime.Region(0, locations[0]))
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]
        if re.search("[ \t]+$", before):
            ret = []
            self.cacheCursor.execute("select name from class where namespaceId is null and name like '%s%%'" % prefix)
            for c in self.cacheCursor:
                ret.append(("%s\tclass" % c[0], c[0]))
            self.cacheCursor.execute("select name from namespace where parentId is null and name like '%s%%'" % prefix)
            for n in self.cacheCursor:
                ret.append(("%s\tnamespace" % n[0], n[0]))
            self.cacheCursor.execute("select displayText, insertionText from member where classId is null and namespaceId is null and name like '%s%%'" % prefix)
            members = self.cacheCursor.fetchall()
            if members:
                ret.extend(members)
            return ret
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


#sqlCache = SQLiteCache()
