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
#include <string.h>
#include <vector>
#include <map>
#include <algorithm>


#if _WIN32
   #define snprintf _snprintf_s
   #define EXPORT __declspec(dllexport)
#else
   #define EXPORT
#endif

bool operator<(const CXCursor &c1, const CXCursor &c2)
{
    CXString s1 = clang_getCursorUSR(c1);
    CXString s2 = clang_getCursorUSR(c2);
    const char *cstr1 = clang_getCString(s1);
    const char *cstr2 = clang_getCString(s2);
    bool ret = strcmp(cstr1, cstr2) < 0;
    clang_disposeString(s1);
    clang_disposeString(s2);
    return ret;
}

typedef std::vector<CXCursor> CursorList;
typedef std::map<CXCursor, CursorList> CategoryContainer;


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

CXChildVisitResult get_first_child_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    *((CXCursor*) client_data) = cursor;
    return CXChildVisit_Break;
}

CXChildVisitResult get_objc_categories_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind == CXCursor_ObjCCategoryDecl)
    {
        CXCursor child = clang_getNullCursor();
        clang_visitChildren(cursor, get_first_child_visitor, &child);
        if (!clang_Cursor_isNull(child))
        {
            CXCursor ref = clang_getCursorReferenced(child);
            if (!clang_Cursor_isNull(ref))
            {
                CategoryContainer* cont = (CategoryContainer*) client_data;
                CategoryContainer::iterator i = cont->find(ref);
                if (i == cont->end())
                {
                    CursorList add;
                    (*cont)[ref] = add;
                }
                (*cont)[ref].push_back(cursor);
            }
        }
    }
    return CXChildVisit_Continue;
}



CXChildVisitResult haschildren_visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    *((bool*)client_data) = true;
    return CXChildVisit_Break;
}

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
    CursorList* children = (CursorList *) client_data;
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
        CursorList children;
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
        CursorList children;
        clang_visitChildren(self, getchildren_visitor, &children);
        for (CursorList::iterator i = children.begin(); i != children.end(); ++i)
        {
            CXCursor &child = *i;
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
            CursorList children;
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
                    for (CursorList::iterator i = children.begin(); i != children.end(); ++i)
                    {
                        CXCursor &c = *i;
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
            CursorList children;
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

void get_return_type(std::string& returnType, CXCursorKind ck)
{
    switch (ck)
    {
        default: break;
        case CXCursor_UnionDecl: returnType = "union"; break;
        case CXCursor_ObjCInterfaceDecl: // fall through
        case CXCursor_ClassTemplate: // fall through
        case CXCursor_ClassDecl: returnType = "class"; break;
        case CXCursor_EnumDecl: returnType = "enum"; break;
        case CXCursor_StructDecl: returnType = "struct"; break;
        case CXCursor_MacroDefinition: returnType = "macro"; break;
        case CXCursor_Namespace: returnType = "namespace"; break;
        case CXCursor_TypedefDecl: returnType = "typedef"; break;
    }
}

void parse_res(std::string& returnType, std::string& insertion, std::string& representation, CXCompletionString comp)
{
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
        clang_disposeString(str);
    }
    representation += "\t" + returnType;
}

void parse_res(std::string& insertion, std::string& representation, CXCursorKind ck, CXCompletionString comp)
{
    std::string returnType;
    get_return_type(returnType, ck);
    parse_res(returnType, insertion, representation, comp);
}

void parse_res(std::string& insertion, std::string& representation, CXCursor cursor)
{
    CXCursorKind ck = clang_getCursorKind(cursor);
    std::string returnType;
    get_return_type(returnType, ck);
    if (ck != CXCursor_MacroDefinition && ck != CXCursor_Namespace)
    {
        CXCompletionString comp = clang_getCursorCompletionString(cursor);
        parse_res(returnType, insertion, representation, comp);
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
        representation += "\t" + returnType;
    }
}

std::string collapse(std::string before, char startT, char endT, char extraT='\0')
{
    int i = (int) before.length();
    int count = 0;
    int end = -1;
    while (i >= 0)
    {
        int a = (int) before.rfind(startT, i-1);
        int b = (int) before.rfind(endT, i-1);
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

class Entry
{
public:
    Entry(CXCursor c, std::string &disp, std::string &ins, CX_CXXAccessSpecifier a=CX_CXXPublic, bool base=false)
    : cursor(c), access(a), isStatic(false), isBaseClass(base)
    {
        display = new char[disp.length()+1];
        memcpy(display, disp.c_str(), disp.length()+1);
        insert = new char[ins.length()+1];
        memcpy(insert, ins.c_str(), ins.length()+1);

        if (!clang_Cursor_isNull(c))
        {
            CXCursorKind ck = clang_getCursorKind(c);
            switch (ck)
            {
                case CXCursor_CXXMethod: isStatic = clang_CXXMethod_isStatic(c); break;
                case CXCursor_VarDecl: isStatic = true; break;
                case CXCursor_ObjCClassMethodDecl: isStatic = true; break;
                default: isStatic = false; break;
            }
        }
    }
    Entry(const Entry& other)
    : cursor(other.cursor), access(other.access), isStatic(other.isStatic), isBaseClass(other.isBaseClass)
    {
        display = new char[strlen(other.display)+1];
        memcpy(display, other.display, strlen(other.display)+1);
        insert = new char[strlen(other.insert)+1];
        memcpy(insert, other.insert, strlen(other.insert)+1);
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
    CX_CXXAccessSpecifier access;
    bool isStatic;
    bool isBaseClass;
};


void trim(std::vector<Entry*>& mEntries)
{
    std::vector<Entry*>::iterator i = mEntries.begin();
    // Trim nameless completions
    while (i != mEntries.end() && (*i)->display[0] == '\t')
    {
        delete *i;
        mEntries.erase(i);
        i = mEntries.begin();
    }
    // Trim duplicates
    if (mEntries.begin() == mEntries.end())
        return;
    for (std::vector<Entry*>::iterator i = mEntries.begin()+1; i != mEntries.end(); i++)
    {
        while (i != mEntries.end() && (*(*i)) == (*(*(i-1))))
        {
            std::vector<Entry*>::iterator del = i;
            bool hasChildren = false;
            // Just to make sure that a forward declaration rather than the
            // real declaration is removed as a duplicate
            if (clang_getCursorKind((*del)->cursor) != CXCursor_ObjCImplementationDecl)
                clang_visitChildren((*del)->cursor, haschildren_visitor, &hasChildren);
            if (hasChildren)
                del = i-1;
            bool begin = del == mEntries.begin();
            if (!begin)
                i = del-1;
            delete *del;
            mEntries.erase(del);
            if (begin)
            {
                i = mEntries.begin();
            }
            i++;
        }
    }
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
        length = (unsigned int) (end-start);
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

class CompletionVisitorData
{
public:
    CompletionVisitorData(std::vector<Entry*>& e, CX_CXXAccessSpecifier a=CX_CXXPrivate, bool base=false)
    : entries(e), access(a), isBaseClass(base)
    {
    }
    CursorList mParents;
    std::vector<Entry*> &entries;
    CX_CXXAccessSpecifier access;
    bool isBaseClass;
};

void add_completion_children(CXCursor cursor, CXCursorKind ck, bool &recurse, CompletionVisitorData* data)
{
    switch (ck)
    {
        default: break;
        case CXCursor_CXXAccessSpecifier:
            data->access = clang_getCXXAccessSpecifier(cursor);
            break;
        case CXCursor_UnexposedDecl: // extern "C" for example
            recurse = true;
            break;
        case CXCursor_UnionDecl:
        case CXCursor_EnumDecl:
            recurse = true;
            // fall through
        case CXCursor_Namespace:
        case CXCursor_ObjCInterfaceDecl:
        case CXCursor_ObjCIvarDecl:
        case CXCursor_ObjCPropertyDecl:
        case CXCursor_ObjCClassMethodDecl:
        case CXCursor_ObjCInstanceMethodDecl:
        case CXCursor_ClassTemplate:
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
            if (ins.length() != 0)
                data->entries.push_back(new Entry(cursor, disp, ins, data->access, data->isBaseClass));
            break;
        }
    }
}

CXChildVisitResult get_completion_children(CXCursor cursor, CXCursor parent, CXClientData client_data)
{
    if (clang_Cursor_isNull(cursor))
        return CXChildVisit_Break;
    bool recurse = false;
    CXCursorKind ck = clang_getCursorKind(cursor);
    CompletionVisitorData* data = (CompletionVisitorData*) client_data;

    add_completion_children(cursor, ck, recurse, data);
    switch (ck)
    {
        case CXCursor_CXXBaseSpecifier:
        case CXCursor_ObjCSuperClassRef:
        case CXCursor_ObjCProtocolRef:
        {
            CXCursor ref = clang_getCursorReferenced(cursor);
            if (!clang_Cursor_isNull(ref) && !clang_isInvalid(clang_getCursorKind(ref)))
            {
                data->mParents.push_back(ref);
                CompletionVisitorData d(data->entries, ck == CXCursor_CXXBaseSpecifier ? CX_CXXPrivate : CX_CXXProtected, true);
                if (clang_getCursorKind(ref) == CXCursor_StructDecl)
                {
                    d.access = CX_CXXPublic;
                }
                clang_visitChildren(ref, get_completion_children, &d);
                for (CursorList::iterator i = d.mParents.begin(); i != d.mParents.end(); i++)
                {
                    data->mParents.push_back(*i);
                }
            }
            break;
        }
        default: break;
    }

    if (recurse)
    {
        return CXChildVisit_Recurse;
    }
    return CXChildVisit_Continue;
}

class NamespaceFinder
{
public:
    NamespaceFinder(CXCursor base, const char ** ns, unsigned int nsLength)
    : mBase(base), namespaces(ns), namespaceCount(nsLength)
    {

    }
    virtual void execute()
    {
        clang_visitChildren(mBase, &NamespaceFinder::visitor, this);
    }

    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck) = 0;

protected:
    CXCursor mBase;
    CursorList mParents;
    const char **namespaces;
    unsigned int namespaceCount;

    static CXChildVisitResult visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
    {
        if (clang_Cursor_isNull(cursor))
            return CXChildVisit_Break;
        NamespaceFinder *nvd = (NamespaceFinder*) client_data;

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
        if (nvd->namespaceCount == 0 || (nvd->mParents.size() == nvd->namespaceCount && clang_equalCursors(nvd->mParents.back(), parent)))
        {
            bool bk = nvd->visitor(cursor, parent, recurse, ck);
            if (bk)
                return CXChildVisit_Break;
        }

        if (recurse)
        {
            nvd->mParents.push_back(cursor);
            return CXChildVisit_Recurse;
        }
        return CXChildVisit_Continue;
    }

};

class NamespaceVisitorData : public NamespaceFinder
{
public:
    NamespaceVisitorData(std::vector<Entry*> &namespaces, const char* firstName, const char **ns, unsigned int nsLength)
    : NamespaceFinder(clang_getNullCursor(), ns, nsLength),  mFirstName(firstName), mNamespaces(namespaces)
    {
    }
    ~NamespaceVisitorData()
    {
        // Note: intentionally not freeing mEntries as the CacheCompletionResults
        //       created later will take ownership
    }
    virtual void execute()
    {
        std::vector<Entry*>::iterator start = std::lower_bound(mNamespaces.begin(), mNamespaces.end(), mFirstName, EntryStringCompare());
        std::vector<Entry*>::iterator end = std::upper_bound(mNamespaces.begin(), mNamespaces.end(), mFirstName, EntryStringCompare());
        while (start < end)
        {
            clang_visitChildren((*start)->cursor, NamespaceFinder::visitor, this);
            start++;
        }

        std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
        trim(mEntries);
    }

    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck)
    {
        CompletionVisitorData d(mEntries, CX_CXXPublic);
        add_completion_children(cursor, ck, recurse, &d);
        return false;
    }

    std::vector<Entry*> &getEntries()
    {
        return mEntries;
    }

private:
    const char *mFirstName;
    std::vector<Entry*> &mNamespaces;
    std::vector<Entry*> mEntries;
};


class FindData : public NamespaceFinder
{
public:
    FindData(CXCursor base, const char **namespaces, unsigned int nsLength, const char* s)
    : NamespaceFinder(base, namespaces, nsLength), mFound(false), mSpelling(s)
    {

    }
    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck)
    {
        switch (ck)
        {
            default: break;
            case CXCursor_ClassTemplate:
            case CXCursor_StructDecl:
            case CXCursor_ClassDecl:
            case CXCursor_TypedefDecl:
            {
                CXString s = clang_getCursorSpelling(cursor);
                const char *str = clang_getCString(s);
                if (str)
                {
                    if (!strcmp(str, mSpelling))
                    {
                        bool hasChildren = false;
                        clang_visitChildren(cursor, haschildren_visitor, &hasChildren);
                        if (hasChildren)
                        {
                            mCursor = cursor;
                            mFound = true;
                        }
                    }
                }
                clang_disposeString(s);
                break;
            }
        }
        return mFound;
    }
    CXCursor getCursor()
    {
        if (mFound)
            return mCursor;
        return clang_getNullCursor();
    }

private:
    CXCursor mCursor;
    bool mFound;
    const char *mSpelling;
};

class Cache
{
public:
    Cache(CXCursor base)
    : mBaseCursor(base)
    {
        CompletionVisitorData d(mEntries, CX_CXXPublic);
        clang_visitChildren(base, get_completion_children, &d);

        std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
        for (std::vector<Entry*>::iterator i = mEntries.begin(); i != mEntries.end(); ++i)
        {
            Entry *e = *i;
            CXCursorKind ck = clang_getCursorKind(e->cursor);
            if (ck == CXCursor_Namespace)
            {
                mNamespaces.push_back(new Entry(*e));
            }
        }
        trim(mEntries);
        clang_visitChildren(base, get_objc_categories_visitor, &mObjCCategories);
    }
    ~Cache()
    {
        for (std::vector<Entry*>::iterator i = mEntries.begin(); i != mEntries.end(); ++i)
        {
            delete *i;
        }
        mEntries.clear();
        for (std::vector<Entry*>::iterator i = mNamespaces.begin(); i != mNamespaces.end(); ++i)
        {
            delete *i;
        }
        mNamespaces.clear();
    }
    bool isMemberKind(CXCursorKind ck)
    {
        switch (ck)
        {
            default: return false;
            case CXCursor_CXXMethod:
            case CXCursor_NotImplemented:
            case CXCursor_FieldDecl:
            case CXCursor_ObjCPropertyDecl:
            case CXCursor_ObjCClassMethodDecl:
            case CXCursor_ObjCInstanceMethodDecl:
            case CXCursor_ObjCIvarDecl:
            case CXCursor_FunctionTemplate:
                return true;
        }
    }
    CacheCompletionResults* clangComplete(const char *filename, unsigned int row, unsigned int col, CXUnsavedFile* unsaved, unsigned int usLength, bool memberCompletion)
    {
        CXCodeCompleteResults* res =  clang_codeCompleteAt(clang_Cursor_getTranslationUnit(mBaseCursor) , filename, row, col, unsaved, usLength, CXCodeComplete_IncludeMacros|CXCodeComplete_IncludeCodePatterns);
        if (!res)
            return NULL;
        clang_sortCodeCompletionResults(res->Results, res->NumResults);
        // TODO: binary search to find the range
        int start = 0;
        int end = res->NumResults;
        std::vector<Entry*> entries;
        CXCursor tmp = clang_getNullCursor();

        while (start < end)
        {
            if (clang_getCompletionAvailability(res->Results[start].CompletionString) == CXAvailability_NotAccessible ||
                (memberCompletion && !isMemberKind(res->Results[start].CursorKind)))
            {
                start++;
                continue;
            }

            std::string insertion;
            std::string representation;
            parse_res(insertion, representation, res->Results[start].CursorKind, res->Results[start].CompletionString);
            if (insertion.length() != 0)
                entries.push_back(new Entry(tmp, representation, insertion));
            start++;
        }
        clang_disposeCodeCompleteResults(res);
        return new CacheCompletionResults(entries.begin(), entries.end(), true);
    }

    CacheCompletionResults* complete(const char *prefix)
    {
        std::vector<Entry*>::iterator start = std::lower_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());
        std::vector<Entry*>::iterator end = std::upper_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());

        return new CacheCompletionResults(start, end);
    }

    CacheCompletionResults* getNamespaceMembers(const char **ns, unsigned int nsLength)
    {
        NamespaceVisitorData d(mNamespaces, ns[0], nsLength > 1 ? &ns[1] : NULL, nsLength-1);
        d.execute();
        std::vector<Entry*>& entries = d.getEntries();
        return new CacheCompletionResults(entries.begin(), entries.end(), true);
    }
    void addCategories(CXCursor cur, CompletionVisitorData* d)
    {
        CategoryContainer::iterator i = mObjCCategories.find(cur);
        if (i != mObjCCategories.end())
        {
            CursorList &list = (*i).second;
            for (CursorList::iterator pos = list.begin(); pos != list.end(); pos++)
            {
                clang_visitChildren(*pos, get_completion_children, d);
            }
        }
    }
    CacheCompletionResults* completeCursor(CXCursor cur)
    {
        std::vector<Entry *> entries;
        CompletionVisitorData d(entries, clang_getCursorKind(cur) == CXCursor_ClassDecl ? CX_CXXPrivate : CX_CXXPublic);
        clang_visitChildren(cur, get_completion_children, &d);
        addCategories(cur, &d);
        for (CursorList::iterator i = d.mParents.begin(); i != d.mParents.end(); i++)
        {
            addCategories(*i, &d);
        }

        std::sort(entries.begin(), entries.end(), EntryCompare());
        trim(mEntries);

        return new CacheCompletionResults(entries.begin(), entries.end(), true);
    }
    CXCursor findType(const char ** namespaces, unsigned int nsLength, const char *type)
    {
        if (nsLength == 0)
        {
            std::string disp(type);
            disp += "\t";
            std::vector<Entry*>::iterator pos = std::lower_bound(mEntries.begin(), mEntries.end(), disp.c_str(), EntryStringCompare());
            if (pos != mEntries.end() && !strncmp((*pos)->display, disp.c_str(), disp.length()))
            {
                return (*pos)->cursor;
            }
            // see if it's a template
            disp = type;
            disp += "<";
            pos = std::lower_bound(mEntries.begin(), mEntries.end(), disp.c_str(), EntryStringCompare());
            if (pos != mEntries.end() && !strncmp((*pos)->display, disp.c_str(), disp.length()))
            {
                return (*pos)->cursor;
            }

            return clang_getNullCursor();
        }
        // TODO: should use mNamespaces for the first namespace entry
        FindData d(mBaseCursor, namespaces, nsLength, type);
        d.execute();
        return d.getCursor();
    }
private:
    CategoryContainer   mObjCCategories;
    CXCursor            mBaseCursor;
    std::vector<Entry*> mEntries;
    std::vector<Entry*> mNamespaces;
};


extern "C"
{

EXPORT CacheCompletionResults* cache_clangComplete(Cache* cache, const char *filename, unsigned int row, unsigned int col, CXUnsavedFile *unsaved, unsigned int usLength, bool memberCompletion)
{
    return cache->clangComplete(filename, row, col, unsaved, usLength, memberCompletion);
}

EXPORT CacheCompletionResults* cache_completeCursor(Cache* cache, CXCursor cur)
{
    return cache->completeCursor(cur);
}

EXPORT CXCursor cache_findType(Cache* cache, const char **namespaces, unsigned int nsLength, const char *type)
{
    return cache->findType(namespaces, nsLength, type);
}
EXPORT CacheCompletionResults* cache_completeNamespace(Cache* cache, const char **namespaces, unsigned int length)
{
    return cache->getNamespaceMembers(namespaces, length);
}

EXPORT CacheCompletionResults* cache_complete_startswith(Cache* cache, const char *prefix)
{
    return cache->complete(prefix);
}
EXPORT void cache_disposeCompletionResults(CacheCompletionResults *comp)
{
    delete comp;
}

EXPORT Cache* createCache(CXCursor base)
{
    return new Cache(base);
}

EXPORT void deleteCache(Cache *cache)
{
    delete cache;
}

}

