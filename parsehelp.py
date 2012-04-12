"""
Copyright (c) 2012 Fredrik Ehnbom

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
import time
import re


def count_brackets(data):
    even = 0
    for i in range(len(data)):
        if data[i] == '{':
            even += 1
        elif data[i] == '}':
            even -= 1
    return even


def collapse_brackets(before):
    i = len(before)-1
    count = 0
    end = -1
    min = 0
    while i >= 0:
        if before[i] == '}':
            count += 1
            if end == -1:
                end = i
        elif before[i] == '{':
            count -= 1
            if count < min:
                min = count

        if count == min and end != -1:
            before = "%s%s" % (before[:i+1], before[end:])
            end = -1
        i -= 1
    #before = re.sub("[^\{}]+\((?!\))", "", before)
    return before


def collapse_parenthesis(before):
    i = len(before)-1
    count = 0
    end = -1
    while i >= 0:
        if before[i] == ')':
            count += 1
            if end == -1:
                end = i
        elif before[i] == '(':
            count -= 1
            if count == 0 and end != -1:
                before = "%s%s" % (before[:i+1], before[end:])
                end = -1
        i -= 1
    before = re.sub("[^\(]+\((?!\))", "", before)
    return before


def extract_completion(before):
    before = collapse_parenthesis(before)
    m = re.search("([^ \t]+)(\.|\->)$", before)
    before = before[m.start(1):m.end(2)]
    return before

_keywords = ["return", "new", "delete", "class", "define", "using", "void", "template", "public:", "protected:", "private:", "public", "private", "protected"]


def extract_used_namespaces(data):
    regex = re.compile("\s*using\s+(namespace\s+)?([^;]+)")
    ret = []
    for match in regex.finditer(data, re.MULTILINE):
        toadd = match.group(2)
        if match.group(1) == None:
            toadd = toadd[:toadd.rfind("::")]
        ret.append(toadd)
    return ret


def extract_namespace(data):
    data = collapse_brackets(data)
    data = remove_namespaces(data)
    regex = re.compile("namespace\s+([^{\s]+)")
    ret = ""
    for match in regex.finditer(data, re.MULTILINE):
        if len(ret):
            ret += "::"
        ret += match.group(1)
    return ret


def extract_class_from_function(data):
    data = collapse_brackets(data)
    data = remove_functions(data)
    ret = None
    for match in re.finditer("(\w+\s+)?(\w+)::~?(\w+)\([^)]*\)\s*\{", data, re.MULTILINE):
        ret = match.group(2)
    return ret


def extract_class(data):
    data = collapse_brackets(data)
    data = remove_classes(data)
    regex = re.compile("class\s+([^;{\s]+)")
    match = regex.search(data, re.MULTILINE)
    if match != None:
        return match.group(1)
    return None


def remove_classes(data):
    regex = re.compile("class\s+\S+\s*\{\}\s*;")
    match = regex.search(data, re.MULTILINE)
    while match:
        data = "%s%s" % (data[:match.start()], data[match.end():])
        match = regex.search(data, re.MULTILINE)
    return data


def remove_functions(data):
    regex = re.compile("\S+\s*\([^\)]*\)\s*(const)?\s*\{\}")
    match = regex.search(data, re.MULTILINE)
    while match:
        data = "%s%s" % (data[:match.start()], data[match.end():])
        match = regex.search(data, re.MULTILINE)
    return data


def remove_namespaces(data):
    regex = re.compile("\s*namespace\s+[^{]+\s*\{\}\s*;")
    match = regex.search(data, re.MULTILINE)
    while match:
        data = "%s%s" % (data[:match.start()], data[match.end():])
        match = regex.search(data, re.MULTILINE)
    return data


def sub(exp, data):
    regex = re.compile(exp)
    while True:
        olddata = data
        data = regex.sub("", data, re.MULTILINE|re.DOTALL)
        if olddata == data:
            break
    return data


def remove_preprocessing(data):
    data = data.replace("\\\n", " ")
    data = sub("\#\s*define.+\\n", data)
    data = sub("\#\s*(ifndef|ifdef|if|endif|else|elif|pragma|include)[^\\n]*\\n", data)
    data = sub("//[^\n]+\\n", data)
    data = sub("/\\*.*(?!\\*/)", data)
    return data


def remove_includes(data):
    regex = re.compile("""\#\s*include\s+(<|")[^>"]+(>|")""")
    while True:
        old = data
        data = regex.sub("", data)
        if old == data:
            break
    return data

_invalid = """( \t\{,\*\&\-\+\/;=%\)\.\"!"""


def extract_variables(data):
    data = remove_preprocessing(data)
    data = remove_includes(data)
    data = collapse_brackets(data)
    data = remove_functions(data)
    data = remove_namespaces(data)
    data = remove_classes(data)

    pattern = "(\\b\\w[^%s]+[ \t\*\&]+(const)?[ \t\*\&]*)(\w[^%s\>]+)[ \t]*(\(|\;|,|\)|=)" % (_invalid, _invalid)
    regex = re.compile(pattern)
    regex2 = re.compile("[^)]+\)+\s+\{")
    ret = []
    for m in regex.finditer(data, re.MULTILINE):
        type = m.group(1).strip()
        if type in _keywords or type.startswith("template"):
            continue
        if m.group(4) == "(":
            left = data[m.end():]
            if regex.match(left) or regex2.match(left, re.MULTILINE):
                continue
        var = m.group(3).strip()
        for i in range(len(ret)):
            if ret[i][1] == var:
                ret[i] = (type, var)
                var = None
                break
        if var != None:
            ret.append((type, var))
    return ret


def get_var_type(data, var):
    regex = re.compile("(\w[^%s]+)[ \t\*\&]+(%s)[ \t]*(\(|\;|,|\)|=)" % (_invalid, var))

    data = collapse_brackets(data)
    match = None
    for m in regex.finditer(data, re.MULTILINE):
        if m.group(1) in _keywords:
            continue
        match = m
    return match


def get_type_definition(data, before):
    start = time.time()
    before = extract_completion(before)
    match = re.search("([^\.\[\-]+)[^\.\-]*(\.|->)(.*)", before)
    var = match.group(1)
    tocomplete = match.group(3)
    end = time.time()
    print "var is %s (%f ms) " % (var, (end-start)*1000)

    start = time.time()
    if var == "this":
        data = data[:data.rfind(var)]
        idx = data.rfind("class")
        match = None
        while idx != -1:
            count = count_brackets(data[idx:])
            if (count & 1) == 0:
                match = re.search("class\s*([^\s\{]+)([^\{]*\{)(.*)", data[idx:])
                break
            idx = data.rfind("class", 0, idx)
    else:
        match = get_var_type(data, var)
    end = time.time()
    print "type is %s (%f ms)" % ("None" if match == None else match.group(1), (end-start)*1000)
    if match == None:
        return -1, -1, None, var, tocomplete
    line = data[:match.start(2)].count("\n") + 1
    column = len(data[:match.start(2)].split("\n")[-1])+1
    typename = match.group(1)
    return line, column, typename, var, tocomplete
