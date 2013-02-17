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
#include <assert.h>
#include <memory>

#if _WIN32
    #if _MSC_VER
       #define snprintf _snprintf_s
    #endif
    #define EXPORT __declspec(dllexport)
#else
   #define EXPORT
#endif
#if __MINGW32__
    #define MINGWSUPPORT __attribute__ ((callee_pop_aggregate_return(0)))
#else
    #define MINGWSUPPORT
#endif

using namespace std;
#ifdef SUBLIMECLANG_USE_TR1
#include <tr1/memory>
using namespace std::tr1;
#elif defined(BOOST_TR1_MEMORY_INCLUDED)
#include <boost/tr1/tr1/memory>
using namespace boost;
#endif

static const char* getCursorKindName(CXCursorKind c)
{
    switch (c)
    {
        case CXCursor_UnexposedDecl:                      return "CXCursor_UnexposedDecl";
        case CXCursor_StructDecl:                         return "CXCursor_StructDecl";
        case CXCursor_UnionDecl:                          return "CXCursor_UnionDecl";
        case CXCursor_ClassDecl:                          return "CXCursor_ClassDecl";
        case CXCursor_EnumDecl:                           return "CXCursor_EnumDecl";
        case CXCursor_FieldDecl:                          return "CXCursor_FieldDecl";
        case CXCursor_EnumConstantDecl:                   return "CXCursor_EnumConstantDecl";
        case CXCursor_FunctionDecl:                       return "CXCursor_FunctionDecl";
        case CXCursor_VarDecl:                            return "CXCursor_VarDecl";
        case CXCursor_ParmDecl:                           return "CXCursor_ParmDecl";
        case CXCursor_ObjCInterfaceDecl:                  return "CXCursor_ObjCInterfaceDecl";
        case CXCursor_ObjCCategoryDecl:                   return "CXCursor_ObjCCategoryDecl";
        case CXCursor_ObjCProtocolDecl:                   return "CXCursor_ObjCProtocolDecl";
        case CXCursor_ObjCPropertyDecl:                   return "CXCursor_ObjCPropertyDecl";
        case CXCursor_ObjCIvarDecl:                       return "CXCursor_ObjCIvarDecl";
        case CXCursor_ObjCInstanceMethodDecl:             return "CXCursor_ObjCInstanceMethodDecl";
        case CXCursor_ObjCClassMethodDecl:                return "CXCursor_ObjCClassMethodDecl";
        case CXCursor_ObjCImplementationDecl:             return "CXCursor_ObjCImplementationDecl";
        case CXCursor_ObjCCategoryImplDecl:               return "CXCursor_ObjCCategoryImplDecl";
        case CXCursor_TypedefDecl:                        return "CXCursor_TypedefDecl";
        case CXCursor_CXXMethod:                          return "CXCursor_CXXMethod";
        case CXCursor_Namespace:                          return "CXCursor_Namespace";
        case CXCursor_LinkageSpec:                        return "CXCursor_LinkageSpec";
        case CXCursor_Constructor:                        return "CXCursor_Constructor";
        case CXCursor_Destructor:                         return "CXCursor_Destructor";
        case CXCursor_ConversionFunction:                 return "CXCursor_ConversionFunction";
        case CXCursor_TemplateTypeParameter:              return "CXCursor_TemplateTypeParameter";
        case CXCursor_NonTypeTemplateParameter:           return "CXCursor_NonTypeTemplateParameter";
        case CXCursor_TemplateTemplateParameter:          return "CXCursor_TemplateTemplateParameter";
        case CXCursor_FunctionTemplate:                   return "CXCursor_FunctionTemplate";
        case CXCursor_ClassTemplate:                      return "CXCursor_ClassTemplate";
        case CXCursor_ClassTemplatePartialSpecialization: return "CXCursor_ClassTemplatePartialSpecialization";
        case CXCursor_NamespaceAlias:                     return "CXCursor_NamespaceAlias";
        case CXCursor_UsingDirective:                     return "CXCursor_UsingDirective";
        case CXCursor_UsingDeclaration:                   return "CXCursor_UsingDeclaration";
        case CXCursor_TypeAliasDecl:                      return "CXCursor_TypeAliasDecl";
        case CXCursor_ObjCSynthesizeDecl:                 return "CXCursor_ObjCSynthesizeDecl";
        case CXCursor_ObjCDynamicDecl:                    return "CXCursor_ObjCDynamicDecl";
        case CXCursor_CXXAccessSpecifier:                 return "CXCursor_CXXAccessSpecifier";
        case CXCursor_ObjCSuperClassRef:                  return "CXCursor_ObjCSuperClassRef";
        case CXCursor_ObjCProtocolRef:                    return "CXCursor_ObjCProtocolRef";
        case CXCursor_ObjCClassRef:                       return "CXCursor_ObjCClassRef";
        case CXCursor_TypeRef:                            return "CXCursor_TypeRef";
        case CXCursor_CXXBaseSpecifier:                   return "CXCursor_CXXBaseSpecifier";
        case CXCursor_TemplateRef:                        return "CXCursor_TemplateRef";
        case CXCursor_NamespaceRef:                       return "CXCursor_NamespaceRef";
        case CXCursor_MemberRef:                          return "CXCursor_MemberRef";
        case CXCursor_LabelRef:                           return "CXCursor_LabelRef";
        case CXCursor_OverloadedDeclRef:                  return "CXCursor_OverloadedDeclRef";
        case CXCursor_InvalidFile:                        return "CXCursor_InvalidFile";
        case CXCursor_NoDeclFound:                        return "CXCursor_NoDeclFound";
        case CXCursor_NotImplemented:                     return "CXCursor_NotImplemented";
        case CXCursor_InvalidCode:                        return "CXCursor_InvalidCode";
        case CXCursor_UnexposedExpr:                      return "CXCursor_UnexposedExpr";
        case CXCursor_DeclRefExpr:                        return "CXCursor_DeclRefExpr";
        case CXCursor_MemberRefExpr:                      return "CXCursor_MemberRefExpr";
        case CXCursor_CallExpr:                           return "CXCursor_CallExpr";
        case CXCursor_ObjCMessageExpr:                    return "CXCursor_ObjCMessageExpr";
        case CXCursor_BlockExpr:                          return "CXCursor_BlockExpr";
        case CXCursor_IntegerLiteral:                     return "CXCursor_IntegerLiteral";
        case CXCursor_FloatingLiteral:                    return "CXCursor_FloatingLiteral";
        case CXCursor_ImaginaryLiteral:                   return "CXCursor_ImaginaryLiteral";
        case CXCursor_StringLiteral:                      return "CXCursor_StringLiteral";
        case CXCursor_CharacterLiteral:                   return "CXCursor_CharacterLiteral";
        case CXCursor_ParenExpr:                          return "CXCursor_ParenExpr";
        case CXCursor_UnaryOperator:                      return "CXCursor_UnaryOperator";
        case CXCursor_ArraySubscriptExpr:                 return "CXCursor_ArraySubscriptExpr";
        case CXCursor_BinaryOperator:                     return "CXCursor_BinaryOperator";
        case CXCursor_CompoundAssignOperator:             return "CXCursor_CompoundAssignOperator";
        case CXCursor_ConditionalOperator:                return "CXCursor_ConditionalOperator";
        case CXCursor_CStyleCastExpr:                     return "CXCursor_CStyleCastExpr";
        case CXCursor_CompoundLiteralExpr:                return "CXCursor_CompoundLiteralExpr";
        case CXCursor_InitListExpr:                       return "CXCursor_InitListExpr";
        case CXCursor_AddrLabelExpr:                      return "CXCursor_AddrLabelExpr";
        case CXCursor_StmtExpr:                           return "CXCursor_StmtExpr";
        case CXCursor_GenericSelectionExpr:               return "CXCursor_GenericSelectionExpr";
        case CXCursor_GNUNullExpr:                        return "CXCursor_GNUNullExpr";
        case CXCursor_CXXStaticCastExpr:                  return "CXCursor_CXXStaticCastExpr";
        case CXCursor_CXXDynamicCastExpr:                 return "CXCursor_CXXDynamicCastExpr";
        case CXCursor_CXXReinterpretCastExpr:             return "CXCursor_CXXReinterpretCastExpr";
        case CXCursor_CXXConstCastExpr:                   return "CXCursor_CXXConstCastExpr";
        case CXCursor_CXXFunctionalCastExpr:              return "CXCursor_CXXFunctionalCastExpr";
        case CXCursor_CXXTypeidExpr:                      return "CXCursor_CXXTypeidExpr";
        case CXCursor_CXXBoolLiteralExpr:                 return "CXCursor_CXXBoolLiteralExpr";
        case CXCursor_CXXNullPtrLiteralExpr:              return "CXCursor_CXXNullPtrLiteralExpr";
        case CXCursor_CXXThisExpr:                        return "CXCursor_CXXThisExpr";
        case CXCursor_CXXThrowExpr:                       return "CXCursor_CXXThrowExpr";
        case CXCursor_CXXNewExpr:                         return "CXCursor_CXXNewExpr";
        case CXCursor_CXXDeleteExpr:                      return "CXCursor_CXXDeleteExpr";
        case CXCursor_UnaryExpr:                          return "CXCursor_UnaryExpr";
        case CXCursor_ObjCStringLiteral:                  return "CXCursor_ObjCStringLiteral";
        case CXCursor_ObjCEncodeExpr:                     return "CXCursor_ObjCEncodeExpr";
        case CXCursor_ObjCSelectorExpr:                   return "CXCursor_ObjCSelectorExpr";
        case CXCursor_ObjCProtocolExpr:                   return "CXCursor_ObjCProtocolExpr";
        case CXCursor_ObjCBridgedCastExpr:                return "CXCursor_ObjCBridgedCastExpr";
        case CXCursor_PackExpansionExpr:                  return "CXCursor_PackExpansionExpr";
        case CXCursor_SizeOfPackExpr:                     return "CXCursor_SizeOfPackExpr";
        case CXCursor_UnexposedStmt:                      return "CXCursor_UnexposedStmt";
        case CXCursor_LabelStmt:                          return "CXCursor_LabelStmt";
        case CXCursor_CompoundStmt:                       return "CXCursor_CompoundStmt";
        case CXCursor_CaseStmt:                           return "CXCursor_CaseStmt";
        case CXCursor_DefaultStmt:                        return "CXCursor_DefaultStmt";
        case CXCursor_IfStmt:                             return "CXCursor_IfStmt";
        case CXCursor_SwitchStmt:                         return "CXCursor_SwitchStmt";
        case CXCursor_WhileStmt:                          return "CXCursor_WhileStmt";
        case CXCursor_DoStmt:                             return "CXCursor_DoStmt";
        case CXCursor_ForStmt:                            return "CXCursor_ForStmt";
        case CXCursor_GotoStmt:                           return "CXCursor_GotoStmt";
        case CXCursor_IndirectGotoStmt:                   return "CXCursor_IndirectGotoStmt";
        case CXCursor_ContinueStmt:                       return "CXCursor_ContinueStmt";
        case CXCursor_BreakStmt:                          return "CXCursor_BreakStmt";
        case CXCursor_ReturnStmt:                         return "CXCursor_ReturnStmt";
        case CXCursor_AsmStmt:                            return "CXCursor_AsmStmt";
        case CXCursor_ObjCAtTryStmt:                      return "CXCursor_ObjCAtTryStmt";
        case CXCursor_ObjCAtCatchStmt:                    return "CXCursor_ObjCAtCatchStmt";
        case CXCursor_ObjCAtFinallyStmt:                  return "CXCursor_ObjCAtFinallyStmt";
        case CXCursor_ObjCAtThrowStmt:                    return "CXCursor_ObjCAtThrowStmt";
        case CXCursor_ObjCAtSynchronizedStmt:             return "CXCursor_ObjCAtSynchronizedStmt";
        case CXCursor_ObjCAutoreleasePoolStmt:            return "CXCursor_ObjCAutoreleasePoolStmt";
        case CXCursor_ObjCForCollectionStmt:              return "CXCursor_ObjCForCollectionStmt";
        case CXCursor_CXXCatchStmt:                       return "CXCursor_CXXCatchStmt";
        case CXCursor_CXXTryStmt:                         return "CXCursor_CXXTryStmt";
        case CXCursor_CXXForRangeStmt:                    return "CXCursor_CXXForRangeStmt";
        case CXCursor_SEHTryStmt:                         return "CXCursor_SEHTryStmt";
        case CXCursor_SEHExceptStmt:                      return "CXCursor_SEHExceptStmt";
        case CXCursor_SEHFinallyStmt:                     return "CXCursor_SEHFinallyStmt";
        case CXCursor_NullStmt:                           return "CXCursor_NullStmt";
        case CXCursor_DeclStmt:                           return "CXCursor_DeclStmt";
        case CXCursor_TranslationUnit:                    return "CXCursor_TranslationUnit";
        case CXCursor_UnexposedAttr:                      return "CXCursor_UnexposedAttr";
        case CXCursor_IBActionAttr:                       return "CXCursor_IBActionAttr";
        case CXCursor_IBOutletAttr:                       return "CXCursor_IBOutletAttr";
        case CXCursor_IBOutletCollectionAttr:             return "CXCursor_IBOutletCollectionAttr";
        case CXCursor_CXXFinalAttr:                       return "CXCursor_CXXFinalAttr";
        case CXCursor_CXXOverrideAttr:                    return "CXCursor_CXXOverrideAttr";
        case CXCursor_AnnotateAttr:                       return "CXCursor_AnnotateAttr";
        case CXCursor_PreprocessingDirective:             return "CXCursor_PreprocessingDirective";
        case CXCursor_MacroDefinition:                    return "CXCursor_MacroDefinition";
        case CXCursor_MacroExpansion:                     return "CXCursor_MacroExpansion";
        case CXCursor_InclusionDirective:                 return "CXCursor_InclusionDirective";
        default:                                          return "Unknown";
    }
}

bool operator<(const CXCursor &c1, const CXCursor &c2)
{
    CXString s1       = clang_getCursorUSR(c1);
    CXString s2       = clang_getCursorUSR(c2);
    const char *cstr1 = clang_getCString(s1);
    const char *cstr2 = clang_getCString(s2);
    bool ret          = strcmp(cstr1, cstr2) < 0;
    clang_disposeString(s1);
    clang_disposeString(s2);
    return ret;
}

class Entry;
typedef std::vector<CXCursor>                CursorList;
typedef std::vector<shared_ptr<Entry> > EntryList;
typedef std::map<CXCursor, CursorList>       CategoryContainer;


void dump(CXCursor cursor)
{
    if (clang_Cursor_isNull(cursor))
    {
        printf("NULL\n");
        return;
    }
    CXString s = clang_getCursorSpelling(cursor);
    const char *str = clang_getCString(s);
    if (str)
    {
        CXSourceLocation loc = clang_getCursorLocation(cursor);
        CXFile file;
        unsigned int line, column;
        clang_getExpansionLocation(loc, &file, &line, &column, NULL);
        CXString filename = clang_getFileName(file);
        const char *str2 = clang_getCString(filename);
        if (!str2)
            str2 = "Null";
        printf("%s - %s\n%s:%d:%d\n", str, getCursorKindName(clang_getCursorKind(cursor)), str2, line, column);
        clang_disposeString(filename);
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

CXCursor resolve(CXCursor cursor)
{
    if (clang_Cursor_isNull(cursor))
        return cursor;
    CXCursorKind ck = clang_getCursorKind(cursor);
    switch (ck)
    {
        case CXCursor_TypeRef:
        {
            CXCursor ref = clang_getCursorReferenced(cursor);
            return resolve(ref);
        }
        case CXCursor_TypedefDecl:
        {
            CursorList children;
            clang_visitChildren(cursor, getchildren_visitor, &children);
            CursorList::iterator first = children.begin();
            while (first < children.end())
            {
                if (clang_getCursorKind(*first) != CXCursor_NamespaceRef)
                    break;
                first++;
            }
            bool simple = true;

            for (CursorList::iterator i = first + 1; i < children.end(); i++)
            {
                if (clang_getCursorKind(*i) != CXCursor_IntegerLiteral)
                {
                    simple = false;
                    break;
                }
            }
            if (simple && children.size())
                return resolve(*first);
            return clang_getNullCursor();
        }
        default:
            break;
    }
    return cursor;
}


void get_return_type(std::string& returnType, CXCursorKind ck)
{
    switch (ck)
    {
        default:                                                   break;
        case CXCursor_UnionDecl:         returnType = "union";     break;
        case CXCursor_ObjCInterfaceDecl: // fall through
        case CXCursor_ClassTemplate:     // fall through
        case CXCursor_ClassDecl:         returnType = "class";     break;
        case CXCursor_EnumDecl:          returnType = "enum";      break;
        case CXCursor_StructDecl:        returnType = "struct";    break;
        case CXCursor_MacroDefinition:   returnType = "macro";     break;
        case CXCursor_NamespaceAlias:    // fall through
        case CXCursor_Namespace:         returnType = "namespace"; break;
        case CXCursor_TypedefDecl:       returnType = "typedef";   break;
        case CXCursor_Constructor:       returnType = "constructor"; break;
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
    switch (ck)
    {
        default:
        {
            CXCompletionString comp = clang_getCursorCompletionString(cursor);
            parse_res(returnType, insertion, representation, comp);
            break;
        }
        case CXCursor_MacroDefinition:
        {
            unsigned int count = 0;
            CXToken * tokens = NULL;
            CXTranslationUnit tu = clang_Cursor_getTranslationUnit(cursor);

            clang_tokenize(tu, clang_getCursorExtent(cursor), &tokens, &count);
            if (tokens)
            {
                int parCount = 0;
                int argCount = 1;
                unsigned int i = 0;
                bool br = false;
                for (i = 0; i < count && !br; i++)
                {
                    CXString s = clang_getTokenSpelling(tu, tokens[i]);
                    const char *str = clang_getCString(s);
                    if (str)
                    {
                        if (str[0] == '(')
                            parCount++;
                        if (i > 0 && parCount == 0)
                        {
                            br = true;
                        }
                        else
                        {
                            representation += str;
                            if (i > 0 && clang_getTokenKind(tokens[i]) == CXToken_Identifier)
                            {
                                char buf[512];
                                snprintf(buf, 512, "${%d:%s}", argCount, str);
                                insertion += buf;
                                argCount++;
                            }
                            else
                            {
                                insertion += str;
                            }
                        }
                        if (str[0] == ')')
                            parCount--;
                        else if (str[0] == ',')
                        {
                            representation += ' ';
                            insertion += ' ';
                        }
                    }
                    clang_disposeString(s);
                }
                if (i == count && count > 2)
                {
                    CXString s = clang_getTokenSpelling(tu, tokens[0]);
                    const char *str = clang_getCString(s);
                    insertion = representation = str;
                    clang_disposeString(s);
                }
                representation += "\t" + returnType;
                clang_disposeTokens(tu, tokens, count);
            }
            break;
        }
        case CXCursor_Namespace:
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
            break;
        }
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
                case CXCursor_CXXMethod:           isStatic = clang_CXXMethod_isStatic(c); break;
                case CXCursor_VarDecl:             isStatic = true;                        break;
                case CXCursor_ObjCClassMethodDecl: isStatic = true;                        break;
                default:                           isStatic = false;                       break;
            }
        }
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
    CXCursor              cursor;
    char *                insert;
    char *                display;
    CX_CXXAccessSpecifier access;
    bool                  isStatic;
    bool                  isBaseClass;
};


void trim(EntryList& mEntries)
{
    EntryList::iterator i = mEntries.begin();
    // Trim nameless completions
    while (i != mEntries.end() && (*i)->display[0] == '\t')
    {
        mEntries.erase(i);
        i = mEntries.begin();
    }
    // Trim duplicates
    if (mEntries.begin() == mEntries.end())
        return;
    for (EntryList::iterator i = mEntries.begin()+1; i < mEntries.end(); )
    {
        while (i != mEntries.end() && (*(*i)) == (*(*(i-1))))
        {
            EntryList::iterator del = i;
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
            mEntries.erase(del);
            if (begin)
            {
                i = mEntries.begin();
            }
            i++;
        }
#if _WIN32
        // MSVC asserts if you i++ past the end of the vector.
        // In this case it's just an overzealous assert as we won't
        // be reading from it. Issue #143
        if (i < mEntries.end())
#endif
        {
            i++;
        }
    }
}

class EntryCompare
{
public:
    bool operator()(const shared_ptr<Entry> a, const shared_ptr<Entry> b) const
    {
        if (!b)
            return false;
        return strcmp(a->display, b->display) < 0;
    }
};
class EntryStringCompare
{
public:
    EntryStringCompare(bool exact=false)
        : mExact(exact)
    {

    }

    bool operator()(const shared_ptr<Entry> a, const char *str) const
    {
        return compare(a, str) < 0;
    }
    bool operator()(const char *str, const shared_ptr<Entry> a) const
    {
        return compare(a, str) > 0;
    }
private:
    int compare(const shared_ptr<Entry> a, const char *str) const
    {
        size_t length;

        if (mExact)
        {
            char * off = strchr(a->display, '\t');
            length = strlen(a->display);
            if (off != NULL)
            {
                length = off - a->display;
            }
            length = std::max(strlen(str), length);
        }
        else
            length = strlen(str);

        return strncmp(a->display, str, length);
    }
    bool mExact;
};

class CacheCompletionResults
{
public:
    CacheCompletionResults(EntryList::iterator start, EntryList::iterator end)
    : mEntries(start, end)
    {
    }
    ~CacheCompletionResults()
    {
    }
    unsigned int length() const
    {
        return mEntries.size();
    }
    const Entry* getEntry(unsigned int index) const
    {
        assert(index >= 0 && index < mEntries.size());
        return mEntries[index].get();
    }

private:
    EntryList    mEntries;
};

CXCursor get_using_cursor(CXCursor cursor, CXCursorKind ck)
{
    CursorList cur;
    clang_visitChildren(cursor, getchildren_visitor, &cur);
    if (cur.size())
    {
        CXCursor cursor = cur.back();
        if (clang_isReference(clang_getCursorKind(cursor)))
        {
            cursor = clang_getCursorReferenced(cursor);
            if (clang_getNumOverloadedDecls(cursor))
            {
                cursor = clang_getOverloadedDecl(cursor, 0);
            }
            return cursor;
        }
    }
    return clang_getNullCursor();
}


class CompletionVisitorData
{
public:
    CompletionVisitorData(EntryList& e, CX_CXXAccessSpecifier a=CX_CXXPrivate, bool base=false)
    : entries(e), access(a), isBaseClass(base)
    {
    }

    void visit_children(CXCursor cursor)
    {
        clang_visitChildren(cursor, get_completion_children, this);
        for (CursorList::iterator i = mAnonymousFields.begin(); i < mAnonymousFields.end(); i++)
        {
            CompletionVisitorData d(entries, access, isBaseClass);
            d.visit_children(*i);
        }
    }

    void add_completion_children(CXCursor cursor, CXCursorKind ck, bool &recurse)
    {
        switch (ck)
        {
            default: break;
            case CXCursor_CXXAccessSpecifier:
                access = clang_getCXXAccessSpecifier(cursor);
                break;
            case CXCursor_UsingDeclaration:
            {
                CXCursor cur = get_using_cursor(cursor, ck);
                if (!clang_Cursor_isNull(cur))
                {
                    bool rec = false;
                    add_completion_children(cur, clang_getCursorKind(cur), rec);
                }
                break;
            }
            case CXCursor_UnexposedDecl: // extern "C" for example
                recurse = true;
                break;
            case CXCursor_EnumDecl:
                recurse = true;
                // fall through
            case CXCursor_UnionDecl:
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
            case CXCursor_NamespaceAlias:
            case CXCursor_MacroDefinition:
            case CXCursor_Constructor:
            {
                std::string ins;
                std::string disp;
                parse_res(ins, disp, cursor);
                if (ins.length() != 0)
                {
                    shared_ptr<Entry> entry(new Entry(cursor, disp, ins, access, isBaseClass));
                    entries.push_back(entry);
                }
                else if (ck == CXCursor_StructDecl || ck == CXCursor_UnionDecl)
                {
                    // Might be an anonymous struct or union whose children we need to add later
                    mAnonymousFields.push_back(cursor);
                }
                switch (ck)
                {
                    case CXCursor_FieldDecl:
                    case CXCursor_VarDecl:
                    case CXCursor_TypedefDecl:
                    {
                        CXCursor child = clang_getNullCursor();
                        clang_visitChildren(cursor, get_first_child_visitor, &child);
                        if (!clang_Cursor_isNull(child) &&
                            (clang_getCursorKind(child) == CXCursor_StructDecl ||
                             clang_getCursorKind(child) == CXCursor_UnionDecl))
                        {
                            for (CursorList::iterator i = mAnonymousFields.begin(); i < mAnonymousFields.end(); i++)
                            {
                                if (clang_equalCursors(child, *i))
                                {
                                    mAnonymousFields.erase(i);
                                    break;
                                }
                            }
                        }
                    }
                    default:
                        break;
                }
                break;
            }
        }
    }
    CursorList            mParents;
    EntryList &           entries;
    CX_CXXAccessSpecifier access;
    bool                  isBaseClass;

    void addConstructors(CXCursor cursor, CXCursorKind ck)
    {
        switch (ck)
        {
            case CXCursor_ClassTemplate:
            case CXCursor_StructDecl:
            case CXCursor_ClassDecl:
            {
                CursorList children;
                EntryList e;
                CompletionVisitorData d(e, access);
                d.visit_children(cursor);
                for (EntryList::iterator i = e.begin(); i < e.end(); i++)
                {
                    shared_ptr<Entry> entry = *i;
                    if (clang_getCursorKind(entry->cursor) == CXCursor_Constructor && entry->access == CX_CXXPublic)
                        entries.push_back(entry);
                }
                break;
            }
            default: break;
        }
    }


private:
    CursorList            mAnonymousFields;


    static CXChildVisitResult get_completion_children(CXCursor cursor, CXCursor parent, CXClientData client_data)
    {
        if (clang_Cursor_isNull(cursor))
            return CXChildVisit_Break;
        bool recurse = false;
        CXCursorKind ck = clang_getCursorKind(cursor);
        CompletionVisitorData* data = (CompletionVisitorData*) client_data;

        data->add_completion_children(cursor, ck, recurse);
        switch (ck)
        {
            case CXCursor_CXXBaseSpecifier:
            case CXCursor_ObjCSuperClassRef:
            case CXCursor_ObjCProtocolRef:
            {
                CXCursor ref = resolve(clang_getCursorReferenced(cursor));

                if (!clang_Cursor_isNull(ref) && !clang_isInvalid(clang_getCursorKind(ref)) && !clang_equalCursors(ref, parent))
                {
                    data->mParents.push_back(ref);
                    CompletionVisitorData d(data->entries, ck == CXCursor_CXXBaseSpecifier ? CX_CXXPrivate : CX_CXXProtected, true);
                    if (clang_getCursorKind(ref) == CXCursor_StructDecl)
                    {
                        d.access = CX_CXXPublic;
                    }
                    d.visit_children(ref);
                    for (CursorList::iterator i = d.mParents.begin(); i != d.mParents.end(); i++)
                    {
                        data->mParents.push_back(*i);
                    }
                }
                break;
            }
            default: break;
        }
        data->addConstructors(cursor, ck);

        if (recurse)
        {
            return CXChildVisit_Recurse;
        }
        return CXChildVisit_Continue;
    }
};

class  NamespaceHelper
{
public:
    NamespaceHelper(CursorList &children)
    {
        nsLength = children.size();
        ns = new char*[nsLength];
        for (size_t i = 0; i < nsLength; i++)
        {
            CXString s = clang_getCursorSpelling(children[i]);
            const char *str = clang_getCString(s);
            size_t len = strlen(str)+1;
            ns[i] = new char[len];
            memcpy(ns[i], str, len);
            clang_disposeString(s);
        }
    }

    ~NamespaceHelper()
    {
        for (size_t i = 0; i < nsLength; i++)
        {
            delete[] ns[i];
        }
        delete[] ns;
    }

    char **ns;
    size_t nsLength;
};





class Cache;
class NamespaceFinder
{
public:
    NamespaceFinder(Cache *cache, CXCursor base, const char ** ns, size_t nsLength)
    : mCache(cache), mBase(base), namespaces(ns), namespaceCount(nsLength)
    {

    }
    virtual void execute()
    {
        clang_visitChildren(mBase, &NamespaceFinder::visitor, this);
    }

    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck) = 0;

    CursorList &GetParents()
    {
        return mParents;
    }

    Cache *getCache() const
    {
        return mCache;
    }
protected:
    Cache*       mCache;
    CXCursor     mBase;
    CursorList   mParents;
    const char **namespaces;
    size_t       namespaceCount;

    static CXChildVisitResult visitor(CXCursor cursor, CXCursor parent, CXClientData client_data);
};


class NamespaceVisitorData : public NamespaceFinder
{
public:
    NamespaceVisitorData(Cache * cache, const char* firstName, const char **ns, size_t nsLength, bool trim = true)
    : NamespaceFinder(cache, clang_getNullCursor(), ns, nsLength), mFirstName(firstName), mTrim(trim)
    {
    }
    ~NamespaceVisitorData()
    {
    }
    virtual void execute();

    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck)
    {
        if (ck == CXCursor_UsingDirective)
        {
            CursorList children;
            clang_visitChildren(cursor, getchildren_visitor, &children);
            NamespaceHelper h(children);
            NamespaceVisitorData d(mCache, h.ns[0], (const char**) (h.nsLength > 1 ? &h.ns[1] : NULL), h.nsLength-1);
            d.execute();
            EntryList &entries = d.getEntries();
            for (EntryList::iterator i = entries.begin(); i < entries.end(); i++)
            {
                mEntries.push_back(*i);
            }
        }
        else
        {
            CompletionVisitorData d(mEntries);
            d.add_completion_children(cursor, ck, recurse);
            d.addConstructors(cursor, ck);
        }

        return false;
    }

    EntryList &getEntries()
    {
        return mEntries;
    }


protected:
    const char *mFirstName;
    EntryList   mEntries;
    bool        mTrim;
};

class UsingNamespaceFinder : public NamespaceVisitorData
{
public:
    UsingNamespaceFinder(const char *firstName, const char **ns, size_t nsLength, NamespaceFinder *realFinder)
    : NamespaceVisitorData(realFinder->getCache(), firstName, ns, nsLength), mRealFinder(realFinder)
    {

    }
    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck)
    {
        CXCursor par;
        if (mRealFinder->GetParents().size())
            par = mRealFinder->GetParents().back();
        else
            par = clang_getNullCursor();
        CXChildVisitResult r = NamespaceFinder::visitor(cursor, par, mRealFinder);
        if (r == CXChildVisit_Recurse)
        {
            clang_visitChildren(cursor, NamespaceFinder::visitor, mRealFinder);
        }
        return false;
    }
private:
    NamespaceFinder *mRealFinder;

};


CXChildVisitResult NamespaceFinder::visitor(CXCursor cursor, CXCursor parent, CXClientData client_data)
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
        case CXCursor_UsingDirective:
        {
            if (nvd->mParents.size() < nvd->namespaceCount)
            {
                CursorList children;
                clang_visitChildren(cursor, getchildren_visitor, &children);
                NamespaceHelper h(children);

                UsingNamespaceFinder unf(h.ns[0], (const char**) (h.nsLength > 1 ? &h.ns[1] : NULL), h.nsLength-1, nvd);
                unf.execute();
            }
            break;
        }
        case CXCursor_NamespaceAlias:
        {
            if (nvd->mParents.size() < nvd->namespaceCount)
            {
                CXString s = clang_getCursorSpelling(cursor);
                const char *str = clang_getCString(s);
                if (str)
                {
                    if (!strcmp(nvd->namespaces[nvd->mParents.size()], str))
                    {
                        CXCursor curr = cursor;
                        CursorList children;
                        while (clang_getCursorKind(curr) != CXCursor_Namespace)
                        {
                            CursorList l;
                            clang_visitChildren(curr, getchildren_visitor, &l);
                            assert(l.size() && clang_isReference(clang_getCursorKind(l.back())));
                            curr = clang_getCursorReferenced(l.back());
                        }
                        while (!clang_Cursor_isNull(curr) && clang_getCursorKind(curr) == CXCursor_Namespace)
                        {
                            children.insert(children.begin(), curr);
                            curr = clang_getCursorLexicalParent(curr);
                        }
                        NamespaceHelper h(children);
                        NamespaceVisitorData d(nvd->mCache, h.ns[0], h.nsLength > 1 ? (const char **) &h.ns[1] : NULL, h.nsLength-1, false);
                        d.execute();
                        nvd->mParents.push_back(cursor);
                        EntryList &entries = d.getEntries();
                        for (EntryList::iterator i = entries.begin(); i < entries.end(); i++)
                        {
                            shared_ptr<Entry> e = (*i);

                            CXChildVisitResult r = NamespaceFinder::visitor(e->cursor, cursor, nvd);
                            if (r == CXChildVisit_Recurse)
                            {
                                clang_visitChildren(e->cursor, NamespaceFinder::visitor, nvd);
                            }
                        }
                    }
                }
                clang_disposeString(s);
            }
            break;
        }
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

class FindData : public NamespaceFinder
{
public:
    FindData(Cache *cache, CXCursor base, const char **namespaces, size_t nsLength, const char* s)
    : NamespaceFinder(cache, base, namespaces, nsLength), mFound(false), mSpelling(s)
    {

    }

    virtual bool visitor(CXCursor cursor, CXCursor parent, bool &recurse, CXCursorKind ck)
    {
        switch (ck)
        {
            default: break;
            case CXCursor_UsingDirective:
            {
                CursorList children;
                clang_visitChildren(cursor, getchildren_visitor, &children);
                size_t nsLength = children.size();
                char **ns = new char*[nsLength];
                for (size_t i = 0; i < nsLength; i++)
                {
                    CXString s = clang_getCursorSpelling(children[i]);
                    const char *str = clang_getCString(s);
                    size_t len = strlen(str)+1;
                    ns[i] = new char[len];
                    memcpy(ns[i], str, len);
                    clang_disposeString(s);
                }
                FindData d(mCache, mBase, (const char **) ns, nsLength, mSpelling);
                d.execute();
                if (!clang_Cursor_isNull(d.getCursor()))
                {
                    mFound = true;
                    mCursor = d.getCursor();
                }
                for (size_t i = 0; i < nsLength; i++)
                {
                    delete[] ns[i];
                }
                delete[] ns;
                break;
            }
            case CXCursor_UsingDeclaration:
            {
                bool rec = false;
                CXCursor cur = get_using_cursor(cursor, ck);
                if (!clang_Cursor_isNull(cur))
                {
                    visitor(cur, cursor, rec, clang_getCursorKind(cur));
                }
            }
            break;
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
    CXCursor    mCursor;
    bool        mFound;
    const char *mSpelling;
};


class Cache
{
public:
    Cache(CXCursor base)
    : mBaseCursor(base)
    {
        CompletionVisitorData d(mEntries, CX_CXXPublic);
        d.visit_children(base);

        std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
        for (EntryList::iterator i = mEntries.begin(); i != mEntries.end(); ++i)
        {
            shared_ptr<Entry> e = *i;
            CXCursorKind ck = clang_getCursorKind(e->cursor);
            if (ck == CXCursor_Namespace || ck == CXCursor_NamespaceAlias)
            {
                mNamespaces.push_back(e);
            }
        }
        trim(mEntries);
        clang_visitChildren(base, get_objc_categories_visitor, &mObjCCategories);
    }
    ~Cache()
    {
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
        EntryList entries;
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
            {
                shared_ptr<Entry> entry(new Entry(tmp, representation, insertion));
                entries.push_back(entry);
            }
            start++;
        }
        clang_disposeCodeCompleteResults(res);
        return new CacheCompletionResults(entries.begin(), entries.end());
    }

    CacheCompletionResults* complete(const char *prefix)
    {
        EntryList::iterator start = std::lower_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());
        EntryList::iterator end = std::upper_bound(mEntries.begin(), mEntries.end(), prefix, EntryStringCompare());

        return new CacheCompletionResults(start, end);
    }

    CacheCompletionResults* getNamespaceMembers(const char **ns, unsigned int nsLength)
    {
        NamespaceVisitorData d(this, ns[0], nsLength > 1 ? &ns[1] : NULL, nsLength-1);
        d.execute();
        EntryList& entries = d.getEntries();
        return new CacheCompletionResults(entries.begin(), entries.end());
    }
    void addCategories(CXCursor cur, CompletionVisitorData* d)
    {
        CategoryContainer::iterator i = mObjCCategories.find(cur);
        if (i != mObjCCategories.end())
        {
            CursorList &list = (*i).second;
            for (CursorList::iterator pos = list.begin(); pos != list.end(); pos++)
            {
                d->visit_children(*pos);
            }
        }
    }
    CacheCompletionResults* completeCursor(CXCursor cur)
    {
        EntryList entries;
        CompletionVisitorData d(entries, clang_getCursorKind(cur) == CXCursor_ClassDecl ? CX_CXXPrivate : CX_CXXPublic);
        d.visit_children(cur);
        addCategories(cur, &d);
        for (CursorList::iterator i = d.mParents.begin(); i != d.mParents.end(); i++)
        {
            addCategories(*i, &d);
        }

        std::sort(entries.begin(), entries.end(), EntryCompare());
        trim(mEntries);

        return new CacheCompletionResults(entries.begin(), entries.end());
    }
    CXCursor findType(const char ** namespaces, unsigned int nsLength, const char *type)
    {
        if (nsLength == 0)
        {
            std::string disp(type);
            disp += "\t";
            EntryList::iterator pos = std::lower_bound(mEntries.begin(), mEntries.end(), disp.c_str(), EntryStringCompare());
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
        FindData d(this, mBaseCursor, namespaces, nsLength, type);
        d.execute();
        return d.getCursor();
    }

    EntryList& getNamespaces()
    {
        return mNamespaces;
    }
private:
    CategoryContainer   mObjCCategories;
    CXCursor            mBaseCursor;
    EntryList           mEntries;
    EntryList           mNamespaces;
};

void NamespaceVisitorData::execute()
{
    EntryList::iterator start = std::lower_bound(mCache->getNamespaces().begin(), mCache->getNamespaces().end(), mFirstName, EntryStringCompare(true));
    EntryList::iterator end   = std::upper_bound(mCache->getNamespaces().begin(), mCache->getNamespaces().end(), mFirstName, EntryStringCompare(true));
    while (start < end)
    {
        if (clang_getCursorKind((*start)->cursor) == CXCursor_NamespaceAlias)
        {
            CXCursor cursor = (*start)->cursor;
            CXCursor curr = cursor;
            CursorList children;
            while (clang_getCursorKind(curr) != CXCursor_Namespace)
            {
                CursorList l;
                clang_visitChildren(curr, getchildren_visitor, &l);
                assert(l.size() && clang_isReference(clang_getCursorKind(l.back())));
                curr = clang_getCursorReferenced(l.back());
            }
            while (!clang_Cursor_isNull(curr) && clang_getCursorKind(curr) == CXCursor_Namespace)
            {
                children.insert(children.begin(), curr);
                curr = clang_getCursorLexicalParent(curr);
            }
            NamespaceHelper h(children);
            NamespaceVisitorData d(mCache, h.ns[0], h.nsLength > 1 ? (const char **) &h.ns[1] : NULL, h.nsLength-1, false);
            d.execute();
            EntryList &entries = d.getEntries();
            for (EntryList::iterator i = entries.begin(); i < entries.end(); i++)
            {
                shared_ptr<Entry> e = (*i);

                CXChildVisitResult r = NamespaceFinder::visitor(e->cursor, cursor, this);
                if (r == CXChildVisit_Recurse)
                {
                    clang_visitChildren(e->cursor, NamespaceFinder::visitor, this);
                }
            }
        }
        else
        {
            clang_visitChildren((*start)->cursor, NamespaceFinder::visitor, this);
        }
        start++;
    }

    std::sort(mEntries.begin(), mEntries.end(), EntryCompare());
    if (mTrim)
        trim(mEntries);
}


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

EXPORT MINGWSUPPORT CXCursor cache_findType(Cache* cache, const char **namespaces, unsigned int nsLength, const char *type)
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
EXPORT unsigned int completionResults_length(CacheCompletionResults *comp)
{
    return comp->length();
}
EXPORT const Entry* completionResults_getEntry(CacheCompletionResults *comp, unsigned int index)
{
    return comp->getEntry(index);
}
EXPORT void completionResults_dispose(CacheCompletionResults *comp)
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

EXPORT const char* getVersion()
{
    return SUBLIMECLANG_VERSION;
}

}

