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


def get_var_type(data, var):
    regex = re.compile("(\w[^( \t\{,\*\&]+)[ \t\*\&]+(%s)[ \t]*(\(|\;|,|\)|=)" % var)

    match = None
    for m in regex.finditer(data, re.MULTILINE):
        if m.group(1) == "return":
            continue
        sub = data[m.start(2):]
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
