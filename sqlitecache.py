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
from common import parse_res, Worker, error_message
try:
    from sqlite3 import connect
except:
    try:
        import platform
        if platform.architecture()[0] == "64bit":
            try:
                import pysqlite64._sqlite
            except:
                pass
            from pysqlite2.dbapi2 import connect
        else:
            from pysqlite2.dbapi2 import connect
    except:
        error_message("Unfortunately neither sqlite3 nor pysqlite2 could be imported so SublimeClang will not work")
import os.path
from clang import cindex
import time
import re
from parsehelp import *
from ctypes import cdll, CFUNCTYPE, c_char_p
import os


def get_nativeindex_library():
    import platform
    name = platform.system()
    if name == 'Darwin':
        return cdll.LoadLibrary('libnativeindexer.dylib')
    elif name == 'Windows':
        if isWin64:
            return cdll.LoadLibrary("libnativeindexer_x64.dll")
        return cdll.LoadLibrary('libnativeindexer.dll')
    else:
        try:
            # Try loading with absolute path first
            import os
            path = os.path.dirname(os.path.abspath(__file__))
            return cdll.LoadLibrary('%s/libnativeindexer.so' % path)
        except:
            try:
                # See if there's one in the system path
                return cdll.LoadLibrary("libnativeindexer.so")
            except:
                import traceback
                traceback.print_exc()
                error_message("""\
It looks like libclang.so couldn't be loaded. On Linux you have to \
compile it yourself, or install it via your package manager. \
Please note that this plugin uses features from clang 3.0 so \
make sure that is the version you have installed.

Once installed, you need to copy libclang.so into the root of this \
plugin. See http://github.com/quarnster/SublimeClang for more details.
""")

idxlib = get_nativeindex_library()

native_index_callback = CFUNCTYPE(None, c_char_p)
native_index = idxlib.nativeindex
native_index.argtypes = [c_char_p, cindex.Cursor, native_index_callback]
if cindex.isWin64:
    native_index.argtypes = [c_char_p, POINTER(cindex.Cursor), native_index_callback]


scriptdir = os.path.dirname(os.path.abspath(__file__))
enableCache = True


def get_db_name():
    return "%s/cache.db" % scriptdir


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
        namespaceId INTEGER DEFAULT -1,
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
        classId INTEGER DEFAULT -1,
        namespaceId INTEGER DEFAULT -1,
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
    cursor.execute("""create table if not exists macro(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        definitionSourceId INTEGER,
        definitionLine INTEGER,
        definitionColumn INTEGER,
        name TEXT,
        insertionText TEXT,
        displayText TEXT,
        usr TEXT,
        FOREIGN KEY(definitionSourceId) REFERENCES source(id))
        """)
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
    cursor.execute("""create unique index if not exists namespaceindex on namespace(name, parentId)""")
    cursor.execute("""create unique index if not exists sourceindex on source(name)""")
    cursor.execute("""create unique index if not exists toscanindex on toscan(sourceId)""")
    cursor.execute("""create unique index if not exists macroindex on macro(usr, name)""")


class DbClassType:
    NORMAL = 0
    TEMPLATE_CLASS = 1
    TEMPLATE_TYPE = 2
    RETURNED_COMPLEX_TEMPLATE = 3
    ENUM_CONSTANT = 4
    SIMPLE_TYPEDEF = 101
    COMPLEX_TYPEDEF = 102


class Indexer(Worker):
    def __init__(self):
        super(Indexer, self).__init__(threadcount=1)

    def test(self, data):
        print data
        self.set_status(data)

    def index(self, cursor, filename=None, dirs=None):
        start = time.time()
        try:
            native_index(get_db_name(), cursor, native_index_callback(self.test))
        except:
            import traceback
            traceback.print_exc()
            pass
        end = time.time()
        timing = "Indexing translation unit took %s seconds" % (end-start)
        print timing
        self.set_status(timing)

    def do_index_tu(self, data):
        tu, filename, dirs = data
        try:
            tu.lock()
            self.index(tu.var.cursor, filename, dirs)
        finally:
            tu.unlock()

    def do_clear(self, data):
        cache = connect(get_db_name(), timeout=10.0)
        cacheCursor = cache.cursor()
        cacheCursor.execute("drop table source")
        cacheCursor.execute("drop table type")
        cacheCursor.execute("drop table dependency")
        cacheCursor.execute("drop table namespace")
        cacheCursor.execute("drop table inheritance")
        cacheCursor.execute("drop table class")
        cacheCursor.execute("drop table member")
        cacheCursor.execute("drop table templatearguments")
        cacheCursor.execute("drop table templatedmembers")
        cacheCursor.execute("drop table typedef")
        cacheCursor.execute("drop table macro")
        createDB(cacheCursor)
        cache.commit()
        cacheCursor.close()
        cache.close()

    def add_index_tu_task(self, translationUnit, filename, dirs=[]):
        filedir = os.path.dirname(filename)
        if filedir not in dirs:
            dirs.append(filedir)
        self.tasks.put((self.do_index_tu, (translationUnit, filename, dirs)))

    def clear(self):
        self.tasks.put((self.do_clear, None))


indexer = Indexer()


class SQLiteCache:
    def __init__(self):
        self.cache = connect(get_db_name(), timeout=0.5)
        self.cacheCursor = self.cache.cursor()
        createDB(self.cacheCursor)

    def clear(self):
        indexer.clear()

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
        sql = "select id, typeId, name from class where id=%d" % data.ret[0]
        self.cacheCursor.execute(sql)
        res = self.cacheCursor.fetchone()
        if res != None and res[1] != DbClassType.NORMAL:
            if res[1] == DbClassType.TEMPLATE_CLASS:
                if args == None:
                    sql = "select argumentClassId, argumentNumber from templatedmembers where memberId=%d order by argumentNumber" % data.ret[1]
                    self.cacheCursor.execute(sql)
                    res = self.cacheCursor.fetchall()
                    data.templateargs = [(x[0], None) for x in res]
                else:
                    data.templateargs = args
            elif res[1] == DbClassType.TEMPLATE_TYPE:
                if data.templateargs != None:
                    tempargs = data.templateargs
                    sql = "select argumentNumber from templatearguments where classId=%d and argumentClassId=%d order by argumentNumber" % (data.classId, data.ret[0])
                    sql = "select argumentNumber,argumentClassId from templatearguments where classId=%d order by argumentNumber" % (data.classId)
                    self.cacheCursor.execute(sql)
                    idx = 0
                    for c in self.cacheCursor:
                        idx = c[0]
                        if idx >= len(tempargs):
                            idx-=1
                            break
                        data.classId = tempargs[idx][0]
                        data.ret = (data.classId, 0)
                        break

                    data.templateargs = tempargs[idx][1]
                    #data.classId = tempargs[idx][0]

                    return self.lookup(data, data.templateargs)
                else:
                    sql = "select argumentClassId, argumentNumber from templatedmembers where memberId=%d order by argumentNumber" % data.ret[1]
                    self.cacheCursor.execute(sql)
                    res = self.cacheCursor.fetchall()
                    data.templateargs = [x[0] for x in res]
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
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
                data.ret = (classId, data.ret[1])
                return self.lookup(data, newargs)
            elif res[1] == DbClassType.RETURNED_COMPLEX_TEMPLATE:
                tmp = solve_template(res[2])
                classId, newargs = self.resolve_template_class_ids(tmp, data.namespaces)
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
                if classid != parent[0]:  # TODO: should figure outh why this happens
                    self.complete_sql(parent[0], prefix, ret, True)

    def get_namespace_id(self, data, namespaces):
        ns = data.split("::")
        if len(ns) == 0:
            return None
        if ns[0].strip() == "":
            return None
        ret = None
        parent = "=-1"
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
        id = -1
        ns = name.split("::")
        name = ns.pop()
        used_ns = namespaces
        ns = self.get_namespace_id("::".join(ns), namespaces)
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

            if ret != None:
                id = ret[0]
                if ret[1] == DbClassType.COMPLEX_TYPEDEF:
                    sql = "select name from typedef where classId=%d" % (id)
                    self.cacheCursor.execute(sql)
                    tmp = solve_template(self.cacheCursor.fetchone()[0])
                    classId, newargs = self.resolve_template_class_ids(tmp, namespaces)
                    return classId, newargs
                elif ret[1] == DbClassType.SIMPLE_TYPEDEF:
                    sql = "select parentId from inheritance where classId=%d" % id
                    self.cacheCursor.execute(sql)
                    classId = self.cacheCursor.fetchone()[0]
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
        namespaces.append("=-1")
        template = solve_template(typename)
        template = self.resolve_template_class_ids(template, namespaces)
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
            self.get_final_type(self.lookup_sql, data, tocomplete)
            classid = data.classId
        return classid

    def complete_members(self, data, before, prefix):
        ret = None
        classid = self.resolve_class_id_from_line(data, before)
        if classid != -1 and classid != None:
            ret = []
            self.complete_sql(classid, prefix, ret)
        return ret

    def get_namespace_query(self, namespace):
        if len(namespace) == 0:
            return "=-1"
        sub = namespace.split("::")
        ns = "=-1"
        for sub in sub:
            sql = "select id from namespace where name='%s' and parentId %s" % (sub, ns)
            self.cacheCursor.execute(sql)
            result = self.cacheCursor.fetchone()
            if result == None:
                ns = "=-1"
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
            ns = "=-1"
            if namespace != "null":
                ns = self.get_namespace_query(namespace)
                if ns == "=-1":
                    # Couldn't find that namespace
                    continue
            self.cacheCursor.execute("select id from namespace where parentId %s and name='%s'" % (ns, first))
            id = self.cacheCursor.fetchone()
            if id != None:
                id = id[0]
                type = "ns"
                break
            self.cacheCursor.execute("select id from class where namespaceId %s and name='%s'" % (ns, first))
            id = self.cacheCursor.fetchone()
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

    def complete(self, data, line, prefix):
        before = line
        if len(prefix) > 0:
            before = line[:-len(prefix)]

        if re.search("::$", before):
            type, id = self.get_colon_colon_base(data, before)

            if not type:
                return None
            ret = None

            if type == "ns":
                ret = []
                self.cacheCursor.execute("select name from class where namespaceId=%d and name like '%s%%' order by name" % (id, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tclass" % n[0], n[0]))
                self.cacheCursor.execute("select name from namespace where parentId= %d and name like '%s%%' order by name" % (id, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tnamespace" % n[0], n[0]))
                self.cacheCursor.execute("select displayText, insertionText from member where classId =-1 and namespaceId=%d and name like '%s%%' order by name" % (id, prefix))
                data = self.cacheCursor.fetchall()
                if data:
                    ret.extend(data)
                return ret
            elif type == "class":
                self.cacheCursor.execute("select displayText, insertionText from member where classId=%s and static=1 and name like '%s%%' order by name" % (id, prefix))
                ret = []
                members = self.cacheCursor.fetchall()
                if members:
                    ret.extend(members)
                return ret
            return None
        elif re.search("([^ \t]+)(\.|\->)$", before):
            return self.complete_members(data, before, prefix)
        else:
            ret = []
            namespaces = extract_used_namespaces(data)
            namespaces.append("null")

            mynamespace = extract_namespace(data)
            if len(mynamespace):
                namespaces.append(mynamespace)
            for namespace in namespaces:
                ns = "=-1"
                if namespace != "null":
                    ns = self.get_namespace_query(namespace)
                    if ns == "=-1":
                        # Couldn't find that namespace
                        continue

                self.cacheCursor.execute("select name from class where namespaceId %s and name like '%s%%' and typeId != %d and typeId != %d" % (ns, prefix, DbClassType.TEMPLATE_TYPE, DbClassType.RETURNED_COMPLEX_TEMPLATE))
                for c in self.cacheCursor:
                    ret.append(("%s\tclass" % c[0], c[0]))
                self.cacheCursor.execute("select name from namespace where parentId %s and name like '%s%%'" % (ns, prefix))
                for n in self.cacheCursor:
                    ret.append(("%s\tnamespace" % n[0], n[0]))
                self.cacheCursor.execute("select displayText, insertionText from member where classId =-1 and namespaceId %s and name like '%s%%'" % (ns, prefix))
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
                            self.cacheCursor.execute("select displayText, insertionText from member where classId=%d and access <=%d and name like '%s%%'" % (parent[0], cindex.CXXAccessSpecifier.PROTECTED, prefix))
                            members = self.cacheCursor.fetchall()
                            if members:
                                ret.extend(members)

            self.cacheCursor.execute("select displayText, insertionText from macro where name like '%s%%'" % (prefix))
            macros = self.cacheCursor.fetchall()
            if macros:
                ret.extend(macros)

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

    def goto_def(self, filename, fulldata, caret, scopename, columnnames="definitionSourceId, definitionLine, definitionColumn"):
        data = fulldata[0:caret]

        word = extract_word_at_offset(fulldata, caret)
        line = extract_line_at_offset(fulldata, caret)
        regex = re.compile("([^\\s&*]+$)")
        extended_word = regex.search(collapse_parenthesis(extract_extended_word_at_offset(fulldata, caret)))
        extended_start = regex.search(collapse_parenthesis(extract_line_until_offset(fulldata, caret)))
        if extended_start:
            extended_start = extended_start.group(1)
        else:
            extended_start = ""

        if extended_word == None:
            return ""
        extended_word = extended_word.group(1)
        variables = extract_variables(data)
        if not "function-call" in scopename and not "entity.name.function." in scopename:
            for type, name in variables:
                if name == word:
                    type = type.replace("*", "\*")
                    pos = caret
                    for match in re.finditer("(%s)\\s*(%s)" % (type, name), data):
                        pos = match.start(2)
                    row, col = get_line_and_column_at_offset(pos)
                    return "%s:%d:%d" % (filename, row+1, col+1)

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
            classes.append(" =-1")

        for clazz in classes:
            sql = "select name, %s from member where name='%s' and classId %s" % (columnnames, word, clazz)
            self.cacheCursor.execute(sql)
            res = self.cacheCursor.fetchall()
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

    def goto_imp(self, filename, fulldata, caret, scopename):
        return self.goto_def(filename, fulldata, caret, scopename, columnnames="implementationSourceId, implementationLine, implementationColumn")


sqlCache = SQLiteCache()
