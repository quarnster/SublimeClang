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
        typeId INTEGER,
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


class DbClassType:
    NORMAL = 0
    TEMPLATE_CLASS = 1
    TEMPLATE_TYPE = 2
    TYPEDEF = 3


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

    def resolve_class_id(self, id, args):
        sql = "select id, typeId, name from class where id=%d" % id
        self.cacheCursor.execute(sql)
        res = self.cacheCursor.fetchone()
        print sql, res
        if res != None:
            if res[1] == DbClassType.TYPEDEF:
                sql = "select name from typedef where classId=%d" % (id)
                self.cacheCursor.execute(sql)
                tmp = solve_template(self.cacheCursor.fetchone()[0])
                print sql, tmp
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
                print "resolved to1: %d, %s" % (classId, newargs)
                return self.resolve_class_id(classId, newargs)  # Proper memberId?
                #TODO data.templateargs = newargs
        else:
            return None
        return res[0]

    def lookup(self, data, args):
        print data.ret
        sql = "select id, typeId, name from class where id=%d" % data.ret[0]
        self.cacheCursor.execute(sql)
        res = self.cacheCursor.fetchone()
        print sql, res
        if res != None and res[1] != DbClassType.NORMAL:
            if res[1] == DbClassType.TEMPLATE_TYPE:
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
            elif res[1] == DbClassType.TYPEDEF:
                sql = "select name from typedef where classId=%d" % (data.ret[0])
                self.cacheCursor.execute(sql)
                name = self.cacheCursor.fetchone()[0]
                tmp = solve_template(name)
                print sql, name, tmp
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
                print "resolved to2: %d, %s" % (classId, data.templateargs)
                data.ret = (classId, data.ret[1])
                return self.lookup(data, newargs)  # Proper memberId?
                #TODO data.templateargs = newargs

        data.classId = data.ret[0]
        return True

    def lookup_sql(self, data, name, function):
        sql = "select returnId, id from member where classId=%d and name='%s' and access <=%d" % (data.classId, name, data.access)
        self.cacheCursor.execute(sql)
        data.ret = self.cacheCursor.fetchone()
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
                    if self.lookup_sql(data, name, function):
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
            sql = "select id, typeId from class where name='%s' and namespaceId %s and (typeId=%d or typeId=%d)" % (name, ns, DbClassType.NORMAL if args == None else DbClassType.TEMPLATE_CLASS, DbClassType.TYPEDEF)
            self.cacheCursor.execute(sql)
            ret = self.cacheCursor.fetchone()
            if ret == None and args == None:
                sql = "select id, typeId from class where name='%s' and namespaceId %s and typeId=%d" % (name, ns, DbClassType.TEMPLATE_TYPE)
                self.cacheCursor.execute(sql)
                ret = self.cacheCursor.fetchone()

            print sql, ret
            if ret != None:
                id = ret[0]
                if ret[1] == DbClassType.TYPEDEF:
                    sql = "select name from typedef where classId=%d" % id
                    self.cacheCursor.execute(sql)
                    ret = self.cacheCursor.fetchone()
                    if ret == None:
                        return None, None
                    tmp = solve_template(ret[0])
                    id, arg = self.resolve_template_class_ids(tmp, namespaces)
                    return id, arg
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

    def complete_members(self, tu, filename, data, before, prefix):
        ret = None
        # if tu != None:
        #     ret = self.complete_cursors(tu, filename, data, before, prefix)
        #     if ret != None:
        #         return ret

        typedef = get_type_definition(data, before)
        if typedef == None:
            return None
        line, column, typename, var, tocomplete = typedef
        if typename == None and var != None:
            # Try and see if we're in a class and var
            # thus might be a member of "this"
            clazz = extract_class(data)
            if clazz == None:
                clazz = extract_class_from_function(data)
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
                    self.access = cindex.CXXAccessSpecifier.PUBLIC
                    self.templateargs = []
            data = Temp()
            data.classId = classid
            data.namespaces = namespaces
            data.templateargs = template[1]
            print "getting final type"
            self.get_final_type(self.lookup_sql, data, tocomplete)
            ret = []
            classid = data.classId
            print classid
            if classid != -1:
                self.complete_sql(classid, prefix, ret)
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
                self.access = [cindex.CXXAccessSpecifier.PRIVATE]
                self.templates = []
                self.templateParameter = []

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
                if isinstance(source, cindex.Cursor):
                    source = "<unknown>" if source.location.file is None else source.location.file.name
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
                    ns = data.get_or_add_namespace_id(p, ns)
                return data.get_or_add_class_id(cursor, ns)

            def get_or_add_class_id(self, child, ns=None):
                typeId = DbClassType.NORMAL
                real = child
                if child.kind == cindex.CursorKind.TYPEDEF_DECL:
                    typeId = DbClassType.TYPEDEF
                elif real.kind == cindex.CursorKind.CLASS_TEMPLATE:
                    typeId = DbClassType.TEMPLATE_CLASS
                elif real.kind == cindex.CursorKind.TEMPLATE_TYPE_PARAMETER:
                    typeId = DbClassType.TEMPLATE_TYPE
                if ns == None:
                    if typeId != DbClassType.TEMPLATE_TYPE:
                        ns = self.get_namespace_id()
                    else:
                        ns = "null"
                sql = "select id from class where name='%s' and namespaceId %s and typeId=%d" % (child.spelling, self.get_namespace_id_query(ns), typeId)
                self.cacheCursor.execute(sql)
                idx = self.cacheCursor.fetchone()
                if idx == None:
                    sql2 = """insert into class (name, namespaceId,
                                definitionSourceId, definitionLine, definitionColumn, typeId) VALUES ('%s', %s, %d, %d, %d, %d)""" % \
                            (child.spelling, ns, \
                             self.get_source_id(child), child.location.line, child.location.column, typeId)
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
                elif oldparent.kind == cindex.CursorKind.CLASS_DECL or \
                        oldparent.kind == cindex.CursorKind.ENUM_DECL or \
                        oldparent.kind == cindex.CursorKind.STRUCT_DECL:
                    data.classes.pop()
                data.access.pop()
                if oldparent.kind == cindex.CursorKind.CLASS_TEMPLATE:
                    data.classes.pop()
                    data.templates.pop()
                    data.templateParameter.pop()

            #if parent and parent.kind == cindex.CursorKind.CLASS_TEMPLATE:
            #if child.spelling == "test":
            #    child.dump()

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
                if child.location.file != None:
                    f = open(child.location.file.name)
                    fdata = f.read()[child.extent.start.offset:child.extent.end.offset+1]
                    f.close()
                    regex = re.search("typedef\s+(.*)\s+(.*);", fdata, re.DOTALL)
                    if regex:
                        #print regex.groups()
                        try:
                            data.cacheCursor.execute("insert into typedef (classId, name) VALUES (%d, '%s')" % (id, regex.group(1)))
                        except:
                            pass
                    else:
                        print "failed regex: %s" % (fdata)
            elif child.kind == cindex.CursorKind.CXX_METHOD or \
                    child.kind == cindex.CursorKind.FUNCTION_DECL or \
                    child.kind == cindex.CursorKind.FIELD_DECL or \
                    child.kind == cindex.CursorKind.VAR_DECL or \
                    child.kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
                classId = "null"
                if len(data.classes) > 0:
                    classId = data.classes[-1]

                sql = """select id from member where name='%s' and definitionSourceId=%d and definitionLine=%d and definitionColumn=%d and classId %s""" % \
                    (child.spelling, data.get_source_id(child), child.location.line, child.location.column, data.get_namespace_id_query(classId))
                data.cacheCursor.execute(sql)
                if data.cacheCursor.fetchone():
                    # TODO. what?
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
                            for c in returnCursor.get_children():
                                if c.kind == cindex.CursorKind.TEMPLATE_REF:
                                    templateCursor = returnCursor
                                    returnCursor = c.get_reference()
                                    break
                        # if templateCursor == returnCursor:
                        #         print "hmm... need to tweak this"
                        returnId = data.get_class_id_from_cursor(returnCursor)
                    if child.spelling == "front":
                        child.dump()
                        print "return is "
                        returnCursor.dump()
                        data.cacheCursor.execute("select name, id, typeId from class where id=%d" % returnId)
                        print data.cacheCursor.fetchone()

                    ret = parse_res(child.get_completion_string(), "")
                    static = False
                    if child.kind == cindex.CursorKind.CXX_METHOD:
                        static = child.get_cxxmethod_is_static()
                        # if child.spelling == "front":
                        #     child.dump()

                    sql2 = """insert into member (namespaceId, classId, returnId, definitionSourceId, definitionLine, definitionColumn, name, displayText, insertionText, static, access) values (%s, %s, %s, %s, %d, %d, '%s', '%s', '%s', %d, %d)""" % \
                        (data.get_namespace_id(), classId, returnId, \
                         data.get_source_id(child), child.location.line, child.location.column, \
                         child.spelling, ret[1], ret[2], static, data.access[-1])
                    data.cacheCursor.execute(sql2)
                    if not templateCursor is None:
                        data.cacheCursor.execute(sql)
                        memberId = data.cacheCursor.fetchone()[0]
                        children = templateCursor.get_children()

                        if child.spelling == "front":
                            templateCursor.dump()
                        # print templateCursor.get_referenced_name_range()
                        # print templateCursor.extent
                        #templateCursor.get_specialized_cursor_template().dump()
                        for i in range(0, len(children)):
                            c = children[i]
                            if c.kind == cindex.CursorKind.PARM_DECL or c.kind == cindex.CursorKind.COMPOUND_STMT:
                                break
                            # print "child is %s, %s" % (c.spelling, c.kind)
                            # c.dump_self()
                            # print c.get_referenced_name_range()
                            # print c.extent
                            # print c.get_canonical_cursor().dump_self()
                            # print c.get_semantic_parent().dump_self()
                            # print c.get_lexical_parent().dump_self()
                            # print "end dump"

                            data.cacheCursor.execute("insert into templatedmembers (memberId, argumentClassId, argumentNumber) VALUES (%d, %s, %d)" % (memberId, data.get_class_id_from_cursor(c.get_resolved_cursor()), i))
                            data.cacheCursor.execute(sql)

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
                data.access.append(cindex.CXXAccessSpecifier.PUBLIC)
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
                if ns == None:
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
            myclass = extract_class(data)
            if myclass == None:
                myclass = extract_class_from_function(data)

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
        elif re.search("::$", before):
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
            return self.complete_members(tu, view.file_name(), data, before, prefix)
        return None
