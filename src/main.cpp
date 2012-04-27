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
#include <vector>
#include <boost/foreach.hpp>
#include <sys/time.h>

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


void parse_res(std::string& insertion, std::string& representation, CXCursor cursor)
{
    CXCursorKind ck = clang_getCursorKind(cursor);
    std::string returnType;
    switch (ck)
    {
        default: break;
        case CXCursor_ClassDecl: returnType = "class"; break;
        case CXCursor_EnumDecl: returnType = "enum"; break;
        case CXCursor_StructDecl: returnType = "struct"; break;
        case CXCursor_MacroDefinition: returnType = "macro"; break;
        case CXCursor_Namespace: returnType = "namespace"; break;
        case CXCursor_TypedefDecl: returnType = "typedef"; break;
    }

    if (ck != CXCursor_MacroDefinition && ck != CXCursor_Namespace)
    {
        CXCompletionString comp = clang_getCursorCompletionString(cursor);
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
    }
    else
    {
        CXString s = clang_getCursorSpelling(cursor);
        const char *str = clang_getCString(s);
        if (str)
        {
            representation += str;
            insertion += str;
        }
        clang_disposeString(s);
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


timeval start;

double getTime()
{
    timeval t;
    gettimeofday(&t, NULL);
    return (t.tv_sec - start.tv_sec) * 1000.0 + (t.tv_usec - start.tv_usec) * (1.0 / 1000.0);
}

class Entry
{
public:
    Entry(CXCursor c, std::string &disp, std::string &ins)
    : cursor(c)
    {
        display = new char[disp.length()+1];
        memcpy(display, disp.c_str(), disp.length()+1);
        insert = new char[ins.length()+1];
        memcpy(insert, ins.c_str(), ins.length()+1);
    }
    ~Entry()
    {
        delete[] display;
        delete[] insert;
    }
    bool operator==(const Entry& other) const
    {
        return strcmp(display, other.display) == 0 && strcmp(insert, other.insert) == 0;
    }
    CXCursor cursor;
    char * insert;
    char * display;
};


void trim(std::vector<Entry*>& mEntries)
{
    float t1 = getTime();
    for (std::vector<Entry*>::iterator i = mEntries.begin(); i < mEntries.end(); i++)
    {
        while ((*i)->display[0] == '\t')
        {
            delete *i;
            mEntries.erase(i);
        }
    }
    for (std::vector<Entry*>::iterator i = mEntries.begin()+1; i < mEntries.end(); i++)
    {
        while ((*(*i)) == (*(*(i-1))))
        {
            delete *i;
            mEntries.erase(i);
        }
    }
    float t2 = getTime();
    printf("removing duplicates: %f ms\n", t2-t1);
}

class EntryCompare
{
public:
    bool operator()(const Entry *a, const Entry *b) const
    {
        if (!b)
            return false;
        return strcmp(a->display, b->display) < 0;
    }
};
class EntryStringCompare
{
public:

    bool operator()(const Entry *a, const char *str) const
    {
        return strncmp(a->display, str, strlen(str)) < 0;
    }
    bool operator()(const char *str, const Entry *a) const
    {
        return strncmp(a->display, str, strlen(str)) > 0;
    }
};

class CacheCompletionResults
{
public:
    CacheCompletionResults(std::vector<Entry*>::iterator start, std::vector<Entry*>::iterator end, bool de=false)
    : deleteEntries(de)
    {
        length = end-start;
        entries = new Entry*[length];
        int i = 0;
        while (start < end)
        {
            entries[i] = *start;
            start++;
            i++;
        }
    }
    ~CacheCompletionResults()
    {
        if (deleteEntries)
        {
            for (unsigned int i = 0; i < length; i++)
            {
                delete entries[i];
            }
        }
        delete[] entries;
    }

    Entry** entries;
    unsigned int length;
    bool deleteEntries;
};

CXChildVisitResult get_completion_children(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    bool recurse = false;
    CXCursorKind ck = clang_getCursorKind(cursor);
    switch (ck)
    {
        default: break;
        case CXCursor_UnexposedDecl: // extern "C" for example
            recurse = true;
            break;
        case CXCursor_EnumDecl:
            recurse = true;
            // fall through
        case CXCursor_Namespace:
        case CXCursor_ClassDecl:
        case CXCursor_CXXMethod:
        case CXCursor_EnumConstantDecl:
        case CXCursor_TypedefDecl:
        case CXCursor_FunctionDecl:
        case CXCursor_FunctionTemplate:
        case CXCursor_StructDecl:
        case CXCursor_FieldDecl:
        case CXCursor_VarDecl:
        case CXCursor_MacroDefinition:
        {
            std::vector<Entry*>* entries = (std::vector<Entry*>*) client_data;
            std::string ins;
            std::string disp;
            parse_res(ins, disp, cursor);
            entries->push_back(new Entry(cursor, disp, ins));
            break;
        }
    }

    if (recurse)
    {
        return CXChildVisit_Recurse;
    }
    return CXChildVisit_Continue;
}

class NamespaceVisitorData
{
public:
    NamespaceVisitorData(CXCursor base, const char **ns, unsigned int nsLength)
    : namespaces(ns), namespaceCount(nsLength)
    {
        clang_visitChildren(base, &visitor, this);
        std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
        trim(mEntries);
    }
    ~NamespaceVisitorData()
    {
        // Note: intentionally not freeing mEntries as the CacheCompletionResults
        //       created later will take ownership
    }
    static CXChildVisitResult visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
    {
        if (clang_Cursor_isNull(cursor))
            return CXChildVisit_Break;
        NamespaceVisitorData *nvd = (NamespaceVisitorData*) client_data;

        while (nvd->mParents.size() && !clang_equalCursors(nvd->mParents.back(), parent))
        {
            nvd->mParents.pop_back();
        }

        CXCursorKind ck = clang_getCursorKind(cursor);
        bool recurse = false;

        switch (ck)
        {
            default: break;
            case CXCursor_Namespace:
            {
                if (nvd->mParents.size() < nvd->namespaceCount)
                {
                    CXString s = clang_getCursorSpelling(cursor);
                    const char *str = clang_getCString(s);
                    if (str)
                    {
                        if (!strcmp(nvd->namespaces[nvd->mParents.size()], str))
                        {
                            recurse = true;
                        }
                    }
                    clang_disposeString(s);
                }
                break;
            }
        }
        if (nvd->mParents.size() && clang_equalCursors(nvd->mParents.back(), clang_getCursorSemanticParent(cursor)))
        {
            switch (ck)
            {
                default: break;
                case CXCursor_EnumDecl:
                    recurse = true;
                case CXCursor_Namespace:
                case CXCursor_ClassDecl:
                case CXCursor_CXXMethod:
                case CXCursor_EnumConstantDecl:
                case CXCursor_TypedefDecl:
                case CXCursor_FunctionDecl:
                case CXCursor_FunctionTemplate:
                case CXCursor_StructDecl:
                case CXCursor_FieldDecl:
                case CXCursor_VarDecl:
                case CXCursor_MacroDefinition:
                {
                    std::string ins;
                    std::string disp;
                    parse_res(ins, disp, cursor);
                    nvd->mEntries.push_back(new Entry(cursor, disp, ins));
                    break;
                }
            }
        }
        if (recurse)
        {
            nvd->mParents.push_back(cursor);
            return CXChildVisit_Recurse;
        }

        return CXChildVisit_Continue;
    }

    std::vector<Entry*> &getEntries()
    {
        return mEntries;
    }

private:
    std::vector<CXCursor> mParents;
    std::vector<Entry*> mEntries;
    const char **namespaces;
    unsigned int namespaceCount;
};


class FindData
{
public:
    FindData(const char* s)
    : found(false), spelling(s)
    {

    }
    static CXChildVisitResult visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
    {
        if (clang_Cursor_isNull(cursor))
            return CXChildVisit_Break;
        CXCursorKind ck = clang_getCursorKind(cursor);
        switch (ck)
        {
            default: break;
            case CXCursor_StructDecl:
            case CXCursor_ClassDecl:
            {
                CXString s = clang_getCursorSpelling(cursor);
                const char *str = clang_getCString(s);
                if (str)
                {
                    FindData* data = (FindData*) client_data;
                    if (!strcmp(str, data->spelling))
                    {
                        data->cursor = cursor;
                        data->found = true;
                        return CXChildVisit_Break;
                    }
                }
                clang_disposeString(s);
                break;
            }
        }
        return CXChildVisit_Continue;
    }
    CXCursor cursor;
    bool found;
    const char *spelling;
};

class Cache
{
public:
    Cache(CXCursor base)
    : mBaseCursor(base)
    {
        float t1 = getTime();
        clang_visitChildren(base, get_completion_children, &mEntries);
        float t2 = getTime();
        printf("quick visit: %f ms\n", t2-t1);

        t1 = getTime();
        std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
        t2 = getTime();
        printf("sort: %f ms\n", t2-t1);
        trim(mEntries);
    }
    ~Cache()
    {
        BOOST_FOREACH(Entry *e, mEntries)
        {
            delete e;
        }
        mEntries.clear();
    }

    void cleanup()
    {
    }
    CacheCompletionResults* complete(const char *prefix)
    {
        std::vector<Entry*>::iterator start = std::lower_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());
        std::vector<Entry*>::iterator end = std::upper_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());

        return new CacheCompletionResults(start, end);
    }

    CacheCompletionResults* getNamespaceMembers(const char **ns, unsigned int nsLength)
    {
        float t1 = getTime();
        NamespaceVisitorData d(mBaseCursor, ns, nsLength);
        float t2 = getTime();
        printf("complete namespace: %f ms\n", t2-t1);
        std::vector<Entry*>& entries = d.getEntries();
        return new CacheCompletionResults(entries.begin(), entries.end(), true);
    }
private:
    CXCursor            mBaseCursor;
    std::vector<Entry*> mEntries;
};


extern "C"
{

CacheCompletionResults* cache_completeNamespace(Cache* cache, const char **namespaces, unsigned int length)
{
    return cache->getNamespaceMembers(namespaces, length);
}

CacheCompletionResults* cache_complete_startswith(Cache* cache, const char *prefix)
{
    return cache->complete(prefix);
}
void cache_disposeCompletionResults(CacheCompletionResults *comp)
{
    delete comp;
}

Cache* createCache(CXCursor base)
{
    gettimeofday(&start, NULL);
    return new Cache(base);
}

void deleteCache(Cache *cache)
{
    delete cache;
}

}

