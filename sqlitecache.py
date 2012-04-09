import sqlite3
import os.path
from clang import cindex
import time
import re
import sublime

scriptdir = os.path.dirname(os.path.abspath(__file__))
enableCache = True


class SQLiteCache:
    def __init__(self):
        self.createDB()
        self.cacheCursor = None
        self.cache = None

    def createDB(self):
        self.cache = sqlite3.connect("%s/cache.db" % scriptdir)
        self.cacheCursor = self.cache.cursor()
        self.cacheCursor.execute("""create table if not exists source(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cacheCursor.execute("""create table if not exists type(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            sourceId INTEGER,
            lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sourceId) REFERENCES source(id))""")
        self.cacheCursor.execute(
        """create table if not exists member(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            typeId INTEGER,
            returnTypeId INTEGER,
            field_or_method INTEGER,
            flags INTEGER,
            insertionText TEXT,
            displayText TEXT,
            FOREIGN KEY(typeId) REFERENCES type(id),
            FOREIGN KEY(returnTypeId) REFERENCES type(id) )""")
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

    def get_type(self, tu, filename, data, before, location):
        start = time.time()
        before = re.search("([^ \t]+)(\.|\->)$", before).group(0)
        match = re.search("([^.\-]+)(\.|\->)(.*)", before)
        var = match.group(1)
        before = match.group(3)
        end = time.time()
        print "var is %s (%f ms) " % (var, (end-start)*1000)
        start = time.time()

        regex = re.compile("(\w[^( \t\{,]+)[ \t\*\&]+(%s)[ \t]*(\(|\;|,|\)|=)" % var)

        match = None
        for m in regex.finditer(data, re.MULTILINE):
            if m.group(1) == "return":
                continue
            sub = data[m.start(2):location]
            count = 0
            lowest = 0
            while len(sub):
                idx1 = sub.rfind("{")
                idx2 = sub.rfind("}")
                if idx1 == idx2 and idx1 == -1:
                    break
                maxidx = max(idx1, idx2)

                sub = sub[:maxidx]
                if idx1 > idx2:
                    count -= 1
                    if count < lowest:
                        lowest = count
                elif idx2 != -1:
                    count += 1
            if count == lowest:
                match = m
                break
        end = time.time()
        print "Regex found type is %s (%f ms)" % ("None" if match == None else match.group(1), (end-start)*1000)
        if match == None:
            return None
        start = time.time()

        line = data[:match.start(2)].count("\n") + 1
        column = len(data[:match.start(2)].split("\n")[-1])+1
        print line
        print column
        type = cindex.Cursor.get(tu, filename, line, column)
        print type.kind
        print type.displayname
        if type is None or type.kind.is_invalid():
            return None
        if type.displayname != var:
            type.dump()
            for child in type.get_children():
                child.dump()
                if child.displayname == var:
                    type = child
                    break
            if type.displayname != var:
                return None
        print "resolving"
        type = type.get_resolved_cursor()
        if type is None or type.kind.is_invalid() or type.kind == cindex.CursorKind.CLASS_TEMPLATE:
            # templates are scary, lets not go there right now
            return None
        #self.format(type)

        end = time.time()
        print "took: %f ms" % ((end-start)*1000)
        count = 0
        while len(before) and count < 100 and not type is None:
            count += 1
            match = re.search("([^\.\-\(]+)(\(|\.|->)(.*)", before)
            if match == None:
                break

            before = match.group(3)
            count = 1
            function = False
            if match.group(2) == "(":
                function = True
                for i in range(len(before)):
                    if before[i] == '(':
                        count += 1
                    elif before[i] == ')':
                        count -= 1
                        if count == 0:
                            before = before[i+1:]
                            break
            before = re.match("(\.|\->)?(.*)", before).group(2)
            member = type.get_member(match.group(1), function)
            if member is None or member.kind.is_invalid():
                type = None
                break
            type = member.get_returned_cursor()
        if not type is None:
            print "type is"
            type.dump_self()
        return type

    def format(self, cursor):
        print cursor.kind
        ref = cursor
        if ref.kind.is_reference():
            ref = ref.get_reference()
        for child in ref.get_children():
            print child.kind
            if child.kind == cindex.CursorKind.CXX_METHOD or child.kind == cindex.CursorKind.FIELD_DECL:
                #print child.kind
                #print child.spelling
                print "%s" % (child.get_completionString())
            elif child.kind == cindex.CursorKind.CXX_ACCESS_SPEC_DECL:
                print child.get_children()
                print child.type.kind
                print child.result_type.kind
                print child.displayname
                print child.spelling


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
    def test(self, tu, view, line, prefix, locations):
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
            self.get_type(tu, view.file_name(), data, before, locations[0])
        end = time.time()
        print "%f ms" % ((end-start)*1000)


sqlCache = SQLiteCache()
        #     sub = before[:idx]
        #     idx2 = sub.find("(")
        #     if idx2 >= 0:
        #         sub = sub[:idx2]

        #     n = self.get_return_type(t, sub)
        #     print "%s.%s = %s" % (t, sub, n)
        #     t = n
        #     before = before[idx+1:]
        #     idx = before.find(".")
