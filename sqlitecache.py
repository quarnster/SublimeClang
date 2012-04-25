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
from common import Worker, error_message
import os.path
from clang import cindex
import time
import re
from parsehelp import *
from ctypes import cdll, CFUNCTYPE, c_char_p, c_void_p, c_int
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

_createDB = idxlib.createDB
_createDB.restype = c_void_p
_createDB.argtypes = [c_char_p, c_int, c_int]
_deleteDB = idxlib.deleteDB
_deleteDB.argtypes = [c_void_p]
db_voidQuery = idxlib.db_voidQuery
db_voidQuery.argtypes = [c_void_p, c_char_p]
db_intQuery = idxlib.db_intQuery
db_intQuery.argtypes = [c_void_p, c_char_p]
db_intQuery.restype = c_int
db_stepQuery = idxlib.db_stepQuery
db_stepQuery.argtypes = [c_void_p]
db_stepQuery.restype = c_int
db_complexQuery = idxlib.db_complexQuery
db_complexQuery.argtypes = [c_void_p, c_char_p]
db_complexQuery.restype = c_void_p
db_getStringColumn = idxlib.db_getStringColumn
db_getStringColumn.argtypes = [c_void_p, c_int]
db_getStringColumn.restype = c_char_p
db_getIntColumn = idxlib.db_getIntColumn
db_getIntColumn.argtypes = [c_void_p, c_int]
db_getIntColumn.restype = c_int
db_getColumnType = idxlib.db_getColumnType
db_getColumnType.argtypes = [c_void_p, c_int]
db_getColumnType.restype = c_int
db_getColumnCount = idxlib.db_getColumnCount
db_getColumnCount.argtypes = [c_void_p]
db_getColumnCount.restype = c_int
db_doneQuery = idxlib.db_doneQuery
db_doneQuery.argtypes = [c_void_p]

scriptdir = os.path.dirname(os.path.abspath(__file__))
enableCache = True


def get_db_name():
    return "%s/cache.db" % scriptdir


class ComplexQuery:
    def __init__(self, handle):
        self.handle = handle

    def __del__(self):
        db_doneQuery(self.handle)

    def __getitem__(self, i):
        if db_getColumnType(self.handle, i) == 1:
            return db_getIntColumn(self.handle, i)
        return db_getStringColumn(self.handle, i)

    def __len__(self):
        return db_getColumnCount(self.handle)

    def fetchall(self):
        start = time.time()
        ret = []
        cols = db_getColumnCount(self.handle)
        while True:
            row = []
            for i in range(cols):
                row.append(self[i])
            ret.append(tuple(row))
            c = db_stepQuery(self.handle)
            if c != 100:
                break
        end = time.time()
        print "fetchall: %f ms" % ((end-start)*1000)
        return ret


class DB:
    def __init__(self, name, timeout=5000, readonly=False):
        self.handle = _createDB(name, timeout, readonly)
        self._delcopy = _deleteDB
        if self.handle == None or self.handle == 0:
            raise ValueError()

    def __del__(self):
        self._delcopy(self.handle)

    def vq(self, q):
        db_voidQuery(self.handle, q)

    def iq(self, q):
        return db_intQuery(self.handle, q)

    def cq(self, q):
        start = time.time()
        comp = db_complexQuery(self.handle, q)
        end = time.time()
        print "prep cq: %f ms" % ((end-start)*1000)

        if comp:
            return ComplexQuery(comp)
        return None


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

    def do_clear(self, data=None):
        db = DB(get_db_name(), 5000)
        db.vq("delete from source")
        db.vq("delete from type")
        db.vq("delete from dependency")
        db.vq("delete from namespace")
        db.vq("delete from inheritance")
        db.vq("delete from class")
        db.vq("delete from member")
        db.vq("delete from templatearguments")
        db.vq("delete from templatedmembers")
        db.vq("delete from typedef")
        db.vq("delete from macro")
        del db

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
        self.cache = DB(get_db_name(), 50, True)

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
        res = self.cache.cq(sql)
        if res != None and res[1] != DbClassType.NORMAL:
            if res[1] == DbClassType.TEMPLATE_CLASS:
                if args == None:
                    sql = "select argumentClassId, argumentNumber from templatedmembers where memberId=%d order by argumentNumber" % data.ret[1]
                    res = self.cache.cq(sql)
                    if res:
                        data.templateargs = [(x[0], None) for x in res.fetchall()]
                    else:
                        data.templateargs = []
                else:
                    data.templateargs = args
            elif res[1] == DbClassType.TEMPLATE_TYPE:
                if data.templateargs != None:
                    tempargs = data.templateargs
                    sql = "select argumentNumber,argumentClassId from templatearguments where classId=%d order by argumentNumber" % (data.classId)
                    q = self.cache.cq(sql)
                    idx = 0
                    for c in q.fetchall():
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
                    res = self.cache.cq.fetchall()
                    data.templateargs = [x[0] for x in res]
            elif res[1] == DbClassType.SIMPLE_TYPEDEF:
                sql = "select parentId from inheritance where classId=%d" % data.ret[0]
                data.ret = (self.cache.iq(sql), data.ret[1])
                return self.lookup(data, data.templateargs)
            elif res[1] == DbClassType.COMPLEX_TYPEDEF:
                sql = "select name from typedef where classId=%d" % (data.ret[0])
                name = self.cache.cq(sql)[0]
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
            data.ret = self.cache.cq(sql)
        elif pointer == "->":
            sql = "select returnId, id from member where classId=%d and name='operator->' and access <=%d" % (data.classId, data.access)
            ret = self.cache.cq(sql)
            if ret == None:
                return True
            data.ret = ret
        else:
            return True
        if data.ret == None or data.ret[0] == None:
            parents = self.cache.cq("select parentId from inheritance where classId=%d" % data.classId).fetchall()
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
        members = self.cache.cq("select displayText, insertionText from member where classId=%s and name like '%s%%' and static=0 and access<=%d" % (classid, prefix, access))
        if members:
            members = members.fetchall()
            if parent:
                for member in members:
                    if member not in ret:
                        ret.append(member)
            else:
                ret.extend(members)
        parents = self.cache.cq("select parentId from inheritance where classId=%d" % classid)
        if parents != None:
            for parent in parents.fetchall():
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
            id = self.cache.iq("select id from namespace where parentId %s and name='%s'" % (parent, ns[0]))
            if id != -1:
                parent = "=%d" % id
                ret = id
                break
        ns.pop(0)

        while len(ns) > 0:
            id = self.cache.iq("select id from namespace where parentId %s and name='%s'" % (parent, ns[0]))
            if id != -1:
                parent = "=%d" % id
                ret = id
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
            ret = self.cache.cq(sql)
            if ret == None and args == None:
                sql = "select id, typeId from class where name='%s' and namespaceId %s and typeId=%d" % (name, ns, DbClassType.TEMPLATE_TYPE)
                ret = self.cache.cq(sql)

            if ret != None:
                id = ret[0]
                if ret[1] == DbClassType.COMPLEX_TYPEDEF:
                    tmp = solve_template(self.cache.cq("select name from typedef where classId=%d" % (id))[0])
                    classId, newargs = self.resolve_template_class_ids(tmp, namespaces)
                    return classId, newargs
                elif ret[1] == DbClassType.SIMPLE_TYPEDEF:
                    sql = "select parentId from inheritance where classId=%d" % id
                    classId = self.cache.iq(sql)
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
            result = self.cache.iq(sql)
            if result == -1:
                ns = "=-1"
                break
            else:
                ns = "=%s" % result
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
            id = self.cache.iq("select id from namespace where parentId %s and name='%s'" % (ns, first))
            if id != -1:
                type = "ns"
                break
            id = self.cache.iq("select id from class where namespaceId %s and name='%s'" % (ns, first))
            if id != -1:
                id = id
                type = "class"
                break
        if type == None:
            return type, id
        for item in tofind:
            if len(item) == 0:
                continue
            if type == "ns":
                newid = self.cache.iq("select id from class where namespaceId= %d and name='%s'" % (id, item))
                if newid != None:
                    id = newid
                    type = "class"
                    continue
                newid = self.cache.iq("select id from namespace where parentId= %d and name='%s'" % (id, item))
                if newid != None:
                    id = newid
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
                q = self.cache.cq("select name from class where namespaceId=%d and name like '%s%%' order by name" % (id, prefix))
                if q:
                    for n in q.fetchall():
                        ret.append(("%s\tclass" % n[0], n[0]))
                q = self.cache.cq("select name from namespace where parentId= %d and name like '%s%%' order by name" % (id, prefix))
                if q:
                    for n in q.fetchall():
                        ret.append(("%s\tnamespace" % n[0], n[0]))
                data = self.cache.cq("select displayText, insertionText from member where classId =-1 and namespaceId=%d and name like '%s%%' order by name" % (id, prefix))
                if data:
                    ret.extend(data.fetchall())
                return ret
            elif type == "class":
                members = self.cache.cq("select displayText, insertionText from member where classId=%s and static=1 and name like '%s%%' order by name" % (id, prefix))
                ret = []
                if members:
                    ret.extend(members.fetchall())
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

                q = self.cache.cq("select name from class where namespaceId %s and name like '%s%%' and typeId != %d and typeId != %d" % (ns, prefix, DbClassType.TEMPLATE_TYPE, DbClassType.RETURNED_COMPLEX_TEMPLATE))
                if q:
                    for c in q.fetchall():
                        ret.append(("%s\tclass" % c[0], c[0]))
                q = self.cache.cq("select name from namespace where parentId %s and name like '%s%%'" % (ns, prefix))
                if q:
                    for n in q.fetchall():
                        ret.append(("%s\tnamespace" % n[0], n[0]))
                members = self.cache.cq("select displayText, insertionText from member where classId =-1 and namespaceId %s and name like '%s%%'" % (ns, prefix))
                if members:
                    ret.extend(members.fetchall())
            myclass = extract_class_from_function(data)
            if myclass == None:
                myclass = extract_class(data)

            if myclass != None:
                ns = self.get_namespace_query(mynamespace)
                classid = self.cache.iq("select id from class where name='%s' and namespaceId %s" % (myclass, ns))
                if classid !=-1:
                    members = self.cache.cq("select displayText, insertionText from member where classId=%s and name like '%s%%'" % (classid, prefix))
                    if members:
                        ret.extend(members.fetchall())
                    parents = self.cache.cq("select parentId from inheritance where classId=%d" % classid)
                    if parents != None:
                        for parent in parents.fetchall():
                            members = self.cache.cq("select displayText, insertionText from member where classId=%d and access <=%d and name like '%s%%'" % (parent[0], cindex.CXXAccessSpecifier.PROTECTED, prefix))
                            if members:
                                ret.extend(members.fetchall())

            macros = self.cache.cq("select displayText, insertionText from macro where name like '%s%%'" % (prefix))
            if macros:
                ret.extend(macros.fetchall())

            variables = extract_variables(data)
            for var in variables:
                ret.append(("%s\t%s" % (var[1], var[0]), var[1]))
            ret = sorted(ret, key=lambda a: a[1])
            return ret
        return None

    def get_inheritance_ids(self, classid, ret):
        parents = self.cache.cq("select parentId from inheritance where classId=%d" % classid)
        if parents != None:
            for parent in parents.fetchall():
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
                    row, col = get_line_and_column_from_offset(fulldata, pos)
                    return "%s:%d:%d" % (filename, row, col)

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
                q = self.cache.cq("select id from class where name='%s'" % clazz)
                if q:
                    for c in q.fetchall():
                        classes.append("=%d" % c[0])
                        inheritance = []
                        self.get_inheritance_ids(c[0], inheritance)
                        for inh in inheritance:
                            classes.append("=%d" % inh)
            classes.append(" =-1")

        for clazz in classes:
            sql = "select name, %s from member where name='%s' and classId %s" % (columnnames, word, clazz)
            res = self.cache.cq(sql)
            if res:
                # TODO if there are multiple entries
                name, definitionSourceId, line, col = res[0], res[1], res[2], res[3]
                if definitionSourceId != None:
                    tmp = self.cache.cq("select name from source where id=%d" % definitionSourceId)

                    return "%s:%d:%d" % (tmp[0], line, col)

        if not "implementation" in columnnames:  # types aren't implemented
            res = self.cache.cq("select id, %s from class where name='%s'" % (columnnames, word))
            if res:
                # TODO if there are multiple entries
                name, definitionSourceId, line, col = res[0], res[1], res[2], res[3]
                if definitionSourceId != None:
                    tmp = self.cache.cq("select name from source where id=%d" % definitionSourceId)

                    return "%s:%d:%d" % (tmp[0], line, col)
            self.cache.cq("select id, %s from macro where name='%s'" % (columnnames, word))
            if res:
                name, definitionSourceId, line, col = res[0], res[1], res[2], res[3]
                if definitionSourceId != None:
                    tmp = self.cache.cq("select name from source where id=%d" % definitionSourceId)
                    return "%s:%d:%d" % (tmp[0], line, col)

        return ""

    def goto_imp(self, filename, fulldata, caret, scopename):
        return self.goto_def(filename, fulldata, caret, scopename, columnnames="implementationSourceId, implementationLine, implementationColumn")


sqlCache = SQLiteCache()
