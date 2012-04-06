import sqlite3
import os.path
from clang import cindex
import time
import re

scriptdir = os.path.dirname(os.path.abspath(__file__))
cache = None
cacheCursor = None
enableCache = True


def createDB():
    global cache
    global cacheCursor
    cache = sqlite3.connect("%s/cache.db" % scriptdir)
    cacheCursor = cache.cursor()
    cacheCursor.execute("""create table if not exists source(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cacheCursor.execute("""create table if not exists type(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        sourceId INTEGER,
        FOREIGN KEY(sourceId) REFERENCES source(id))""")
    cacheCursor.execute(
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
createDB()


def cursor_to_db_name(c2):
    ret = ""
    for c3 in c2.get_children():
        add = ""
        if c3.kind.is_reference():
            add = c3.displayname
        if len(ret) > 0 and len(add) > 0:
            ret += ";;-;;"
        ret += add
    return ret


def recurse(cursor, symbol, count=0):
    if cursor is None or cursor.kind.is_invalid() or count > 2:
        return None
    if cursor.kind.is_reference():
        c2 = cursor.get_reference()
        if not c2 is None and not c2.kind.is_invalid() and not c2 == cursor:
            ret = recurse(c2, symbol, count+1)
            if not ret is None:
                return ret
    elif cursor.kind == cindex.CursorKind.VAR_DECL and cursor.displayname == symbol:
        return cursor
    else:
        for child in cursor.get_children():
            ret = recurse(child, symbol, count+1)
            if not ret is None:
                return ret
    return None


def find_type(cursor, symbol, tu=None, count=0):
    type = recurse(cursor, symbol)
    if not type is None:
        return type

    if not tu is None and count < 20:
        loc = cursor.extent.start
        row = loc.line
        col = loc.column
        if col > 1:
            col -= 1
        else:
            row -= 1
        if row < 1:
            return None

        cursor2 = cindex.Cursor.get(tu, loc.file.name, row, col)
        if not cursor2 is None:
            if cursor2.kind.is_invalid():
                return None
            return find_type(cursor2, symbol, tu, count+1)
    return None


def test(tu, view, line, prefix):
    start = time.time()
    before = line
    if len(prefix) > 0:
        before = line[:-len(prefix)]
    if re.search("[ \t]+$", before):
        before = ""
    elif re.search("(\.|->)$", before):
        before = re.search("([^ \t]+)(\.|->)$", before).group(0)
        idx = before.find(".")
        idx2 = before.find("->")
        if idx == -1:
            idx = 100000000000000
        if idx2 == -1:
            idx2 = 10000000000000
        idx = min(idx, idx2)
        var = before[:idx].strip()
        before = before[idx+1:]
        end = time.time()
        print "var is %s (%f ms) " % (var, (end-start)*1000)
        start = time.time()
        row, col = view.rowcol(view.sel()[0].a)
        cursor = cindex.Cursor.get(tu, view.file_name(),
                                   row + 1, col + 1)
        if not cursor is None:
            cursor = find_type(cursor, var, tu)
            if not cursor is None:
                print "name: %s" % cursor_to_db_name(cursor)
        end = time.time()
        print "took: %f ms" % ((end-start)*1000)
