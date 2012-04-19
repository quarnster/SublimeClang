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
from common import parse_res, Worker
from parsehelp import *
import translationunitcache

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
        typeId INTEGER,
        usr TEXT,
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
        static BOOL,
        access INTEGER,
        usr TEXT,
        FOREIGN KEY(classId) REFERENCES class(id),
        FOREIGN KEY(namespaceId) REFERENCES namespace(id),
        FOREIGN KEY(returnId) REFERENCES class(id),
        FOREIGN KEY(definitionSourceId) REFERENCES source(id),
        FOREIGN KEY(implementationSourceId) REFERENCES source(id),
        FOREIGN KEY(typeId) REFERENCES type(id))
        """
    )
    cursor.execute("""create table if not exists templatearguments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classId INTEGER,
        argumentClassId INTEGER,
        argumentNumber INTEGER,
        FOREIGN KEY(classId) REFERENCES class(id),
        FOREIGN KEY(argumentClassId) REFERENCES class(id))
        """)
    cursor.execute("""create table if not exists templatedmembers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memberId INTEGER,
        argumentClassId INTEGER,
        argumentNumber INTEGER,
        FOREIGN KEY(memberId) REFERENCES member(id),
        FOREIGN KEY(argumentClassId) REFERENCES class(id))
        """)
    cursor.execute("""create table if not exists typedef(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classId INTEGER,
        name TEXT,
        FOREIGN KEY(classId) REFERENCES class(id))""")
    cursor.execute("""create table if not exists toscan(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        priority INTEGER,
        sourceId INTEGER,
        FOREIGN KEY(sourceId) REFERENCES source(id))""")
    cursor.execute("""create unique index if not exists classindex on class (namespaceId, name, typeId, usr)""")
    cursor.execute("""create unique index if not exists memberindex on member(classId, namespaceId, returnId, typeId, name, usr)""")
    cursor.execute("""create unique index if not exists memberindex2 on member(classId, name, usr)""")
    cursor.execute("""create unique index if not exists namespaceindex on namespace(name, parentId)""")
    cursor.execute("""create unique index if not exists sourceindex on source(name)""")


class DbClassType:
    NORMAL = 0
    TEMPLATE_CLASS = 1
    TEMPLATE_TYPE = 2
    RETURNED_COMPLEX_TEMPLATE = 3
    SIMPLE_TYPEDEF = 101
    COMPLEX_TYPEDEF = 102


class Indexer(Worker):
    def __init__(self):
        super(Indexer, self).__init__(threadcount=1)
        self.process_tasks = True

    def cancel(self):
        self.process_tasks = False

    def reset(self):
        self.process_tasks = True

    class IndexData:
        def __init__(self):
            self.count = 0
            self.parents = []
            self.cache = sqlite3.connect("%s/cache.db" % scriptdir, timeout=90, check_same_thread=False)
            self.cacheCursor = self.cache.cursor()
            createDB(self.cacheCursor)
            self.namespace = []
            self.classes = []
            self.access = [cindex.CXXAccessSpecifier.PRIVATE]
            self.templates = []
            self.templateParameter = []
            self.foundFile = False
            self.filename = None
            self.lastFile = None
            self.shouldIndex = True

        def get_namespace_id(self):
            if len(self.namespace) > 0:
                return self.namespace[-1]
            return "null"

        def get_namespace_id_query(self, ns=None):
            if ns == None:
                ns = self.get_namespace_id()
            if ns == "null":
                return " is null"
            return "=%d" % ns

        def get_source_id(self, source):
            if isinstance(source, cindex.Cursor):
                source = "<unknown>" if source.location.file is None else source.location.file.name
            sql = "select id from source where name='%s'" % source
            self.cacheCursor.execute(sql)
            id = self.cacheCursor.fetchone()
            if id == None:
                self.cacheCursor.execute("insert into source (name, lastmodified) values ('%s', CURRENT_TIMESTAMP)" % source)
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
            if cursor is None:
                return "null"
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
                ns = self.get_or_add_namespace_id(p, ns)
            return self.get_or_add_class_id(cursor, ns)

        def get_or_add_class_id(self, child, ns=None):
            typeId = DbClassType.NORMAL
            real = child
            if child.kind == cindex.CursorKind.TYPEDEF_DECL:
                if len(child.get_children()) == 1:
                    typeId = DbClassType.SIMPLE_TYPEDEF
                else:
                    typeId = DbClassType.COMPLEX_TYPEDEF
            elif real.kind == cindex.CursorKind.CLASS_TEMPLATE:
                typeId = DbClassType.TEMPLATE_CLASS
            elif real.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                typeId = DbClassType.TEMPLATE_TYPE
            if ns == None:
                if typeId != DbClassType.TEMPLATE_TYPE:
                    ns = self.get_namespace_id()
                else:
                    ns = "null"
            sql = "select id from class where name='%s' and namespaceId %s and typeId=%d and usr='%s'" % (child.spelling, self.get_namespace_id_query(ns), typeId, child.get_usr())
            self.cacheCursor.execute(sql)
            idx = self.cacheCursor.fetchone()
            if idx == None:
                sql2 = """insert into class (name, namespaceId,
                            definitionSourceId, definitionLine, definitionColumn, typeId, usr) VALUES ('%s', %s, %d, %d, %d, %d, '%s')""" % \
                        (child.spelling, ns, \
                         self.get_source_id(child), child.location.line, child.location.column, typeId, child.get_usr())
                self.cacheCursor.execute(sql2)
                self.cacheCursor.execute(sql)
                idx = self.cacheCursor.fetchone()
            return idx[0]

    def visitor(self, child, parent, data):
        if child == cindex.Cursor_null() or not self.process_tasks:
            return 0

        if child.location.file:
            name = child.location.file.name
            if data.lastFile != name:
                okToIndexNow = True
                if data.filename != None:
                    okToIndexNow = False
                    for dir in data.dirs:
                        if name.startswith(dir):
                            okToIndexNow = True
                            break
                data.cacheCursor.execute("select lastmodified from source where name='%s'" % name)
                modified = data.cacheCursor.fetchone()
                shouldIndex = data.filename == name

                if modified == None:
                    # TODO: compare last indexed timestamp with modification timestamp
                    # TODO: compare last indexed timestamp with modification timestamp of dependencies
                    id = data.get_source_id(name)

                    if not okToIndexNow:
                        data.cacheCursor.execute("insert into toscan(sourceId) values (%d)" % id)
                    shouldIndex = shouldIndex or okToIndexNow
                data.shouldIndex = shouldIndex

                data.lastFile = name
                if data.shouldIndex:
                    self.set_status("Indexing %s" % name)
            if not data.shouldIndex:
                return 1  # skip

        data.count = data.count + 1
        #if data.count > 5000:
        #    return 0
        while len(data.parents) > 0 and data.parents[-1] != parent:
            oldparent = data.parents.pop()
            if oldparent.kind == cindex.CursorKind.NAMESPACE:
                data.namespace.pop()
            elif oldparent.kind == cindex.CursorKind.CLASS_DECL or \
                    oldparent.kind == cindex.CursorKind.ENUM_DECL or \
                    oldparent.kind == cindex.CursorKind.STRUCT_DECL:
                data.classes.pop()
                # TODO: here would be a good place to purge removed
                #       members
            data.access.pop()
            if oldparent.kind == cindex.CursorKind.CLASS_TEMPLATE:
                data.classes.pop()
                data.templates.pop()
                data.templateParameter.pop()
        #child.dump()

        recurse = False
        if child.kind == cindex.CursorKind.NAMESPACE:
            data.namespace.append(data.get_or_add_namespace_id(child.spelling))
            recurse = True
        elif child.kind == cindex.CursorKind.CLASS_TEMPLATE:
            data.classes.append(data.get_or_add_class_id(child))
            data.templates.append(child)
            data.templateParameter.append(0)
            recurse = True
        elif child.kind == cindex.CursorKind.CLASS_DECL or \
                    child.kind == cindex.CursorKind.ENUM_DECL or \
                    child.kind == cindex.CursorKind.STRUCT_DECL:

            data.classes.append(data.get_or_add_class_id(child))
            recurse = True
        elif child.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
            id = data.get_or_add_class_id(child)
            data.cacheCursor.execute("select id from templatearguments where classId=%d and argumentClassId = %d and argumentNumber = %d" % (data.classes[-1], id, data.templateParameter[-1]))
            if data.cacheCursor.fetchone() == None:
                data.cacheCursor.execute("insert into templatearguments (classId, argumentClassId, argumentNumber) VALUES (%d, %d, %d)" % (data.classes[-1], id, data.templateParameter[-1]))
            data.templateParameter[-1] += 1
        elif child.kind == cindex.CursorKind.CXX_ACCESS_SPEC_DECL:
            data.access[-1] = child.get_cxx_access_specifier().kind
        elif child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
            for c in child.get_children():
                if c.kind == cindex.CursorKind.TYPE_REF:
                    cl = c.get_reference()
                    classId = None
                    if cl.kind == cindex.CursorKind.CLASS_DECL:
                        classId = data.get_class_id_from_cursor(cl)
                        data.cacheCursor.execute("insert into inheritance (classId, parentId) VALUES (%d, %d)" % (data.classes[-1], classId))
        elif child.kind == cindex.CursorKind.TYPEDEF_DECL:
            id = data.get_class_id_from_cursor(child)
            children = child.get_children()
            if len(children) == 1:
                c = children[0].get_reference()
                if not c is None:
                    pid = data.get_class_id_from_cursor(c)
                    data.cacheCursor.execute("select id from inheritance where classId=%d and parentId=%d" % (id, pid))
                    if data.cacheCursor.fetchone() == None:
                        data.cacheCursor.execute("insert into inheritance (classId, parentId) values (%d, %d)" % (id, pid))
            elif child.location.file != None:
                # TODO: hack.. mail sent to cfe-dev to ask what to do about it though
                # http://lists.cs.uiuc.edu/pipermail/cfe-dev/2012-April/020838.html
                f = open(child.location.file.name)
                fdata = f.read()[child.extent.start.offset:child.extent.end.offset+1]
                f.close()
                regex = re.search("typedef\s+(.*)\s+(.*);", fdata, re.DOTALL)
                if regex and regex.group(1):
                    try:
                        data.cacheCursor.execute("select id from typedef where classId=%d and name='%s'" % (id, regex.group(1)))
                        ret = data.cacheCursor.fetchone()
                        if ret == None:
                            data.cacheCursor.execute("insert into typedef (classId, name) VALUES (%d, '%s')" % (id, regex.group(1)))
                    except:
                        pass
                # else:
                #     print "failed typedef regex: %s" % (fdata)
        elif child.kind == cindex.CursorKind.CXX_METHOD or \
                child.kind == cindex.CursorKind.FUNCTION_DECL or \
                child.kind == cindex.CursorKind.FIELD_DECL or \
                child.kind == cindex.CursorKind.VAR_DECL or \
                child.kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
            classId = "null"
            if len(data.classes) > 0:
                classId = data.classes[-1]
            elif child.kind == cindex.CursorKind.CXX_METHOD:
                classId = data.get_class_id_from_cursor(child.get_semantic_parent())

            implementation = False
            if child.kind == cindex.CursorKind.CXX_METHOD or \
                    child.kind == cindex.CursorKind.FUNCTION_DECL:
                for c in child.get_children():
                    if c.kind == cindex.CursorKind.COMPOUND_STMT:
                        implementation = True
                        break
            sql = """select id from member where name='%s' and classId %s and usr='%s'""" % \
                (child.spelling, data.get_namespace_id_query(classId), child.get_usr())
            data.cacheCursor.execute(sql)
            memberId = data.cacheCursor.fetchone()
            if memberId:
                if implementation:
                    sql = "update member set implementationSourceId=%d, implementationLine=%d, implementationColumn=%d where id=%d" % (data.get_source_id(child), child.location.line, child.location.column, memberId[0])
                    data.cacheCursor.execute(sql)
                pass
            else:
                returnId = "null"
                returnCursor = child.get_returned_cursor()
                templateCursor = None

                # child.dump_self()
                # for c in child.get_children():
                #     print "   - %s, %s" % (c.spelling, c.kind)
                #     #returnCursor.dump_self()
                if not returnCursor is None and not returnCursor.kind.is_invalid():
                    # if child.spelling == "getTemp":
                    #     child.dump_self()
                    #     for c in child.get_children():
                    #         print "   - %s, %s" % (c.spelling, c.kind)
                    #     returnCursor.dump_self()
                    #if child.spelling == "front":
                    #    returnCursor.dump()
                    if child == returnCursor:
                        if child.location.file != None:
                            children = returnCursor.get_children()
                            templateCount = 0
                            for c in children:
                                if c.kind == cindex.CursorKind.TEMPLATE_REF:
                                    if templateCount == 0:
                                        templateCursor = returnCursor
                                        returnCursor = c.get_reference()
                                    templateCount += 1
                                elif c.kind != cindex.CursorKind.TYPE_REF:
                                    break

                            if templateCount > 1:
                                # TODO: hack... see comment in TYPEDEF_DECL
                                # Means it's a complex template
                                f = open(child.location.file.name)
                                f.seek(child.extent.start.offset)
                                fdata = f.read(child.extent.end.offset-child.extent.start.offset+1)
                                f.close()
                                name = ""
                                if fdata.startswith("template"):
                                    d = collapse_ltgt(collapse_parenthesis(collapse_brackets(fdata)))
                                    regex = re.search("template\\s*<>\\s+((const\s+)?typename\\s+)?(.+?)\\s+([^\\s]+)::", d, re.DOTALL)
                                    if regex == None:
                                        print d
                                        print fdata
                                    else:
                                        name = regex.group(3).strip()
                                        if "<" in name:
                                            regex = re.search("(%s.*?%s)" % (name[:name.find("<")+1], name[name.find(">"):]), fdata, re.DOTALL)
                                            name = regex.group(1)
                                else:
                                    regex = re.search("(.+)\s+(.+);", fdata, re.DOTALL)
                                    name = regex.group(1).strip()
                                #print name

                                sql = "select id from class where namespaceId %s and typeId=%d and name='%s'" % (data.get_namespace_id_query(classId), DbClassType.RETURNED_COMPLEX_TEMPLATE, name)
                                data.cacheCursor.execute(sql)
                                res = data.cacheCursor.fetchone()
                                if res == None:
                                    data.cacheCursor.execute("insert into class (name, namespaceId, typeId) VALUES ('%s', %s, %d)" % (name, classId, DbClassType.RETURNED_COMPLEX_TEMPLATE))
                                    data.cacheCursor.execute(sql)
                                    res = data.cacheCursor.fetchone()
                                returnId = res[0]
                                templateCursor = None
                    if returnId == "null":
                        returnId = data.get_class_id_from_cursor(returnCursor)

                static = False
                if child.kind == cindex.CursorKind.CXX_METHOD:
                    static = child.get_cxxmethod_is_static()
                comp_string = parse_res(child.get_completion_string(), "")
                sql2 = """insert into member (namespaceId, classId, returnId, definitionSourceId, definitionLine, definitionColumn, name, displayText, insertionText, static, access, usr) values (%s, %s, %s, %s, %d, %d, '%s', '%s', '%s', %d, %d, '%s')""" % \
                    (data.get_namespace_id(), classId, returnId, \
                     data.get_source_id(child), child.location.line, child.location.column, \
                     child.spelling, comp_string[1], comp_string[2], static, data.access[-1], child.get_usr())
                data.cacheCursor.execute(sql2)
                if not templateCursor is None:
                    data.cacheCursor.execute(sql)
                    memberId = data.cacheCursor.fetchone()[0]
                    children = templateCursor.get_children()

                    off = 0
                    for i in range(0, len(children)):
                        c = children[i]
                        #c.dump()
                        if c.kind == cindex.CursorKind.PARM_DECL or c.kind == cindex.CursorKind.COMPOUND_STMT:
                            break
                        if c.kind != cindex.CursorKind.TYPE_REF:
                            continue
                        sql2 = "insert into templatedmembers (memberId, argumentClassId, argumentNumber) VALUES (%d, %s, %d)" % (memberId, data.get_class_id_from_cursor(c.get_resolved_cursor()), off)
                        off += 1
                        data.cacheCursor.execute(sql2)
                        #data.cacheCursor.execute(sql)

        # elif child.kind == cindex.CursorKind.CLASS_TEMPLATE or \
        #         child.kind == cindex.CursorKind.FUNCTION_TEMPLATE or \
        #         child.kind == cindex.CursorKind.CXX_ACCESS_SPEC_DECL or \
        #         child.kind == cindex.CursorKind.FUNCTION_TEMPLATE or \
        #         child.kind == cindex.CursorKind.USING_DIRECTIVE or \
        #         child.kind == cindex.CursorKind.USING_DECLARATION or \
        #         child.kind == cindex.CursorKind.CONSTRUCTOR or \
        #         child.kind == cindex.CursorKind.DESTRUCTOR or \
        #         child.kind == cindex.CursorKind.TEMPLATE_REF or \
        #         child.kind == cindex.CursorKind.VAR_DECL or \
        #         child.kind == cindex.CursorKind.TYPE_REF:
        #     pass
        elif child.kind == cindex.CursorKind.UNEXPOSED_DECL:
            # extern "C" for example
            recurse = True
        else:
            #if child.location.file != None:
            #    child.dump_self()
            pass

        if recurse:
            data.access.append(cindex.CXXAccessSpecifier.PRIVATE)
            data.parents.append(child)
            return 2

        return 1  # continue

    def index(self, cursor, filename=None, dirs=[]):
        start = time.time()
        data = Indexer.IndexData()
        data.cursor = cursor
        data.filename = filename
        data.dirs = dirs
        data.cacheCursor.execute("select lastmodified from source where name='%s'" % filename)
        if data.cacheCursor.fetchone() == None:
            # TODO: hack... just to scan the whole translation unit
            data.filename = None
        cindex.Cursor_visit(cursor, cindex.Cursor_visit_callback(self.visitor), data)

        data.cache.commit()
        data.cacheCursor.close()

        end = time.time()
        self.newCache = data.cache
        self.set_status("Indexing translation unit took %s seconds" % (end-start))

    def do_index_tu(self, data):
        if not self.process_tasks:
            return
        tu, filename, dirs = data
        tu.lock()
        self.index(tu.var.cursor, filename, dirs)
        tu.unlock()

    def add_index_tu_task(self, translationUnit, filename, dirs=[]):
        filedir = os.path.dirname(filename)
        if filedir not in dirs:
            dirs.append(filedir)
        self.tasks.put((self.do_index_tu, (translationUnit, filename, dirs)))


indexer = Indexer()


class SQLiteCache:
    def __init__(self):
        self.cache = sqlite3.connect("%s/cache.db" % scriptdir, timeout=0.5, check_same_thread=False)
        self.cacheCursor = self.cache.cursor()
        createDB(self.cacheCursor)

    def clear(self):
        self.cacheCursor.execute("drop table source")
        self.cacheCursor.execute("drop table type")
        self.cacheCursor.execute("drop table dependency")
        self.cacheCursor.execute("drop table namespace")
        self.cacheCursor.execute("drop table inheritance")
        self.cacheCursor.execute("drop table class")
        self.cacheCursor.execute("drop table member")
        self.cacheCursor.execute("drop table templatearguments")
        self.cacheCursor.execute("drop table templatedmembers")
        self.cacheCursor.execute("drop table typedef")
        createDB(self.cacheCursor)

    def get_final_type(self, lookup_function, lookup_data, tocomplete):
        count = 0
        while len(tocomplete) and count < 100:
            count += 1
            match = re.search("([^\.\-\(]+)?(\(|\.|->)(.*)", tocomplete)
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
            left = re.match("(\.|\->)?(.*)", tocomplete)
            tocomplete = left.group(2)
            if left.group(1) != None:
                tocomplete = left.group(1) + tocomplete
            if not lookup_function(lookup_data, match.group(1), match.group(2), function):
                return

    def lookup(self, data, args):
        print data.ret, args
        sql = "select id, typeId, name from class where id=%d" % data.ret[0]
        self.cacheCursor.execute(sql)
        res = self.cacheCursor.fetchone()
        print sql, res
        if res != None and res[1] != DbClassType.NORMAL:
            if res[1] == DbClassType.TEMPLATE_CLASS:
                sql = "select argumentClassId, argumentNumber from templatedmembers where memberId=%d order by argumentNumber" % data.ret[1]
                self.cacheCursor.execute(sql)
                res = self.cacheCursor.fetchall()
                print sql, res
                data.templateargs = [(x[0], None) for x in res]
            elif res[1] == DbClassType.TEMPLATE_TYPE:
                if data.templateargs != None:
                    tempargs = data.templateargs
                    print tempargs
                    sql = "select argumentNumber from templatearguments where classId=%d and argumentClassId=%d order by argumentNumber" % (data.classId, data.ret[0])
                    sql = "select argumentNumber,argumentClassId from templatearguments where classId=%d order by argumentNumber" % (data.classId)
                    self.cacheCursor.execute(sql)
                    idx = 0
                    for c in self.cacheCursor:
                        idx = c[0]
                        if idx >= len(tempargs):
                            idx-=1
                            break
                        print "swapping %d for %d" % (data.ret[0], tempargs[idx][0])
                        data.classId = tempargs[idx][0]
                        data.ret = (data.classId, 0)
                    data.templateargs = tempargs[idx][1]
                    #data.classId = tempargs[idx][0]

                    return self.lookup(data, args)
                else:
                    sql = "select argumentClassId, argumentNumber from templatedmembers where memberId=%d order by argumentNumber" % data.ret[1]
                    self.cacheCursor.execute(sql)
                    res = self.cacheCursor.fetchall()
                    print sql, res
                    data.templateargs = [x[0] for x in res]
                    print "down here... Will break"
                    print data.templateargs
            elif res[1] == DbClassType.SIMPLE_TYPEDEF:
                sql = "select parentId from inheritance where classId=%d" % data.ret[0]
                self.cacheCursor.execute(sql)
                data.ret = (self.cacheCursor.fetchone()[0], data.ret[1])
                return self.lookup(data, data.templateargs)
            elif res[1] == DbClassType.COMPLEX_TYPEDEF:
                sql = "select name from typedef where classId=%d" % (data.ret[0])
                self.cacheCursor.execute(sql)
                name = self.cacheCursor.fetchone()[0]
                tmp = solve_template(name)
                print sql, name, tmp
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
                print "resolved to2: %d, %s" % (classId, data.templateargs)
                data.ret = (classId, data.ret[1])
                return self.lookup(data, newargs)  # Proper memberId?
            elif res[1] == DbClassType.RETURNED_COMPLEX_TEMPLATE:
                tmp = solve_template(res[2])
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
                print "resolved to3: %d, %s" % (classId, newargs)
                data.ret = (classId, data.ret[1])
                data.templateargs = newargs
                return self.lookup(data, newargs)
        data.classId = data.ret[0]
        return True

    def lookup_sql(self, data, name, pointer, function):
        if name != None:
            sql = "select returnId, id from member where classId=%d and name='%s' and access <=%d" % (data.classId, name, data.access)
            self.cacheCursor.execute(sql)
            data.ret = self.cacheCursor.fetchone()
        elif pointer == "->":
            sql = "select returnId, id from member where classId=%d and name='operator->' and access <=%d" % (data.classId, data.access)
            self.cacheCursor.execute(sql)
            ret = self.cacheCursor.fetchone()
            if ret == None:
                return True
            data.ret = ret
        else:
            return True
        print sql, data.ret
        if data.ret == None or data.ret[0] == None:
            self.cacheCursor.execute("select parentId from inheritance where classId=%d" % data.classId)

            parents = self.cacheCursor.fetchall()
            if parents != None:
                for id in parents:
                    data.classId = id[0]
                    if data.access > cindex.CXXAccessSpecifier.PROTECTED:
                        # Only have access to the protected
                        # level in inheritance
                        data.access = cindex.CXXAccessSpecifier.PROTECTED
                    if self.lookup_sql(data, name, pointer, function):
                        return True
            data.classId = -1
            return False
        else:
            return self.lookup(data, data.templateargs)
        return True

    def complete_sql(self, classid, prefix, ret, parent=False, access=cindex.CXXAccessSpecifier.PUBLIC):
        self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and name like '%s%%' and static=0 and access<=%d" % (classid, prefix, access))
        members = self.cacheCursor.fetchall()
        print members
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

    def get_namespace_id(self, data, namespaces):
        ns = data.split("::")
        if len(ns) == 0:
            return None
        if ns[0].strip() == "":
            return None
        ret = None
        parent = "is null"
        for name in namespaces:
            self.cacheCursor.execute("select id from namespace where parentId %s and name='%s'" % (parent, ns[0]))
            id = self.cacheCursor.fetchone()
            if id != None:
                parent = "=%d" % id[0]
                ret = id[0]
                break
        ns.pop(0)

        while len(ns) > 0:
            self.cacheCursor.execute("select id from namespace where parentId %s and name='%s'" % (parent, ns[0]))
            id = self.cacheCursor.fetchone()
            if id != None:
                parent = "=%d" % id[0]
                ret = id[0]
            else:
                return None
            ns.pop(0)
        return ret

    def resolve_template_class_ids(self, template, namespaces):
        name, args = template
        print "args: %s" % args
        id = -1
        ns = name.split("::")
        name = ns.pop()
        used_ns = namespaces
        ns = self.get_namespace_id("::".join(ns), namespaces)
        print used_ns
        if ns != None:
            used_ns = ["=%d" % ns]

        for ns in used_ns:
            if ns == None:
                continue
            sql = "select id, typeId from class where name='%s' and namespaceId %s and (typeId=%d or typeId>=%d)" % (name, ns, DbClassType.NORMAL if args == None else DbClassType.TEMPLATE_CLASS, DbClassType.SIMPLE_TYPEDEF)
            self.cacheCursor.execute(sql)
            ret = self.cacheCursor.fetchone()
            if ret == None and args == None:
                sql = "select id, typeId from class where name='%s' and namespaceId %s and typeId=%d" % (name, ns, DbClassType.TEMPLATE_TYPE)
                self.cacheCursor.execute(sql)
                ret = self.cacheCursor.fetchone()

            print sql, ret
            if ret != None:
                id = ret[0]
                if ret[1] == DbClassType.COMPLEX_TYPEDEF:
                    sql = "select name from typedef where classId=%d" % (id)
                    self.cacheCursor.execute(sql)
                    tmp = solve_template(self.cacheCursor.fetchone()[0])
                    print sql, tmp
                    classId, newargs = self.resolve_template_class_ids(tmp, namespaces)
                    print "resolved to1: %d, %s" % (classId, newargs)
                    return classId, newargs
                elif ret[1] == DbClassType.SIMPLE_TYPEDEF:
                    sql = "select parentId from inheritance where classId=%d" % id
                    self.cacheCursor.execute(sql)
                    classId = self.cacheCursor.fetchone()[0]
                    print sql, classId
                    return classId, None
                    #return self.resolve_template_class_ids(classId, template, namespaces)
                break
        if args != None:
            for i in range(len(args)):
                args[i] = self.resolve_template_class_ids(args[i], namespaces)

        return id, args

    def resolve_namespace_ids(self, namespaces):
        namespaceids = []
        for namespace in namespaces:
            namespaceids.append(self.get_namespace_query(namespace))
        return namespaceids

    def resolve_class_id_from_line(self, data, before):
        typedef = get_type_definition(data, before)
        if typedef == None:
            return None
        line, column, typename, var, tocomplete = typedef
        if typename == None and var != None:
            # Try and see if we're in a class and var
            # thus might be a member of "this"
            clazz = extract_class_from_function(data)
            if clazz == None:
                clazz = extract_class(data)
            if clazz != None:
                typename = clazz
                tocomplete = "%s.%s" % (var, tocomplete)
        if typename == None:
            return None

        namespaces = extract_used_namespaces(data)
        namespaces.append("null")
        mynamespace = extract_namespace(data)
        if len(mynamespace):
            namespaces.append(mynamespace)
        namespaces = self.resolve_namespace_ids(namespaces)
        namespaces.append("like '%%'")
        template = solve_template(typename)
        print template
        template = self.resolve_template_class_ids(template, namespaces)
        print template
        classid = template[0]
        if classid != None:
            class Temp:
                def __init__(self):
                    self.classId = -1
                    self.namespace = -1
                    self.access = cindex.CXXAccessSpecifier.PRIVATE
                    self.templateargs = []

                def __str__(self):
                    return "(%d, %d, %d, %s)" % (self.classId, self.namespace, self.access, self.templateargs)
            data = Temp()
            data.classId = classid
            data.namespaces = namespaces
            data.templateargs = template[1]
            print "getting final type: %s, %s" % (data, tocomplete)
            self.get_final_type(self.lookup_sql, data, tocomplete)
            classid = data.classId
            print classid
        return classid

    def complete_members(self, filename, data, before, prefix):
        ret = None
        classid = self.resolve_class_id_from_line(data, before)
        if classid != -1:
            ret = []
            self.complete_sql(classid, prefix, ret)
        return ret

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

    def get_colon_colon_base(self, data, before):
        # What's before :: will be either a class or a namespace,
        # and after it'll be a class, namespace, or class static member
        match = re.search("([^\s]+::)+$", before)
        before = match.group(1)
        tofind = before.split("::")
        first = tofind.pop(0)

        namespaces = extract_used_namespaces(data)
        namespaces.append("null")
        type = None
        id = -1

        mynamespace = extract_namespace(data)
        if len(mynamespace):
            namespaces.append(mynamespace)
        for namespace in namespaces:
            ns = "is null"
            if namespace != "null":
                ns = self.get_namespace_query(namespace)
                if ns == "is null":
                    # Couldn't find that namespace
                    continue
            self.cacheCursor.execute("select id from namespace where parentId %s and name='%s'" % (ns, first))
            id = self.cacheCursor.fetchone()
            print "namespace: ", id, ns, first
            if id != None:
                id = id[0]
                type = "ns"
                break
            self.cacheCursor.execute("select id from class where namespaceId %s and name='%s'" % (ns, first))
            id = self.cacheCursor.fetchone()
            print "class: ", id, ns, first
            if id != None:
                id = id[0]
                type = "class"
                break
        if type == None:
            return type, id
        for item in tofind:
            if len(item) == 0:
                continue
            if type == "ns":
                self.cacheCursor.execute("select id from class where namespaceId= %d and name='%s'" % (id, item))
                newid = self.cacheCursor.fetchone()
                if newid != None:
                    id = newid[0]
                    type = "class"
                    continue
                self.cacheCursor.execute("select id from namespace where parentId= %d and name='%s'" % (id, item))
                newid = self.cacheCursor.fetchone()
                if newid != None:
                    id = newid[0]
                    type = "ns"
                    continue
                type = None
                break
            else:
                print "id, type: %d, %s" % (id, type)
        return type, id

    def complete(self, view, line, prefix, locations):
        data = view.substr(sublime.Region(0, locations[0]))
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        if re.search("::$", before):
            type, id = self.get_colon_colon_base(data, before)
            print type, id

            if not type:
                return None

            if type == "ns":
                ret = []
                self.cacheCursor.execute("select name from class where namespaceId=%d and name like '%s%%'" % (id, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tclass" % n[0], n[0]))
                self.cacheCursor.execute("select name from namespace where parentId= %d and name like '%s%%'" % (id, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tnamespace" % n[0], n[0]))
                type = None
                return ret
            elif type == "class":
                self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and static=1 and name like '%s%%'" % (id, prefix))
                ret = []
                members = self.cacheCursor.fetchall()
                if members:
                    ret.extend(members)
                return ret
            return None
        elif re.search("([^ \t]+)(\.|\->)$", before):
            return self.complete_members(view.file_name(), data, before, prefix)
        else:
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
                    if ns == "is null":
                        # Couldn't find that namespace
                        continue

                self.cacheCursor.execute("select name from class where namespaceId %s and name like '%s%%' and typeId != %d" % (ns, prefix, DbClassType.TEMPLATE_TYPE))
                for c in self.cacheCursor:
                    ret.append(("%s\tclass" % c[0], c[0]))
                self.cacheCursor.execute("select name from namespace where parentId %s and name like '%s%%'" % (ns, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tnamespace" % n[0], n[0]))
                self.cacheCursor.execute("select displayText, insertionText from member where classId is null and namespaceId %s and name like '%s%%'" % (ns, prefix))
                members = self.cacheCursor.fetchall()
                if members:
                    ret.extend(members)
            myclass = extract_class_from_function(data)
            if myclass == None:
                myclass = extract_class(data)

            if myclass != None:
                ns = self.get_namespace_query(mynamespace)
                self.cacheCursor.execute("select id from class where name='%s' and namespaceId %s" % (myclass, ns))
                classid = self.cacheCursor.fetchone()
                if classid != None:
                    classid = classid[0]

                    self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and name like '%s%%'" % (classid, prefix))
                    members = self.cacheCursor.fetchall()
                    if members:
                        ret.extend(members)
                    self.cacheCursor.execute("select parentId from inheritance where classId=%d" % classid)
                    parents = self.cacheCursor.fetchall()
                    if parents != None:
                        for parent in parents:
                            print parent
                            self.cacheCursor.execute("select displayText, insertionText from member where classId=%d and access <=%d and name like '%s%%'" % (parent[0], cindex.CXXAccessSpecifier.PROTECTED, prefix))
                            members = self.cacheCursor.fetchall()
                            print members
                            if members:
                                ret.extend(members)

            variables = extract_variables(data)
            for var in variables:
                ret.append(("%s\t%s" % (var[1], var[0]), var[1]))
            ret = sorted(ret, key=lambda a: a[1])
            return ret
        return None

    def get_inheritance_ids(self, classid, ret):
        self.cacheCursor.execute("select parentId from inheritance where classId=%d" % classid)
        parents = self.cacheCursor.fetchall()
        if parents != None:
            for parent in parents:
                ret.append(parent[0])
                self.get_inheritance_ids(parent[0], ret)

    def goto_def(self, view, columnnames="definitionSourceId, definitionLine, definitionColumn"):
        caret = view.sel()[0].a
        scope = view.scope_name(caret)
        data = view.substr(sublime.Region(0, caret))

        line = view.substr(view.line(caret))
        regex = re.compile("([^\(\\s&*]+$)")
        extended_word = regex.search(view.substr(sublime.Region(view.line(caret).begin(), view.word(caret).end())))
        extended_start = regex.search(view.substr(sublime.Region(view.line(caret).begin(), caret)))
        if extended_start:
            extended_start = extended_start.group(1)
        else:
            extended_start = ""

        if extended_word == None:
            return ""
        extended_word = extended_word.group(1)
        word = view.substr(view.word(caret))

        variables = extract_variables(data)
        if not "function-call" in scope and not "entity.name.function." in scope:
            for type, name in variables:
                if name == word:
                    type = type.replace("*", "\*")
                    pos = caret
                    for match in re.finditer("(%s)\\s*(%s)" % (type, name), data):
                        pos = match.start(2)
                    row, col = view.rowcol(pos)
                    return "%s:%d:%d" % (view.file_name(), row+1, col+1)

        classes = []
        if "." in extended_word or "->" in extended_word:
            extended_start = re.search("(.*)(\.|->)[^-.]*$", extended_start)
            before = "%s%s" % (extended_start.group(1, 2))
            classid = self.resolve_class_id_from_line(data, before)
            if classid != -1:
                classes.append("=%d" % (classid))
                inheritance = []
                self.get_inheritance_ids(classid, inheritance)
                for inh in inheritance:
                    classes.append("=%d" % inh)
            #self.cacheCursor.execute("select name from class where id=%d" % classid)
            #print "resolved name=%s" % self.cacheCursor.fetchone()
        else:
            clazz = extract_class_from_function(data)
            if clazz == None:
                clazz = extract_class(data)

            if clazz:
                self.cacheCursor.execute("select id from class where name='%s'" % clazz)
                for c in self.cacheCursor:
                    classes.append("=%d" % c[0])
                    inheritance = []
                    self.get_inheritance_ids(c[0], inheritance)
                    for inh in inheritance:
                        classes.append("=%d" % inh)
            classes.append(" is null")

        for clazz in classes:
            sql = "select name, %s from member where name='%s' and classId %s" % (columnnames, word, clazz)
            self.cacheCursor.execute(sql)
            res = self.cacheCursor.fetchall()
            print sql, res
            if res:
                # TODO if there are multiple entries
                name, definitionSourceId, line, col = res[0]
                if definitionSourceId != None:
                    self.cacheCursor.execute("select name from source where id=%d" % definitionSourceId)

                    return "%s:%d:%d" % (self.cacheCursor.fetchone()[0], line, col)

        if not "implementation" in columnnames:  # types aren't implemented
            self.cacheCursor.execute("select id, %s from class where name='%s'" % (columnnames, word))
            res = self.cacheCursor.fetchall()
            if res:
                # TODO if there are multiple entries
                name, definitionSourceId, line, col = res[0]
                if definitionSourceId != None:
                    self.cacheCursor.execute("select name from source where id=%d" % definitionSourceId)

                    return "%s:%d:%d" % (self.cacheCursor.fetchone()[0], line, col)

        return ""

    def goto_imp(self, view):
        return self.goto_def(view, columnnames="implementationSourceId, implementationLine, implementationColumn")


sqlCache = SQLiteCache()
