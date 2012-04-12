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

    def get_final_type(self, lookup_function, lookup_data, tocomplete):
        count = 0
        while len(tocomplete) and count < 100:
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
            if not lookup_function(lookup_data, match.group(1), function):
                return

    def lookup_member(self, data, name, function):
        data.member = data.type.get_member(name, function)
        if data.member is None or data.member.kind.is_invalid():
            data.type = None
            return False
        data.type = data.member.get_returned_cursor()
        if data.type is None:
            return False
        return True

    def lookup_sql(self, data, name, function):
        sql = "select returnId from member where classId=%d and namespaceId %s and name='%s'" % (data.classId, data.namespace, name)
        self.cacheCursor.execute(sql)
        ret = self.cacheCursor.fetchone()
        if ret == None:
            self.cacheCursor.execute("select parentId from inheritance where classId=%d" % data.classId)

            parents = self.cacheCursor.fetchall()
            if parents != None:
                for id in parents:
                    data.classId = id[0]
                    if self.lookup_sql(data, name, function):
                        return True
            data.classId = -1
            return False
        data.classId = ret[0]
        return True

    def complete_cursors(self, tu, filename, data, before, prefix):
        typedef = get_type_definition(data, before)
        if typedef == None:
            return None
        line, column, typename, var, tocomplete = typedef
        start = time.time()
        type = cindex.Cursor.get(tu, filename, line, column)
        print type.kind
        print type.displayname
        if type is None or type.kind.is_invalid() or type.displayname != var:
            return None
        print "resolving"
        type = type.get_resolved_cursor()
        if type is None or type.kind.is_invalid() or type.kind == cindex.CursorKind.CLASS_TEMPLATE:
            # templates are scary, lets not go there right now
            return None
        print "base type is:"
        type.dump_self()

        class Temp:
            def __init__(self):
                self.type = None
                self.member = None
        data = Temp()
        data.type = type
        self.get_final_type(self.lookup_member, data, tocomplete)
        type = data.type
        end = time.time()
        print "took: %f ms" % ((end-start)*1000)

        if not type is None:
            print "type is"
            type.dump_self()
        if not type is None and not type.kind.is_invalid() and \
                        not type.kind == cindex.CursorKind.CLASS_TEMPLATE:
            ret = []
            self.complete_cursor(type, prefix, ret)
            end = time.time()
            print "%f ms" % ((end-start)*1000)
            return sorted(ret)
        else:
            return None

    def complete_cursor(self, cursor, prefix, ret):
        for child in cursor.get_children():
            print "%s, %s, %d" % (child.kind, child.displayname, child.availability)
            if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                self.complete_cursor(child.get_reference(), prefix, ret)
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

    def complete_sql(self, classid, prefix, ret, parent=False):
        self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and name like '%s%%'" % (classid, prefix))
        members = self.cacheCursor.fetchall()
        if members:
            if parent:
                for member in members:
                    if member not in ret:
                        ret.append(member)
            else:
                ret.extend(members)
        self.cacheCursor.execute("select parentId from inheritance where classId=%d" % classid)
        parents = self.cacheCursor.fetchall()
        if parents != None:
            for parent in parents:
                self.complete_sql(parent[0], prefix, ret, True)

    def complete_members(self, tu, filename, data, before, prefix):
        ret = None
        if tu != None:
            ret = self.complete_cursors(tu, filename, data, before, prefix)
            if ret != None:
                return ret

        typedef = get_type_definition(data, before)
        if typedef == None:
            return None
        line, column, typename, var, tocomplete = typedef

        ns = self.get_namespace_query(extract_namespace(data))
        self.cacheCursor.execute("select id from class where name='%s' and namespaceId %s" % (typename, ns))
        classid = self.cacheCursor.fetchone()
        if classid != None:
            classid = classid[0]

            class Temp:
                def __init__(self):
                    self.classId = -1
                    self.namespace = -1
            data = Temp()
            data.classId = classid
            data.namespace = ns
            self.get_final_type(self.lookup_sql, data, tocomplete)
            ret = []
            classid = data.classId
            if classid != -1:
                self.complete_sql(classid, prefix, ret)
            if len(ret) == 0:
                ret = None
        return ret

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

            def get_namespace_id_query(self, ns=None):
                if ns == None:
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

            def get_or_add_namespace_id(self, spelling, parent=None):
                if parent == None:
                    parent = self.get_namespace_id()
                sql = "select id from namespace where name='%s' and parentId %s" % (spelling, self.get_namespace_id_query(parent))

                self.cacheCursor.execute(sql)
                idx = self.cacheCursor.fetchone()
                if idx == None:
                    sql2 = "insert into namespace (name, parentId) VALUES ('%s', %s)" % (spelling, parent)
                    self.cacheCursor.execute(sql2)
                    self.cacheCursor.execute(sql)
                    idx = self.cacheCursor.fetchone()
                idx = idx[0]
                return idx

            def get_class_id_from_cursor(self, cursor):
                path = []
                c3 = cursor.get_lexical_parent()
                while not c3 is None and not c3.kind.is_invalid():
                    if c3.kind == cindex.CursorKind.NAMESPACE:
                        path.append(c3.spelling)
                    old = c3
                    c3 = c3.get_lexical_parent()
                    if not c3 is None and old == c3:
                        break

                ns = "null"
                for p in path:
                    ns = data.get_or_add_namespace_id(p, ns)
                return data.get_or_add_class_id(cursor, ns)

            def get_or_add_class_id(self, child, ns=None):
                if ns == None:
                    ns = self.get_namespace_id()
                sql = "select id from class where name='%s' and namespaceId %s" % (child.spelling, self.get_namespace_id_query(ns))
                self.cacheCursor.execute(sql)
                idx = self.cacheCursor.fetchone()
                if idx == None:
                    sql2 = """insert into class (name, namespaceId,
                                definitionSourceId, definitionLine, definitionColumn) VALUES ('%s', %s, %d, %d, %d)""" % \
                            (child.spelling, ns, \
                             self.get_source_id(child.location.file.name), child.location.line, child.location.column)
                    self.cacheCursor.execute(sql2)
                    self.cacheCursor.execute(sql)
                    idx = self.cacheCursor.fetchone()
                return idx[0]

        def visitor(child, parent, data):
            if child == cindex.Cursor_null():
                return 0

            data.count = data.count + 1
            while len(data.parents) > 0 and data.parents[-1] != parent:
                oldparent = data.parents.pop()
                #child.dump_self()
                if oldparent.kind == cindex.CursorKind.NAMESPACE:
                    data.namespace.pop()
                elif oldparent.kind == cindex.CursorKind.CLASS_DECL:
                    data.classes.pop()

            recurse = False
            if child.kind == cindex.CursorKind.NAMESPACE:
                data.namespace.append(data.get_or_add_namespace_id(child.spelling))
                recurse = True
            elif child.kind == cindex.CursorKind.CLASS_DECL:
                data.classes.append(data.get_or_add_class_id(child))
                recurse = True
            elif child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                chs = child.get_children()
                for c in chs:
                    if c.kind == cindex.CursorKind.TYPE_REF:
                        cl = c.get_reference()
                        if cl.kind == cindex.CursorKind.CLASS_DECL:
                            classId = data.get_class_id_from_cursor(cl)
                            data.cacheCursor.execute("insert into inheritance (classId, parentId) VALUES (%d, %d)" % (data.classes[-1], classId))
            elif child.kind == cindex.CursorKind.CXX_METHOD or child.kind == cindex.CursorKind.FUNCTION_DECL or child.kind == cindex.CursorKind.FIELD_DECL:
                classId = "null"
                if len(data.classes) > 0:
                    classId = data.classes[-1]
                returnId = "null"  # TODO
                returnCursor = child.get_returned_cursor()
                if not returnCursor is None and not returnCursor.kind.is_invalid():
                    returnId = data.get_class_id_from_cursor(returnCursor)
                ret = parse_res(child.get_completion_string(), "")
                sql = """select id from member where name='%s' and definitionSourceId=%d and definitionLine=%d and definitionColumn=%d and classId %s""" % \
                    (child.spelling, data.get_source_id(child.location.file.name), child.location.line, child.location.column, data.get_namespace_id_query(classId))
                data.cacheCursor.execute(sql)
                if data.cacheCursor.fetchone():
                    # TODO. what?
                    pass
                else:
                    sql2 = """insert into member (namespaceId, classId, returnId, definitionSourceId, definitionLine, definitionColumn, name, displayText, insertionText) values (%s, %s, %s, %s, %d, %d, '%s', '%s', '%s')""" % \
                        (data.get_namespace_id(), classId, returnId, \
                         data.get_source_id(child.location.file.name), child.location.line, child.location.column, \
                         child.spelling, ret[1], ret[2])
                    data.cacheCursor.execute(sql2)
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

    def get_namespace_query(self, namespace):
        if len(namespace) == 0:
            return "is null"
        sub = namespace.split("::")
        ns = "is null"
        for sub in sub:
            sql = "select id from namespace where name='%s' and parentId %s" % (sub, ns)
            self.cacheCursor.execute(sql)
            result = self.cacheCursor.fetchone()
            if result == None:
                ns = "is null"
                break
            else:
                ns = "=%s" % result[0]
        return ns

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
        if re.search("[ \t]+$", before) or len(before.strip()) == 0:
            ret = []
            namespaces = extract_used_namespaces(data)
            namespaces.append("null")

            mynamespace = extract_namespace(data)
            if len(mynamespace):
                namespaces.append(mynamespace)
            for namespace in namespaces:
                ns = "is null"
                if namespace != "null":
                    ns = self.get_namespace_query(namespace)
                    if ns == None:
                        # Couldn't find that namespace
                        continue

                self.cacheCursor.execute("select name from class where namespaceId %s and name like '%s%%'" % (ns, prefix))
                for c in self.cacheCursor:
                    ret.append(("%s\tclass" % c[0], c[0]))
                self.cacheCursor.execute("select name from namespace where parentId %s and name like '%s%%'" % (ns, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tnamespace" % n[0], n[0]))
                self.cacheCursor.execute("select displayText, insertionText from member where classId is null and namespaceId %s and name like '%s%%'" % (ns, prefix))
                members = self.cacheCursor.fetchall()
                if members:
                    ret.extend(members)
            myclass = extract_class(data)
            if myclass == None:
                myclass = extract_class_from_function(data)

            if myclass != None:
                ns = self.get_namespace_query(mynamespace)
                self.cacheCursor.execute("select id from class where name='%s' and namespaceId %s" % (myclass, ns))
                classid = self.cacheCursor.fetchone()
                if classid != None:
                    classid = classid[0]

                    self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and namespaceId %s and name like '%s%%'" % (classid, ns, prefix))
                    members = self.cacheCursor.fetchall()
                    if members:
                        ret.extend(members)
            variables = extract_variables(data)
            for var in variables:
                ret.append(("%s\t%s" % (var[1], var[0]), var[1]))
            ret = sorted(ret, key=lambda a: a[1])
            return ret
        elif re.search("([^ \t]+)(\.|\->)$", before):
            return self.complete_members(tu, view.file_name(), data, before, prefix)
        return None
