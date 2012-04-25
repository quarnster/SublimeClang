/*
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
*/
#include "clang-c/Index.h"
#include <stdio.h>
#include <string>
#include "sqlite/sqlite3.h"
#include <vector>
#include <boost/foreach.hpp>
#include <boost/regex.hpp>

void checkthrow(const char *buf, int rc)
{
    switch (rc)
    {
        case SQLITE_OK:
        case SQLITE_ROW:
        case SQLITE_DONE:
            break;
        default:
        {
            char tmp[8192];
            snprintf(tmp, 8192, "sql: %s\n%d\n", buf, rc);
            throw std::runtime_error(tmp);
        }
    }
}
class StatementContainer
{
public:
    StatementContainer(sqlite3* cache, const char *buf)
    {
        threw = false;
        int rc = sqlite3_prepare_v2(cache, buf, strlen(buf), &stmt, NULL);
        try
        {
            checkthrow(buf, rc);
        }
        catch (std::exception &e)
        {
            sqlite3_finalize(stmt);
            printf("threw: %s\n", e.what());
            throw e;
        }
    }
    ~StatementContainer()
    {
        sqlite3_finalize(stmt);
    }
    sqlite3_stmt* operator*()
    {
        return stmt;
    }
private:
    bool threw;
    sqlite3_stmt* stmt;
};
class DB
{
public:
    bool debug;
    bool readonly;
    DB(const char *dbname, int timeout=2000, bool rd=false)
    {
        debug = false;
        readonly = rd;

        int rc = sqlite3_open_v2(dbname, &cache, readonly ? SQLITE_OPEN_READONLY : (SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE), NULL);
        if (rc != SQLITE_OK && readonly)
        {
            sqlite3_close(cache);
            sqlite3_open_v2(dbname, &cache, SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE, NULL);
            sqlite3_close(cache);
            rc = sqlite3_open_v2(dbname, &cache, SQLITE_OPEN_READONLY, NULL);
        }
        if (rc != SQLITE_OK)
        {
            sqlite3_close(cache);
            cache = NULL;
            char buf[512];
            snprintf(buf, 512, "Couldn't open database: %d", rc);
            throw std::runtime_error(buf);
        }
        else
        {

            sqlite3_extended_result_codes(cache, 1);
            sqlite3_busy_timeout(cache, timeout);
            if (!readonly)
            {
                voidQuery("begin deferred transaction");
                createTables();
            }
        }
    }
    ~DB()
    {
        if (cache)
        {
            if (!readonly)
            {
                while (true)
                {
                    try
                    {
                        voidQuery("commit transaction");
                        break;
                    }
                    catch (std::exception &e)
                    {
                        printf("exception caught in destructor: %s\n", e.what());
                    }
                }
            }
            sqlite3_close(cache);
        }
    }

    void createTables()
    {
        voidQuery("create table if not exists source("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT,"
            "lastmodified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        voidQuery("create table if not exists type("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT)");
        voidQuery("create table if not exists dependency("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "sourceId INTEGER,"
            "dependencyId INTEGER,"
            "FOREIGN KEY(sourceId) REFERENCES source(id),"
            "FOREIGN KEY(dependencyId) REFERENCES source(id))");
        voidQuery("""create table if not exists namespace("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "parentId INTEGER,"
            "name TEXT,"
            "FOREIGN KEY(parentId) REFERENCES namespace(id))");
        voidQuery("create table if not exists inheritance("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "classId INTEGER,"
            "parentId INTEGER)");
        voidQuery("create table if not exists class("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "namespaceId INTEGER DEFAULT -1,"
            "definitionSourceId INTEGER,"
            "definitionLine INTEGER,"
            "definitionColumn INTEGER,"
            "name TEXT,"
            "typeId INTEGER,"
            "usr TEXT,"
            "FOREIGN KEY(namespaceId) REFERENCES namespace(id),"
            "FOREIGN KEY(definitionSourceId) REFERENCES source(id))");
        voidQuery("create table if not exists member("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "classId INTEGER DEFAULT -1,"
            "namespaceId INTEGER DEFAULT -1,"
            "returnId INTEGER,"
            "definitionSourceId INTEGER,"
            "definitionLine INTEGER,"
            "definitionColumn INTEGER,"
            "implementationSourceId INTEGER,"
            "implementationLine INTEGER,"
            "implementationColumn INTEGER,"
            "typeId INTEGER,"
            "name TEXT,"
            "insertionText TEXT,"
            "displayText TEXT,"
            "static BOOL,"
            "access INTEGER,"
            "usr TEXT,"
            "FOREIGN KEY(classId) REFERENCES class(id),"
            "FOREIGN KEY(namespaceId) REFERENCES namespace(id),"
            "FOREIGN KEY(returnId) REFERENCES class(id),"
            "FOREIGN KEY(definitionSourceId) REFERENCES source(id),"
            "FOREIGN KEY(implementationSourceId) REFERENCES source(id),"
            "FOREIGN KEY(typeId) REFERENCES type(id))");
        voidQuery("create table if not exists macro("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "definitionSourceId INTEGER,"
            "definitionLine INTEGER,"
            "definitionColumn INTEGER,"
            "name TEXT,"
            "insertionText TEXT,"
            "displayText TEXT,"
            "usr TEXT,"
            "FOREIGN KEY(definitionSourceId) REFERENCES source(id))");
        voidQuery("create table if not exists templatearguments("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "classId INTEGER,"
            "argumentClassId INTEGER,"
            "argumentNumber INTEGER,"
            "FOREIGN KEY(classId) REFERENCES class(id),"
            "FOREIGN KEY(argumentClassId) REFERENCES class(id))");
        voidQuery("create table if not exists templatedmembers("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "memberId INTEGER,"
            "argumentClassId INTEGER,"
            "argumentNumber INTEGER,"
            "FOREIGN KEY(memberId) REFERENCES member(id),"
            "FOREIGN KEY(argumentClassId) REFERENCES class(id))");
        voidQuery("create table if not exists typedef("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "classId INTEGER,"
            "name TEXT,"
            "FOREIGN KEY(classId) REFERENCES class(id))");
        voidQuery("create table if not exists toscan("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "priority INTEGER,"
            "sourceId INTEGER,"
            "FOREIGN KEY(sourceId) REFERENCES source(id))");
        voidQuery("create unique index if not exists classindex on class (namespaceId, name, typeId, usr)");
        voidQuery("create unique index if not exists memberindex on member(classId, namespaceId, returnId, typeId, name, usr)");
        voidQuery("create unique index if not exists namespaceindex on namespace(name, parentId)");
        voidQuery("create unique index if not exists sourceindex on source(name)");
        voidQuery("create unique index if not exists toscanindex on toscan(sourceId)");
        voidQuery("create unique index if not exists macroindex on macro(usr, name)");

    }

#define QUERYSIZE 8192

    void voidQuery(const char *format, ...)
    {
        char buf[QUERYSIZE];
        va_list v;
        va_start(v, format);
        vsnprintf(buf, QUERYSIZE, format, v);
        va_end(v);
        int rc = SQLITE_BUSY;
        bool wasBusy = false;
        StatementContainer sc(cache, buf);
        rc = sqlite3_step(*sc);
        if (debug)
            printf("%s - rc: %d, %d, %d\n", buf, rc, SQLITE_ROW, SQLITE_DONE);

        while (!readonly && rc == SQLITE_BUSY)
        {
            wasBusy = true;
            printf("busy...%s\n", buf);
            rc = sqlite3_step(*sc);
        }
        if (wasBusy)
            printf("broke out of busy!\n");
        checkthrow(buf, rc);
    }
    int intQuery(const char *format, ...)
    {
        char buf[QUERYSIZE];
        va_list v;
        va_start(v, format);
        vsnprintf(buf, QUERYSIZE, format, v);
        va_end(v);

        int ret = -1;
        StatementContainer sc(cache, buf);
        int rc;

        bool done = false;
        bool wasBusy = false;
        while (!done)
        {
            rc = sqlite3_step(*sc);

            switch (rc)
            {
                case SQLITE_BUSY:
                    done = readonly;
                    break;
                case SQLITE_ROW:
                    ret = sqlite3_column_int(*sc, 0);
                default:
                    done = true;
                    break;
            }
            if (done)
                break;
            wasBusy = true;
            printf("busy spinning...\n");
            usleep(10000);
        }
        if (wasBusy)
            printf("broke out of busy!\n");

        checkthrow(buf, rc);
        if (debug)
            printf("%s - %d rc: %d, %d, %d\n", buf, ret, rc, SQLITE_ROW, SQLITE_DONE);
        return ret;
    }
    sqlite3_stmt* complexQuery(const char *buf)
    {
        sqlite3_stmt *stmt;
        int rc = sqlite3_prepare_v2(cache, buf, strlen(buf), &stmt, NULL);

        try
        {
            checkthrow(buf, rc);
        }
        catch (std::exception &e)
        {
            sqlite3_finalize(stmt);
            stmt = NULL;
            printf("complexQuery exception: %s\n", e.what());
            throw e;
        }
        return stmt; // Remember to call finalize when done!
    }

private:
    sqlite3 *cache;

};




enum DbClassType
{
    NORMAL = 0,
    TEMPLATE_CLASS = 1,
    TEMPLATE_TYPE = 2,
    RETURNED_COMPLEX_TEMPLATE = 3,
    ENUM_CONSTANT = 4,
    SIMPLE_TYPEDEF = 101,
    COMPLEX_TYPEDEF = 102,
};


CXChildVisitResult childcount_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    (*((int*) client_data))++;
    return CXChildVisit_Continue;
}

CXChildVisitResult getchildren_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    std::vector<CXCursor>* children = (std::vector<CXCursor> *) client_data;
    children->push_back(cursor);
    return CXChildVisit_Continue;
}


typedef void (*Callback)(const char *);
class Data
{
private:
public:
    Callback mCallback;

    std::string lastfile;
    bool shouldIndex;
    DB cache;
    std::vector<int> mNamespace;
    std::vector<CXCursor> mParents;
    std::vector<CX_CXXAccessSpecifier> mAccess;
    std::vector<CXCursor> mTemplates;
    std::vector<int>    mTemplateParameter;
    std::vector<int>    mClasses;

public:
    Data(const char *dbname, Callback cb)
    : mCallback(cb), cache(dbname)
    {
        mAccess.push_back(CX_CXXPublic);
    }

    CXCursor get_resolved_cursor(CXCursor self)
    {
        CXCursorKind kind = clang_getCursorKind(self);
        if (kind == CXCursor_TypedefDecl)
        {
            return self;
        }
        CXType result_type = clang_getCursorResultType(self);
        if (result_type.kind == CXType_Record)
        {
            std::vector<CXCursor> children;
            clang_visitChildren(self, getchildren_visitor, &children);
            return get_resolved_cursor(children[0]);
        }
        if (kind == CXCursor_ClassDecl ||
            kind == CXCursor_EnumDecl ||
            kind == CXCursor_TemplateRef ||
            kind == CXCursor_TemplateTypeParameter)
        {
            return self;
        }
        if (clang_isReference(kind))
        {
            CXCursor ref = clang_getCursorReferenced(self);
            if (clang_equalCursors(ref, self))
                return clang_getNullCursor();
            return get_resolved_cursor(ref);
        }
        if (clang_isDeclaration(kind))
        {
            std::vector<CXCursor> children;
            clang_visitChildren(self, getchildren_visitor, &children);
            BOOST_FOREACH(CXCursor child, children)
            {
                CXCursorKind ck = clang_getCursorKind(child);
                switch (ck)
                {
                    default: break;
                    case CXCursor_TypeRef:
                    {
                        CXCursor ref = clang_getCursorReferenced(child);
                        if (clang_equalCursors(ref, child))
                            return clang_getNullCursor();
                        return get_resolved_cursor(ref);
                    }
                    case CXCursor_EnumDecl:
                        return child;
                    case CXCursor_TemplateRef:
                        return self;
                }
            }
        }
        switch (result_type.kind)
        {
            default: break;
            case CXType_Pointer:
            case CXType_LValueReference:
            case CXType_RValueReference:
            {
                return clang_getTypeDeclaration(clang_getPointeeType(result_type));
            }
        }

        return self;
    }
    CXCursor get_returned_cursor(CXCursor self)
    {
        CXCursorKind kind = clang_getCursorKind(self);
        switch (kind)
        {
            default: break;
            case CXCursor_FunctionDecl:
            case CXCursor_FieldDecl:
            case CXCursor_CXXMethod:
            case CXCursor_VarDecl:
            {
                std::vector<CXCursor> children;
                clang_visitChildren(self, getchildren_visitor, &children);
                if (children.size() > 0)
                {
                    CXCursor c = children[0];
                    unsigned int i = 0;
                    while (i+1 < children.size())
                    {
                        CXCursorKind ck = clang_getCursorKind(c);
                        if (ck == CXCursor_NamespaceRef)
                        {
                            i++;
                            c = children[i];
                        }
                        else
                            break;
                    }
                    CXCursorKind ck = clang_getCursorKind(c);
                    if (ck == CXCursor_TemplateRef)
                    {
                        return self;
                    }
                    else if (clang_isReference(ck))
                    {
                        BOOST_FOREACH(CXCursor c, children)
                        {
                            ck = clang_getCursorKind(c);
                            if (ck != CXCursor_NamespaceRef)
                                return get_resolved_cursor(clang_getCursorReferenced(c));
                        }
                    }
                    return clang_getNullCursor();
                }
                else
                {
                    return clang_getNullCursor();
                }
            }
        }
        CXCursor ret = clang_getNullCursor();
        if (clang_isDeclaration(kind))
        {
            ret = self;
        }
        CXType result_type = clang_getCursorResultType(self);

        switch (result_type.kind)
        {
            default: break;
            case CXType_Record:
            {
                std::vector<CXCursor> children;
                clang_visitChildren(self, getchildren_visitor, &children);
                return children[0];
            }
            case CXType_Pointer:
            case CXType_LValueReference:
            case CXType_RValueReference:
            {
                ret = clang_getTypeDeclaration(clang_getPointeeType(result_type));
                if (clang_Cursor_isNull(ret) || clang_isInvalid(clang_getCursorKind(ret)))
                {
                    ret = clang_getTypeDeclaration(clang_getResultType(result_type));
                }
            }
        }
        if (!clang_Cursor_isNull(ret) && !clang_isInvalid(clang_getCursorKind(ret)))
        {
            return get_resolved_cursor(ret);
        }
        return clang_getNullCursor();
    }

    int get_namespace_id()
    {
        if (mNamespace.size() > 0)
        {
            return mNamespace.back();
        }
        return -1;
    }

    int get_source_id(const std::string &str)
    {
        int id = cache.intQuery("select id from source where name=\"%s\"", str.c_str());
        if (id == -1)
        {
            cache.voidQuery("insert into source (name, lastmodified) values (\"%s\", CURRENT_TIMESTAMP)", str.c_str());
            id = cache.intQuery("select id from source where name=\"%s\"", str.c_str());
        }
        return id;
    }

    int get_or_add_namespace_id(const std::string &spelling, int parent=-2)
    {
        if (spelling == "null")
            return -1;
        if (parent == -2)
        {
            parent = get_namespace_id();
        }
        int id = cache.intQuery("select id from namespace where name=\"%s\" and parentId=%d", spelling.c_str(), parent);
        if (id == -1)
        {
            cache.voidQuery("insert into namespace (name, parentId) VALUES(\"%s\", %d)", spelling.c_str(), parent);
            id = cache.intQuery("select id from namespace where name=\"%s\" and parentId=%d", spelling.c_str(), parent);
        }
        return id;
    }

    int get_class_id_from_cursor(CXCursor c)
    {
        if (clang_Cursor_isNull(c))
            return -1;
        std::vector<std::string> path;
        CXCursor c3 = clang_getCursorLexicalParent(c);
        while (!clang_Cursor_isNull(c3))
        {
            CXCursorKind kind = clang_getCursorKind(c3);
            if (clang_isInvalid(kind))
                break;

            if (kind == CXCursor_Namespace)
            {
                CXString str = clang_getCursorSpelling(c3);
                path.push_back(clang_getCString(str));
                clang_disposeString(str);
            }
            CXCursor old = c3;
            c3 = clang_getCursorLexicalParent(c3);
            if (!clang_Cursor_isNull(c3) && clang_equalCursors(c3, old))
                break;
        }
        int ns = -1;
        BOOST_FOREACH(std::string &s, path)
        {
            ns = get_or_add_namespace_id(s, ns);
        }
        return get_or_add_class_id(c, ns);
    }

    int get_or_add_class_id(CXCursor child, int ns = -2)
    {
        DbClassType typeId = NORMAL;
        CXCursorKind kind = clang_getCursorKind(child);
        CXSourceLocation loc = clang_getCursorLocation(child);
        CXFile file;
        unsigned int line;
        unsigned int column;
        clang_getInstantiationLocation(loc, &file, &line, &column, NULL);
        CXString fn;
        const char *str = NULL;
        if (file)
        {
            fn = clang_getFileName(file);
            str = clang_getCString(fn);
        }

        switch (kind)
        {
            default:
                break;
            case CXCursor_TypedefDecl:
            {
                int childcount = 0;
                clang_visitChildren(child, childcount_visitor, &childcount);
                int idCount = 0;
                if (childcount == 1)
                {
                    CXTranslationUnit tu = clang_Cursor_getTranslationUnit(child);
                    CXToken *tokens;
                    unsigned int numTokens;

                    clang_tokenize(tu, clang_getCursorExtent(child), &tokens, &numTokens);
                    for (unsigned int i = 1; numTokens >= 2 && i < numTokens-2; i++)
                    {
                        if (clang_getTokenKind(tokens[i]) == CXToken_Identifier)
                            idCount++;
                    }
                    clang_disposeTokens(tu, tokens, numTokens);
                }

                if (idCount == 1)
                    typeId = SIMPLE_TYPEDEF;
                else
                    typeId = COMPLEX_TYPEDEF;
                break;
            }
            case CXCursor_ClassTemplate:
            {
                typeId = TEMPLATE_CLASS;
                break;
            }
            case CXCursor_TemplateTypeParameter:
            {
                typeId = TEMPLATE_TYPE;
                break;
            }
        }
        if (ns == -2)
        {
            if (typeId != TEMPLATE_TYPE)
                ns = get_namespace_id();
            else
                ns = -1;
        }
        CXString spell = clang_getCursorSpelling(child);
        CXString usr = clang_getCursorUSR(child);
        const char *usrs = clang_getCString(usr);
        const char * name = clang_getCString(spell);
        if (!usrs)
            usrs = "null";
        if (!name)
            name = "null";

        char sql[512];
        snprintf(sql, 512, "select id from class where name='%s' and namespaceId=%d and typeId=%d and usr='%s'",
            name,
            ns,
            typeId,
            usrs
        );
        if (str == NULL)
            str = "<unknown>";
        int id = cache.intQuery(sql);
        if (id == -1)
        {
            cache.voidQuery("insert into class (name, namespaceId, definitionSourceId, definitionLine, definitionColumn, typeId, usr) "
                         "VALUES ('%s', %d, %d, %d, %d, %d, '%s')",
                         name,
                         ns,
                         get_source_id(str),
                         line, column,
                         typeId,
                         usrs
            );
            id = cache.intQuery(sql);
        }
        clang_disposeString(usr);
        clang_disposeString(spell);
        if (file)
            clang_disposeString(fn);

        return id;
    }

};

class TemplatedMemberData
{
public:
    TemplatedMemberData(Data* d, int mem)
    : mData(d), memberId(mem), off(0)
    {

    }
    Data * mData;
    int memberId;
    int off;
};


CXChildVisitResult templatedmembers_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    CXCursorKind kind = clang_getCursorKind(cursor);
    switch (kind)
    {
        case CXCursor_ParmDecl:
        case CXCursor_CompoundStmt:
            return CXChildVisit_Break;
        case CXCursor_TypeRef:
        case CXCursor_TypedefDecl:
        {
            TemplatedMemberData *data = (TemplatedMemberData*) client_data;
            data->mData->cache.voidQuery("insert into templatedmembers (memberId, argumentClassId, argumentNumber) VALUES (%d, %d, %d)",
                data->memberId,
                data->mData->get_class_id_from_cursor(data->mData->get_resolved_cursor(cursor)),
                data->off
            );
            data->off++;
        }
        default:
            return CXChildVisit_Continue;
    }
    return CXChildVisit_Continue;
}



CXChildVisitResult isimplementation_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    if (clang_getCursorKind(cursor) == CXCursor_CompoundStmt)
    {
        *((bool*) client_data) = true;
        return CXChildVisit_Break;
    }

    return CXChildVisit_Continue;
}


CXChildVisitResult inheritance_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;

    CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind == CXCursor_TypeRef)
    {
        CXCursor cl = clang_getCursorReferenced(cursor);
        int classId = -1;
        kind = clang_getCursorKind(cl);
        if (kind == CXCursor_ClassDecl)
        {
            Data * data = (Data*) client_data;
            classId = data->get_class_id_from_cursor(cl);
            int q = data->cache.intQuery("select id from inheritance where classId=%d and parentId=%d", data->mClasses.back(), classId);
            if (q == -1)
            {
                data->cache.voidQuery("insert into inheritance (classId, parentId) values (%d, %d)", data->mClasses.back(), classId);
            }
        }
    }

    return CXChildVisit_Continue;
}

void parse_res(std::string& insertion, std::string& representation, CXCursor cursor)
{
    CXCompletionString comp = clang_getCursorCompletionString(cursor);
    std::string returnType;
    int num = clang_getNumCompletionChunks(comp);
    int placeholderCount = 0;
    bool start = false;
    for (int i = 0; i < num; i++)
    {
        CXCompletionChunkKind kind = clang_getCompletionChunkKind(comp, i);
        CXString str = clang_getCompletionChunkText(comp, i);
        const char *spelling = clang_getCString(str);
        if (!spelling)
            spelling = "";
        if (kind == CXCompletionChunk_TypedText)
        {
            start = true;
        }
        if (kind == CXCompletionChunk_ResultType)
        {
            returnType = spelling;
        }
        else
        {
            representation += spelling;
        }
        if (start && kind != CXCompletionChunk_Informative)
        {
            if (kind == CXCompletionChunk_Placeholder)
            {
                placeholderCount++;
                char buf[512];
                snprintf(buf, 512, "${%d:%s}", placeholderCount, spelling);
                insertion += buf;
            }
            else
                insertion += spelling;
        }
    }
    representation += "\t" + returnType;
}

void dump(CXCursor cursor)
{
    if (clang_Cursor_isNull(cursor))
    {
        printf("NULL");
        return;
    }
    CXString s = clang_getCursorSpelling(cursor);
    const char *str = clang_getCString(s);
    if (str)
    {
        printf("%s - %d\n", str, clang_getCursorKind(cursor));
    }
    clang_disposeString(s);

}

std::string collapse(std::string before, char startT, char endT, char extraT='\0')
{
    int i = before.length();
    int count = 0;
    int end = -1;
    while (i >= 0)
    {
        int a = before.rfind(startT, i-1);
        int b = before.rfind(endT, i-1);
        i = a > b ? a : b;
        if (i == -1)
            break;
        if (before[i] == endT)
        {
            if (i > 0 && (before[i-1] == endT || before[i-1] == extraT))
            {
                i--;
            }
            else
            {
                count++;
                if (end == -1)
                    end = i;
            }
        }
        else if (before[i] == startT)
        {
            if (i > 0 && before[i-1] == startT)
            {
                i--;
            }
            else
            {
                count--;
                if (count == 0 && end != -1)
                {
                    std::string s(before.substr(0, i+1));
                    std::string e(before.substr(end));
                    before = s+e;
                    end = -1;
                }
            }
        }
    }
    return before;
}

CXChildVisitResult visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    Data* data = (Data*) client_data;

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    CXFile file;
    unsigned int line;
    unsigned int column;
    clang_getInstantiationLocation(loc, &file, &line, &column, NULL);

    std::string filename;
    if (file)
    {
        CXString fn = clang_getFileName(file);

        const char * str = clang_getCString(fn);
        if (str)
        {
            filename = str;
            if (data->lastfile != filename)
            {
                bool shouldIndex = true;
                int  id = data->cache.intQuery("select id from source where name=\"%s\"", filename.c_str());

                if (id == -1)
                {
                    id = data->get_source_id(filename);
                    if (id == -1)
                    {
                        printf("sourceid = -1 - %s\n", filename.c_str());
                    }
                    data->cache.voidQuery("insert into toscan (sourceId) values(%d)", id);
                }
                else
                {
                    // TODO: compare last indexed timestamp with modification timestamp
                    // TODO: compare last indexed timestamp with modification timestamp of dependencies

                    shouldIndex = data->cache.intQuery("select id from toscan where sourceId=%d", id) != -1;
                }
                data->lastfile = filename;
                data->shouldIndex = shouldIndex;
                if (data->shouldIndex && data->mCallback)
                {
                   std::string cat(filename);
                   data->mCallback(cat.c_str());
                }
            }
            if (!data->shouldIndex)
                return CXChildVisit_Continue;
        }
        clang_disposeString(fn);
    }


    while (data->mParents.size() && !clang_equalCursors(data->mParents.back(), parent))
    {
        CXCursor oldparent = data->mParents.back();
        data->mParents.pop_back();
        CXCursorKind kind = clang_getCursorKind(oldparent);
        switch (kind)
        {
            default:
                break;
            case CXCursor_Namespace:
                data->mNamespace.pop_back();
                break;
            case CXCursor_ClassDecl:
            case CXCursor_StructDecl:
                data->mClasses.pop_back();
                break;
            case CXCursor_ClassTemplate:
                data->mClasses.pop_back();
                data->mTemplates.pop_back();
                data->mTemplateParameter.pop_back();
                break;
        }
        data->mAccess.pop_back();
    }
    bool recurse = false;
    CXCursorKind kind = clang_getCursorKind(cursor);
    CXString spell = clang_getCursorSpelling(cursor);
    const char *spelling = clang_getCString(spell);
    if (!spelling)
        spelling = "null";
    switch (kind)
    {
        default: break;
        case CXCursor_Namespace:
        {
            data->mNamespace.push_back(data->get_or_add_namespace_id(spelling));
            recurse = true;
            break;
        }

        case CXCursor_ClassTemplate:
        {
            data->mClasses.push_back(data->get_or_add_class_id(cursor));
            data->mTemplates.push_back(cursor);
            data->mTemplateParameter.push_back(0);
            recurse = true;
            break;
        }
        case CXCursor_ClassDecl:
        case CXCursor_StructDecl:
        {
            data->mClasses.push_back(data->get_or_add_class_id(cursor));
            recurse = true;
            break;
        }
        case CXCursor_TemplateTypeParameter:
        {
            int id = data->get_or_add_class_id(cursor);
            int q = data->cache.intQuery("select id from templatearguments where classId=%d and argumentClassId=%d and argumentNumber=%d",
                data->mClasses.back(), id, data->mTemplateParameter.back()
            );
            if (q == -1)
            {
                data->cache.voidQuery("insert into templatearguments (classId, argumentClassId, argumentNumber) VALUES (%d, %d, %d)",
                    data->mClasses.back(), id, data->mTemplateParameter.back()
                );
            }
            data->mTemplateParameter.back()++;
            break;
        }
        case CXCursor_CXXAccessSpecifier:
        {
            data->mAccess.back() = clang_getCXXAccessSpecifier(cursor);
            break;
        }
        case CXCursor_CXXBaseSpecifier:
        {
            clang_visitChildren(cursor, inheritance_visitor, data);
            break;
        }
        case CXCursor_EnumDecl:
        {
            recurse = true;
            break;
        }
        case CXCursor_EnumConstantDecl:
        {
            char sql[512];
            snprintf(sql, 512, "select id from member where name='%s' and typeId=%d", spelling, ENUM_CONSTANT);
            int id = data->cache.intQuery(sql);

            if (id == -1)
            {
                std::string displaytext(spelling);
                displaytext += "\tenum";
                data->cache.voidQuery("insert into member (name, typeId, definitionSourceId, definitionLine, definitionColumn, displayText, insertionText) values ('%s', %d, %d, %d, %d, '%s', '%s')",
                    spelling, ENUM_CONSTANT, data->get_source_id(filename),
                    line, column,
                    displaytext.c_str(), spelling
                );
            }
            else
            {
                data->cache.voidQuery("update member set definitionSourceId=%d, definitionLine=%d, definitionColumn=%d where id=%d",
                    data->get_source_id(filename), line, column, id
                );
            }
            break;
        }
        case CXCursor_TypedefDecl:
        {
            int id = data->get_class_id_from_cursor(cursor);
            std::vector<CXCursor> children;
            clang_visitChildren(cursor, getchildren_visitor , &children);
            if (children.size() == 1)
            {
                CXTranslationUnit tu = clang_Cursor_getTranslationUnit(cursor);
                CXToken *tokens;
                unsigned int numTokens;

                clang_tokenize(tu, clang_getCursorExtent(cursor), &tokens, &numTokens);
                std::string td;
                int idCount = 0;
                for (unsigned int i = 1; numTokens >= 2 && i < numTokens-2; i++)
                {
                    CXTokenKind tk = clang_getTokenKind(tokens[i]);
                    if (tk == CXToken_Keyword)
                    {
                        td += "_";
                        continue;
                    }
                    else if (tk == CXToken_Identifier)
                        idCount += 1;
                    CXString s = clang_getTokenSpelling(tu, tokens[i]);
                    const char *str = clang_getCString(s);
                    if (str)
                        td += str;
                    clang_disposeString(s);
                }
                clang_disposeTokens(tu, tokens, numTokens);
                if (idCount == 1)
                {
                    CXCursor c = clang_getCursorReferenced(children[0]);
                    if (!clang_Cursor_isNull(c) && !clang_isInvalid(clang_getCursorKind(c)))
                    {
                        int pid = data->get_class_id_from_cursor(c);
                        int inh = data->cache.intQuery("select id from inheritance where classId=%d and parentId=%d", id, pid);
                        if (inh == -1)
                        {
                            data->cache.voidQuery("insert into inheritance (classId, parentId) values (%d, %d)", id, pid);
                        }
                    }
                }
                else
                {
                    int idx = td.find("'");
                    while (idx >= 0)
                    {
                        td.replace(idx, 1, "''");
                        idx = td.find("'", idx+2);
                    }
                    int ret = data->cache.intQuery("select id from typedef where classId=%d and name='%s'", id, td.c_str());
                    if (ret == -1)
                    {
                        data->cache.voidQuery("update class set typeId=%d where id=%d", COMPLEX_TYPEDEF, id);
                        data->cache.voidQuery("insert into typedef (classId, name) VALUES (%d, '%s')", id, td.c_str());
                    }
                }
            }
            else if (filename.length() > 0)
            {
                std::string name = "";
                std::vector<int> templateArgs;
                if (children.size())
                {
                    std::vector<CXCursor> template_parameters;
                    BOOST_FOREACH(CXCursor c, children)
                    {
                        bool break2 = false;
                        CXCursorKind ck = clang_getCursorKind(c);
                        switch (ck)
                        {
                            default:
                                break;
                            case CXCursor_NamespaceRef:
                                continue;
                            case CXCursor_TemplateRef:
                            {
                                CXString s = clang_getCursorSpelling(c);
                                const char *str = clang_getCString(s);
                                if (str)
                                    name += str;
                                clang_disposeString(s);
                                name += "<";
                                CXCursor ref = clang_getCursorReferenced(c);
                                templateArgs.push_back(1);  // self
                                template_parameters.push_back(c);
                                std::vector<CXCursor> children2;
                                clang_visitChildren(ref, getchildren_visitor, &children2);
                                BOOST_FOREACH(CXCursor c2, children2)
                                {
                                    CXCursorKind ck2 = clang_getCursorKind(c2);
                                    if (ck2 == CXCursor_TemplateTypeParameter || ck2 == CXCursor_NonTypeTemplateParameter)
                                    {
                                        template_parameters.push_back(c2);
                                        templateArgs.back()++;
                                    }
                                }
                                break;
                            }
                            case CXCursor_TypeRef:
                            {
                                CXString s = clang_getCursorSpelling(clang_getCursorReferenced(c));
                                const char * str = clang_getCString(s);
                                if (str)
                                    name += str;
                                clang_disposeString(s);
                                break;
                            }
                            case CXCursor_ParmDecl:
                            {
                                // A function pointer... Not supported
                                name = "";
                                break2 = true;
                                break;
                            }
                            case CXCursor_IntegerLiteral:
                            case CXCursor_FloatingLiteral:
                            case CXCursor_ImaginaryLiteral:
                            case CXCursor_StringLiteral:
                            case CXCursor_CharacterLiteral:
                            {
                                // It can't resolve to a class for completion anyway so it doesn't matter what we do here
                                name += "_";
                                break;
                            }
                        }
                        if (break2)
                            break;
                        if (templateArgs.size() == 0)
                            break;
                        assert(template_parameters.size());
                        assert(templateArgs.size());
                        template_parameters.erase(template_parameters.begin());
                        templateArgs.back()--;
                        while (templateArgs.size() && templateArgs.back() == 0)
                        {
                            name += "> ";
                            templateArgs.pop_back();
                            if (templateArgs.size())
                            {
                                templateArgs.back()--;
                            }
                        }
                        if (templateArgs.size() && name[name.length()-1] != '<')
                        {
                            name += ",";
                        }
                    }
                    if (templateArgs.size() && template_parameters.size())
                    {
                        // Check if there are default values we can add in to close it out
                        int i = template_parameters.size()-1;
                        while (i >= 0)
                        {
                            assert(i < (int) template_parameters.size());
                            CXCursor par = template_parameters[i];
                            CXCursorKind ck = clang_getCursorKind(par);
                            if (ck == CXCursor_NonTypeTemplateParameter)
                            {
                                name += "_";
                            }
                            else if (ck == CXCursor_TemplateTypeParameter)
                            {
                                CXTranslationUnit tu = clang_Cursor_getTranslationUnit(par);
                                CXToken *tokens;
                                unsigned int numTokens;

                                clang_tokenize(tu, clang_getCursorExtent(par), &tokens, &numTokens);
                                CXCursor first = clang_getNullCursor();
                                if (numTokens)
                                    clang_annotateTokens(tu, tokens, 1, &first);
                                if (clang_equalCursors(first, par)) // TODO: huh??
                                {
                                    for (unsigned int i = 0; i < numTokens; i++)
                                    {
                                        CXTokenKind tk = clang_getTokenKind(tokens[i]);
                                        if (tk == CXToken_Literal)
                                        {
                                            CXString s = clang_getTokenSpelling(tu, tokens[i]);
                                            const char *str = clang_getCString(s);
                                            if (str)
                                                name += str;
                                            clang_disposeString(s);
                                        }
                                    }
                                }
                                clang_disposeTokens(tu, tokens, numTokens);
                            }
                            i--;
                            assert(template_parameters.size());
                            assert(templateArgs.size());
                            template_parameters.erase(template_parameters.begin());
                            templateArgs.back()--;
                            while (templateArgs.size() && templateArgs.back() == 0)
                            {
                                name += "> ";
                                templateArgs.pop_back();
                                if (templateArgs.size())
                                {
                                    templateArgs.back()--;
                                }
                            }
                            if (templateArgs.size() && name[name.length()-1] != '<')
                            {
                                name += ",";
                            }
                            // TODO: original python code had a break here, which is wrong as there could be
                            //       more default template arguments, but without the break I hit an assert
                            //       above due to templateArgs becoming empty. Keeping the break for now
                            //       until I can look at a proper fix
                            break;
                        }
                    }
                }
                else
                {
                    // TODO: hack.. just so that it isn't parsed
                    templateArgs.clear();
                    name = "";
                }
                if (templateArgs.size())
                {
                    // Oops, didn't resolve cleanly
                    // TODO: hack.. mail sent to cfe-dev to ask what to do about it though
                    // http://lists.cs.uiuc.edu/pipermail/cfe-dev/2012-April/020838.html
                    FILE * fp = fopen(filename.c_str(), "rb");
                    if (fp)
                    {
                        CXSourceRange extent = clang_getCursorExtent(cursor);
                        if (!clang_Range_isNull(extent))
                        {
                            unsigned int off;
                            unsigned int length;
                            clang_getInstantiationLocation(clang_getRangeStart(extent), NULL, NULL, NULL, &off);
                            clang_getInstantiationLocation(clang_getRangeEnd(extent), NULL, NULL, NULL, &length);
                            length++;
                            if (length > off)
                            {
                                length -= off;
                                char * filedata = new char[length+1];
                                assert(filedata);
                                fseek(fp, off, SEEK_SET);
                                fread(filedata, length, 1, fp);
                                filedata[length] = '\0';
                                std::string strdata(filedata);
                                delete[] filedata;
                                boost::regex e("typedef\\s+(.*)\\s+(.*);");
                                boost::smatch what;

                                if (boost::regex_match(strdata, what, e, boost::regex_constants::match_not_dot_null))
                                {
                                    name = what.str(1);
                                }
                                else
                                {
                                    name = "";
                                }
                            }
                        }
                        fclose(fp);
                    }
                }
                if (name.length())
                {
                    int idx = name.find("'");
                    while (idx >= 0)
                    {
                        name.replace(idx, 1, "''");
                        idx = name.find("'", idx+2);
                    }
                    int q = data->cache.intQuery("select id from typedef where classId=%d and name='%s'", id, name.c_str());
                    if (q == -1)
                    {
                        data->cache.voidQuery("insert into typedef (classId, name) VALUES (%d, '%s')", id, name.c_str());
                    }
                }
            }
            break;
        }
        case CXCursor_CXXMethod:
        case CXCursor_FieldDecl:
        case CXCursor_VarDecl:
        case CXCursor_FunctionTemplate:
        case CXCursor_FunctionDecl:
        {
            bool implementation = false;
            int classId = -1;
            if (data->mClasses.size())
            {
                classId = data->mClasses.back();
            }
            else if (kind == CXCursor_CXXMethod || kind == CXCursor_FieldDecl)
            {
                classId = data->get_class_id_from_cursor(clang_getCursorSemanticParent(cursor));
            }

            if (kind == CXCursor_CXXMethod || kind == CXCursor_FunctionDecl)
            {
                clang_visitChildren(cursor, isimplementation_visitor, &implementation);
            }
            CXString usr = clang_getCursorUSR(cursor);
            const char * usr_c = clang_getCString(usr);
            if (!usr_c)
                usr_c = "null";
            char sql[512];
            snprintf(sql, 512, "select id from member where name='%s' and classId=%d and namespaceId=%d and usr='%s'",
                spelling, classId, data->get_namespace_id(), usr_c);
            int memberId = data->cache.intQuery(sql);
            if (memberId != -1)
            {
                if (implementation)
                {
                    data->cache.voidQuery("update member set implementationSourceId=%d, implementationLine=%d, implementationColumn=%d where id=%d",
                     data->get_source_id(filename), line, column, memberId);
                }
                else
                {
                    // TODO
                }
            }
            else
            {
                int returnId = -1;
                CXCursor returnCursor = data->get_returned_cursor(cursor);
                CXCursor templateCursor = clang_getNullCursor();
                if (!clang_Cursor_isNull(returnCursor) && !clang_isInvalid(clang_getCursorKind(returnCursor)))
                {
                    if (clang_equalCursors(cursor, returnCursor))
                    {
                        std::vector<CXCursor> children;
                        clang_visitChildren(cursor, getchildren_visitor, &children);
                        int templateCount = 0;
                        BOOST_FOREACH(CXCursor c, children)
                        {
                            CXCursorKind ck = clang_getCursorKind(c);
                            if (ck == CXCursor_TemplateRef)
                            {
                                if (templateCount == 0)
                                {
                                    templateCursor = returnCursor;
                                    returnCursor = clang_getCursorReferenced(c);
                                }
                                templateCount++;
                            }
                            else if (ck != CXCursor_TypeRef && ck != CXCursor_NamespaceRef)
                                break;
                        }
                        if (templateCount > 1 && filename.length())
                        {
                            // TODO: hack... see comment in TypedefDecl
                            // If we get here, it means it's a complex template

                            FILE *fp = fopen(filename.c_str(), "rb");
                            if (fp)
                            {
                                std::string name = "";
                                CXSourceRange extent = clang_getCursorExtent(cursor);
                                unsigned int off;
                                unsigned int length;
                                clang_getInstantiationLocation(clang_getRangeStart(extent), NULL, NULL, NULL, &off);
                                clang_getInstantiationLocation(clang_getRangeEnd(extent), NULL, NULL, NULL, &length);
                                length++;
                                if (length > off)
                                {
                                    length -= off;
                                    char * filedata = new char[length+1];
                                    fseek(fp, off, SEEK_SET);
                                    fread(filedata, length, 1, fp);
                                    filedata[length] = '\0';
                                    std::string strdata(filedata);
                                    delete[] filedata;
                                    if (strdata.find("template") == 0)
                                    {
                                        std::string collapsed = collapse(
                                                collapse(
                                                    collapse(strdata, '{', '}'),
                                                '(', ')'),
                                        '<','>','-');

                                        boost::regex e("template\\s*<.*>\\s+((const\\s+)?typename\\s+)?(.+?)\\s+([^\\s]+)::");
                                        boost::smatch what;

                                        if (boost::regex_search(collapsed, what, e, boost::regex_constants::match_not_dot_null))
                                        {
                                            name = what.str(3);
                                            int i1 = name.find("<");
                                            int i2 = name.find(">");
                                            if (i1 >= 0 && i2 >= 0)
                                            {
                                                char buf[512];
                                                snprintf(buf, 512, "(%s.*?%s)", name.substr(0, i1+1).c_str(), name.substr(i2).c_str());
                                                boost::regex e2(buf);
                                                boost::regex_search(strdata, what, e2, boost::regex_constants::match_not_dot_null);
                                                name = what.str(1);
                                            }
                                        }
                                        else
                                        {
                                            printf("filedata: %s\n", strdata.c_str());
                                        }
                                    }
                                    else
                                    {
                                        boost::regex e("\\s*(.+)\\s+(.+);");
                                        boost::smatch what;
                                        if (boost::regex_search(strdata, what, e, boost::regex_constants::match_not_dot_null))
                                        {
                                            name = what.str(1);
                                        }
                                    }
                                    if (name.length())
                                    {
                                        // NOTE: intentionally using the classId as the namespaceId for the complex template return type
                                        char sql[512];
                                        snprintf(sql, 512, "select id from class where namespaceId=%d and typeId=%d and name='%s'",
                                            classId, RETURNED_COMPLEX_TEMPLATE, name.c_str());
                                        int id = data->cache.intQuery(sql);
                                        if (id == -1)
                                        {
                                            data->cache.voidQuery("insert into class (name, namespaceId, typeId) VALUES ('%s', %d, %d)",
                                                    name.c_str(), classId, RETURNED_COMPLEX_TEMPLATE
                                            );
                                            id = data->cache.intQuery(sql);
                                        }
                                        returnId = id;
                                        templateCursor = clang_getNullCursor();
                                    }
                                }
                                fclose(fp);
                            }
                        }
                    }

                    if (returnId == -1 && !clang_equalCursors(cursor, returnCursor))
                    {
                        returnId = data->get_class_id_from_cursor(returnCursor);
                    }
                }
                bool stat = false;
                if (kind == CXCursor_CXXMethod)
                    stat = clang_CXXMethod_isStatic(cursor);

                std::string displayText;
                std::string insertionText;
                parse_res(insertionText, displayText, cursor);
                data->cache.voidQuery("insert into member (namespaceId, classId, returnId, definitionSourceId, definitionLine, definitionColumn, name, displayText, insertionText, static, access, usr) values (%d, %d, %d, %d, %d, %d, '%s', '%s', '%s', %d, %d, '%s')",
                    data->get_namespace_id(), classId, returnId, data->get_source_id(filename),
                    line, column, spelling,
                    displayText.c_str(),
                    insertionText.c_str(),
                    stat, data->mAccess.back(),
                    usr_c
                );
                if (!clang_Cursor_isNull(templateCursor))
                {
                    TemplatedMemberData tdata(data, data->cache.intQuery(sql));
                    clang_visitChildren(templateCursor, templatedmembers_visitor, &tdata);
                }
            }
            clang_disposeString(usr);
            break;
        }
        case CXCursor_MacroDefinition:
        {
            CXString usr = clang_getCursorUSR(cursor);
            CXString displayname = clang_getCursorDisplayName(cursor);
            const char *disp_c = clang_getCString(displayname);
            if (!disp_c)
                disp_c = "null";
            const char * usr_c = clang_getCString(usr);
            if (!usr_c)
                usr_c = "null";
            int id = data->cache.intQuery("select id from macro where usr='%s'", usr_c);
            if (id == -1)
            {
                data->cache.voidQuery("insert into macro (definitionSourceId, definitionLine, definitionColumn, usr, displayText, insertionText, name) values (%d, %d, %d, '%s', '%s', '%s', '%s')",
                    data->get_source_id(filename), line, column, usr_c, (std::string(disp_c)+std::string("\tmacro")).c_str(), disp_c, disp_c
                );
            }
            else
            {
                data->cache.voidQuery("update macro set definitionSourceId=%d, definitionLine=%d, definitionColumn=%d where id=%d",
                    data->get_source_id(filename), line, column, id
                );
            }
            clang_disposeString(usr);
            clang_disposeString(displayname);
            break;
        }
        case CXCursor_UnexposedDecl:
        {
            // extern "C" for example
            recurse = true;
            break;
        }
    }
    clang_disposeString(spell);

    if (recurse)
    {
        data->mAccess.push_back(CX_CXXPrivate);
        data->mParents.push_back(cursor);
        return CXChildVisit_Recurse;
    }

    return CXChildVisit_Continue;
}

extern "C"
{

void *createDB(const char *database, int timeout, bool readonly)
{
    DB * ret = NULL;
    try
    {
        ret = new DB(database, timeout, readonly);
        printf("created: %p\n", ret);
    }
    catch (std::exception &e)
    {
        printf("exception: %s\n", e.what());
    }
    return ret;
}
void deleteDB(void *db)
{
    printf("delete: %p\n", db);
    delete (DB*) db;
}
void db_voidQuery(void*db, const char *q)
{
    DB* d = (DB*) db;
    try
    {
        d->voidQuery(q);
    }
    catch (std::exception &e)
    {
        printf("exception: %s\n", e.what());
    }
}
int db_intQuery(void *db, const char *q)
{
    DB* d = (DB*) db;
    int ret = -1;
    try
    {
        ret = d->intQuery(q);
    }
    catch (std::exception &e)
    {
        printf("exception: %s\n", e.what());
    }
    return ret;
}

sqlite3_stmt* db_complexQuery(void *db, const char*q)
{
    DB* d = (DB*) db;
    sqlite3_stmt* stmt = NULL;

    try
    {
        stmt = d->complexQuery(q);
        int rc = sqlite3_step(stmt);
        if (rc != SQLITE_ROW)
        {
            printf("will return NULL from complexQuery: %d - %s\n", rc, q);
            sqlite3_finalize(stmt);
            stmt = NULL;
        }
    }
    catch (std::exception &e)
    {
        printf("exception: %s\n", e.what());
        if (stmt)
            sqlite3_finalize(stmt);
        stmt = NULL;
    }
    return stmt;
}

void db_doneQuery(sqlite3_stmt* stmt)
{
    sqlite3_finalize(stmt);
}

int db_stepQuery(sqlite3_stmt* stmt)
{
    return sqlite3_step(stmt);
}

int db_getIntColumn(sqlite3_stmt* stmt, int column)
{
    return sqlite3_column_int(stmt, column);
}

const unsigned char* db_getStringColumn(sqlite3_stmt* stmt, int column)
{
    return sqlite3_column_text(stmt, column);
}

int db_getColumnType(sqlite3_stmt* stmt, int column)
{
    return sqlite3_column_type(stmt, column);
}

int db_getColumnCount(sqlite3_stmt* stmt)
{
    return sqlite3_column_count(stmt);
}

void nativeindex(const char *database, CXCursor c, Callback cb)
{
    try
    {
        Data data(database, cb);
        clang_visitChildren(c, visitor, &data);
        data.cache.voidQuery("delete from toscan");
    }
    catch (std::exception &e)
    {
        printf("exception: %s\n", e.what());
    }
}

}

