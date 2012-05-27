import sys
sys.path.append(".")
import translationunitcache
import os
import pickle
import sys
import gzip
import re
import platform

opts = []

golden = {}
testsAdded = False
tu = None
currfile = None

GOLDFILE = "unittests/gold.txt.gz"
debug = False
onlywarn = False
update = False
debugnew = False
dryrun = False
disableplatformspecific = False

for arg in sys.argv[1:]:
    if arg == "-debug":
        debug = True
    elif arg == "-warn":
        onlywarn = True
    elif arg == "-update":
        update = True
    elif arg == "-debugnew":
        debugnew = True
    elif arg == "-dryrun":
        dryrun = True
    elif arg == "-disableplatformspecific":
        disableplatformspecific = True
    else:
        raise Exception("Bad argument")


filter = re.compile("(^_.*\tmacro$)|(^__)|(OBJC_NEW_PROPERTIES)|(type_info)|(i386)")

if os.access(GOLDFILE, os.R_OK):
    f = gzip.GzipFile(GOLDFILE, 'rb')
    golden = pickle.load(f)
    for key in golden:
        if golden[key]:
            new = []
            for name in golden[key]:
                if not filter.match(name[0]):
                    new.append(name)
            golden[key] = new
    f.close()


def fail(message, forcewarn=False):
    if onlywarn or forcewarn:
        print message
    else:
        raise Exception(message)


def add_test(currtest, platformspecific=False):
    global off
    global testsAdded

    key = "%s-%s" % (currfile, currtest)
    dn = key not in golden and debugnew

    output = None
    if dn or not debugnew:
        output = tu.cache.complete(currtest, "")
    if output:
        new = []
        for name in output:
            if not filter.match(name[0]):
                new.append(name)
        output = new

    if debug or dn:
        print key
        if output == None:
            print "\tNone"
        elif len(output) == 0:
            print "\t[]"
        else:
            for data in output:
                print "\t%s" % str(data)
    if debugnew:
        return
    if not key in golden:
        golden[key] = output
        testsAdded = True
    else:
        gold = golden[key]
        if update:
            golden[key] = output
        if (gold == None and output != None) or (output == None and gold != None):
            fail("Test failed: %s - %s" % (key, "gold was None, output wasn't %s" % str(output) if gold == None else "output was None, but gold wasn't %s" % str(gold)))
        if platformspecific and disableplatformspecific:
            return
        if gold != None and output != None:
            max = len(gold)
            if len(output) > max:
                max = len(output)
            for i in range(max):
                g = gold[i] if i < len(gold) else None
                o = output[i] if i < len(output) else None
                if g != o:
                    fail("Mismatch in test: %s %s, %s != %s" % (currfile, currtest, g, o))


def get_tu(filename):
    global currfile
    currfile = filename
    myopts = []
    myopts.extend(opts)
    myopts.append("-x")
    myopts.append("c++")
    return translationunitcache.tuCache.get_translation_unit(filename, myopts)

# ---------------------------------------------------------

tu = get_tu("unittests/1.cpp")
add_test("", True)

# ---------------------------------------------------------

tu = get_tu("unittests/2.cpp")
add_test("Class1 c;\nc.")
add_test("void Class1::publicFunction() {", True)
add_test("void Class2::something() {", True)
add_test("Class1::")
add_test("void Class2::something() { Class1::")
add_test("Class3 c3; c3.")
add_test("void Class2::something() { Class3::")
add_test("void Class2::something() { Class3 c3; c3.")
add_test("void Class2::something() { this->")
add_test("void Class1::something() { this->")

# ---------------------------------------------------------

tu = get_tu("unittests/3.cpp")
add_test("std::", True)
add_test("std2::")
add_test("Test::")
add_test("namespace Test { ", True)
add_test(" ", True)
add_test("using namespace Test; ", True)
add_test("using namespace Test;\nusing namespace std; ", True)
add_test("std::vector<Test::Class1> t; t.", True)
add_test("using namespace Class1; std::vector<Class1> t; t.", True)
add_test("using namespace std; vector<Test::Class1> t; t.", True)
add_test("vector<Test::Class1> t; t.")
if platform.system() != "Windows":
    # For some reason this crashes in libclang on Windows..
    add_test("std::vector<Test::Class1> t; t[0].")
add_test("std::string s; s.")

# ---------------------------------------------------------

tu = get_tu("unittests/4.cpp")
add_test("C c; c.")
add_test("C c; c->")
add_test("C c; c[0].")
add_test("C c; c[0]->")
add_test("C *c; c[0].")
add_test("C *c; c[0][0].")
add_test("C *c; c[0]->")
add_test("C *c; c->")
add_test("C *c; c.")
add_test("void C::something() { singleA.")
add_test("void C::something() { singleA->")
add_test("void C::something() { singleA[0].")
add_test("void C::something() { singleA[0]->")
add_test("void C::something() { singleA[0][0].")
add_test("void C::something() { doubleA.")
add_test("void C::something() { doubleA->")
add_test("void C::something() { doubleA[0].")
add_test("void C::something() { doubleA[0]->")
add_test("void C::something() { doubleA[0][0].")
add_test("void C::something() { doubleA[0][0]->")
add_test("void C::something() { doubleA[0][0][0].")
add_test("void C::something() { tripleA.")
add_test("void C::something() { tripleA->")
add_test("void C::something() { tripleA[0].")
add_test("void C::something() { tripleA[0]->")
add_test("void C::something() { tripleA[0][0].")
add_test("void C::something() { tripleA[0][0]->")
add_test("void C::something() { tripleA[0][0][0].")
add_test("void C::something() { tripleA[0][0][0]->")
add_test("void C::something() { tripleA[0][0][0][0].")
add_test("void C::something() { singleB.")
add_test("void C::something() { singleB->")
add_test("void C::something() { singleB[0].")
add_test("void C::something() { singleB[0]->")
add_test("void C::something() { singleB[0][0].")
add_test("void C::something() { doubleB.")
add_test("void C::something() { doubleB->")
add_test("void C::something() { doubleB[0].")
add_test("void C::something() { doubleB[0]->")
add_test("void C::something() { doubleB[0][0].")
add_test("void C::something() { doubleB[0][0]->")
add_test("void C::something() { doubleB[0][0][0].")
add_test("void C::something() { tripleB.")
add_test("void C::something() { tripleB->")
add_test("void C::something() { tripleB[0].")
add_test("void C::something() { tripleB[0]->")
add_test("void C::something() { tripleB[0][0].")
add_test("void C::something() { tripleB[0][0]->")
add_test("void C::something() { tripleB[0][0][0].")
add_test("void C::something() { tripleB[0][0][0]->")
add_test("void C::something() { tripleB[0][0][0][0].")
add_test("void C::something() { getSingleA().")
add_test("void C::something() { getSingleA()->")
add_test("void C::something() { getSingleA()[0].")
add_test("void C::something() { getSingleA()[0]->")
add_test("void C::something() { getSingleA()[0][0].")
add_test("void C::something() { getDoubleA().")
add_test("void C::something() { getDoubleA()->")
add_test("void C::something() { getDoubleA()[0].")
add_test("void C::something() { getDoubleA()[0]->")
add_test("void C::something() { getDoubleA()[0][0].")
add_test("void C::something() { getDoubleA()[0][0]->")
add_test("void C::something() { getDoubleA()[0][0][0].")
add_test("void C::something() { getTripleA().")
add_test("void C::something() { getTripleA()->")
add_test("void C::something() { getTripleA()[0].")
add_test("void C::something() { getTripleA()[0]->")
add_test("void C::something() { getTripleA()[0][0].")
add_test("void C::something() { getTripleA()[0][0]->")
add_test("void C::something() { getTripleA()[0][0][0].")
add_test("void C::something() { getTripleA()[0][0][0]->")
add_test("void C::something() { getTripleA()[0][0][0][0].")
add_test("void C::something() { asinglemix.")
add_test("void C::something() { asinglemix->")
add_test("void C::something() { asinglemix[0].")
add_test("void C::something() { asinglemix[0]->")
add_test("void C::something() { asinglemix[0][0].")
add_test("void C::something() { asinglemix[0][0]->")
add_test("void C::something() { asinglemix.")
add_test("void C::something() { adoublemix1->")
add_test("void C::something() { adoublemix1[0].")
add_test("void C::something() { adoublemix1[0]->")
add_test("void C::something() { adoublemix1[0][0].")
add_test("void C::something() { adoublemix1[0][0]->")
add_test("void C::something() { adoublemix2->")
add_test("void C::something() { adoublemix2[0].")
add_test("void C::something() { adoublemix2[0]->")
add_test("void C::something() { adoublemix2[0][0].")
add_test("void C::something() { adoublemix2[0][0]->")

# ---------------------------------------------------------

tu = get_tu("unittests/5.cpp")
add_test("sp<A> t; t.")
add_test("sp<A> t; t.get().")
add_test("sp<A> t; t.get()->")
add_test("sp<A> t; t->")
add_test("sp<A> t; t[0].")
add_test("sp<A> t; t[0]->")
add_test("sp<B> t; t.")
add_test("sp<B> t; t.get().")
add_test("sp<B> t; t.get()->")
add_test("sp<B> t; t->")
add_test("sp<B> t; t[0].")
add_test("sp<B> t; t[0]->")
add_test("sp<C> t; t.")
add_test("sp<C> t; t->")
add_test("sp<C> t; t.get().")
add_test("sp<C> t; t.get()->")
add_test("sp<C> t; t[0].")
add_test("sp<C> t; t[0]->")
add_test("sp<A> t; t->afunction().")
add_test("sp2<A, B> t; t.")
add_test("sp2<A, B> t; t.funca()->")
add_test("sp2<A, B> t; t.funcb()->")
add_test("sp2<A, B> t; t.funca().")
add_test("sp2<A, B> t; t.funcb().")

# ---------------------------------------------------------

tu = get_tu("unittests/6.cpp")
add_test(" ")
add_test("myenum::")
add_test("myenum e; e.")
add_test("m.")
add_test("m s; s.")
add_test("mystruct2 s; s.")
add_test("A::")
add_test("A a; a.")
add_test("A a; a.f.")
add_test("A a; a.i.")
add_test("A a; a.ms.")

if (testsAdded or update) and not dryrun:
    f = gzip.GzipFile(GOLDFILE, "wb")
    pickle.dump(golden, f, -1)
    f.close()

print "All is well"
