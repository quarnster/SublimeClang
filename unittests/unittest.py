import sys
sys.path.append(".")
import translationunitcache
import os
import os.path
import pickle
import sys
import gzip
import re
import platform

scriptpath = os.path.dirname(os.path.abspath(__file__))
opts = ["-I%s/../clang/include" % scriptpath]

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


filter = re.compile("(^_.*\tmacro$)|(^__)|(OBJC_NEW_PROPERTIES)|(type_info)|(i386)|linux|unix")

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


def add_test(currtest, platformspecific=False, noneok=False):
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
        if not (platformspecific and noneok) and ((gold == None and output != None) or (output == None and gold != None)):
            fail("Test failed: %s - %s" % (key, "gold was None, output wasn't %s" % str(output) if gold == None else "output was None, but gold wasn't %s" % str(gold)))
        if platformspecific and disableplatformspecific:
            return
        if gold != None and output != None:
            goldset = set(gold)
            outputset = set(output)
            ingold = goldset - outputset
            inoutput = outputset - goldset
            for i in ingold:
                fail("Test failed: %s - Was in gold but not output: %s" % (key, i))
            for i in inoutput:
                fail("Test failed: %s - Was in output but not gold: %s" % (key, i))


def get_tu(filename):
    global currfile
    currfile = filename
    myopts = []
    myopts.extend(opts)
    if filename.endswith(".cpp"):
        myopts.append("-x")
        myopts.append("c++")
    else:
        myopts.append("-ObjC")
    return translationunitcache.tuCache.get_translation_unit(filename, myopts)

# ---------------------------------------------------------

tu = get_tu("unittests/1.cpp")
add_test("", True)
add_test("new ", True)

# ---------------------------------------------------------

tu = get_tu("unittests/2.cpp")
add_test("Class1 c;\nc.")
add_test("void Class1::publicFunction() {", True)
add_test("void Class2::something() {", True)
add_test("Class1::")
add_test("void Class2::something() { Class1::")
add_test("void Class2::something() { Class2::")
add_test("Class3 c3; c3.")
add_test("void Class2::something() { Class3::")
add_test("void Class2::something() { Class3 c3; c3.")
add_test("void Class2::something() { this->")
add_test("void Class1::something() { this->")
add_test("Test t[1]; t.")
add_test("Test t[1]; t[0].")
add_test("new ")
add_test("new Cla")

f = open("unittests/2.cpp")
data = f.read()
f.close()
add_test(data + "Test t[1]; t.")
add_test(data + "Test t[1]; t[0].")
add_test(data + "t2.")
add_test(data + "t2[0].")


# ---------------------------------------------------------

tu = get_tu("unittests/3.cpp")
add_test("new ", True)
add_test("new std::", True)
add_test("new std::rel_ops::", True)
add_test("new std2::")
add_test("new blah::", True)
add_test("new Test::")
add_test("std::", True)
add_test("std2::")
add_test("Test::")
add_test("std::string::", True, True)
add_test("std::vector<int>::", True)
add_test("Test::Class1::")
add_test("Test::intvector::", True)
add_test("Test::intvector s; s.", True)
add_test("Test::intvector s; s[0].", True)
add_test("Test::stringvector::")
add_test("Test::stringvector s; s.")
add_test("Test::stringvector s; s[0].")
add_test("std::vector<std::string> s; s.", True)
add_test("std::vector<std::string> s; s.back().")
add_test("std::vector<std::string> s; s[0].")
add_test("namespace Test { ", True)
add_test(" ", True)
add_test("using namespace Test; ", True)
add_test("using namespace Test;\nusing namespace std; ", True)
add_test("std::vector<Test::Class1> t; t.", True)
add_test("using namespace Class1; std::vector<Class1> t; t.", True)
add_test("using namespace std; vector<Test::Class1> t; t.", True)
add_test("vector<Test::Class1> t; t.")
add_test("std::vector<Test::Class1> t; t[0].")
add_test("std::string s; s.", True, True)
add_test("blah::", True)
add_test("std::rel_ops::", True)
add_test("a::")
add_test("a::Test2::")
add_test("a::Test2::Test3::")
add_test("Test::")
add_test("Test::Test2::")
add_test("Test::Test2::Test3::")
add_test("b::")
add_test("c::")
add_test("d::")
add_test("e::")
add_test("a::Test2::Test3::T3Class::")
add_test("b::Test3::T3Class::")
add_test("c::T3Class::")
add_test("d::Test3::T3Class::")
add_test("d::T3Class::")
add_test("a::T3Class::")
add_test("e::T3Class::")
add_test("Test::Test2::Test3::T3Class::")
add_test("ZZZ::")
add_test("ZZZ::Class1::")
add_test("ZZZ::Test3::")
add_test("ZZZ::T3Class::")
add_test("ZZZ::Test2::")
add_test("ZZZ::Test3::T3Class::")
add_test("ZZZ::z::")
add_test("void Test::Class1::function(int something) {", True)
add_test("void Test::Class1::function(Class1 &other) { other.")

#---------------------------------------------------------

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
add_test("quat q; q.")
add_test("quat q; q.test.")
add_test("quat::")
add_test("quat::test2 t; t.")
add_test("quat q; q.myEnum.")
add_test("Test2 t2; t2.")
add_test("Test2 t2; t2.UnionMember.")
add_test("Test2 t2; t2.EnumMember.")
add_test("Test2::")
add_test("void Test2::something() { this->")
add_test("void Test2::something() { UnionMember.")
add_test("void Test2::something() { EnumMember.")
add_test("void Test2::something() { ", True)

f = open("unittests/3.cpp")
data = f.read()
f.close()

add_test(data + "quat q; q.myEnum.")
add_test(data + "Test2 t2; t2.")
add_test(data + "Test2 t2; t2.UnionMember.")
add_test(data + "Test2 t2; t2.EnumMember.")


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
add_test("C c; c.")
add_test("C c; c.m_sp2.")
add_test("C c; c.m_sp2.funca()->")
add_test("C c; c.m_sp2.funcb()->")
add_test("C c; c.m_sp2.funca().")
add_test("C c; c.m_sp2.funcb().")

# ---------------------------------------------------------

tu = get_tu("unittests/6.cpp")
add_test(" ", True)
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
add_test("MyStaticClass c; c.")
add_test("MyStaticClass::")
add_test("void MyStaticClass::something() { MyStaticClass::")
add_test("void MyStaticClass::something() { this->")
add_test("Child::")
add_test("void Child::something() { MyStaticClass::")
add_test("void Child::something() { Child::")
add_test("void Child::something() { this->")
add_test("void A::something() {")

f = open("unittests/6.cpp")
data = f.read()
f.close()
add_test(data + " ")
add_test(data + " myenum::")
add_test(data + " m.")
add_test(data + " A::")

# ---------------------------------------------------------

tu = get_tu("unittests/7.cpp")
add_test("A a; a.")
add_test("AArray.")
add_test("AArray[0].")
add_test("AArray test; test.")
add_test("AArray test; test[0].")
add_test("AArray *test; test.")
add_test("AArray *test; test[0].")
add_test("AArray *test; test[0][0].")
add_test("Test t; t.")
add_test("Test t; t.a.")
add_test("Test t; t.array.")
add_test("Test t; t.array[0].")
add_test("TestStruct i; i.")
add_test("TestStruct::")
add_test("TestStruct2::")
add_test("TS.")
add_test("TS[0].")
add_test("TS t; t.")
add_test("TS t; t[0].")
add_test("Test t[10]; t.")
add_test("Test t[10]; t[0].")
add_test("Test t[10][20]; t.")
add_test("Test t[10][20]; t[0].")
add_test("Test t[10][20]; t[0][0].")
add_test("Test *t[20]; t[0][0].")
add_test("Test *t[20]; t[0].")
add_test("Test *t[20]; t.")
add_test("size_t t; t.")
add_test("TestStruct2::MyClass::")
add_test("TestStruct2::MyClass m; m.")
add_test("TestStruct2::MyStruct::")
add_test("TestStruct2::MyStruct m; m.")
add_test("TestStruct2::MyEnum::")
add_test("TestStruct2::MyEnum e; e.")
add_test("void TestStruct2::blah() { someMember.")

f = open("unittests/7.cpp")
data = f.read()
f.close()
subdata = data[:data.rfind("*t;")+4]
add_test(subdata + "t.")
add_test(subdata + "t->")

subdata = data[:data.rfind(" a;")+4]
add_test(subdata + "a.")
add_test(subdata + "a->")
add_test(data + "c.")
add_test(data + "b.")
add_test(data + "i.")

# ---------------------------------------------------------

opts = [
            "-isysroot",
            "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.7.sdk/",
            "-F/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.7.sdk/System/Library/Frameworks",
            "-ICocoa"]
tu = get_tu("unittests/8.mm")
add_test(" ", True)
add_test("[Hello ")
add_test("Hello * h; [h ")
add_test("World * w; [w ")
add_test("World * w; [[w world] ")
add_test("World * w; [[w blah] ")
add_test("World2 * w; [[w world2] ")
add_test("World2 * w; [[[w world2] world] ")
add_test("World2 * w; w.")
add_test("World2 * w; w.world2.")
add_test("World2 * w; w.world2.world.")
add_test("""@implementation World2
- (World*) world2
{
[self """)
add_test("""@implementation World2
- (World*) world2
{
    self.""")

add_test("World3 *w; w.")
add_test("World3 *w; [w ")
add_test("World3 *w; w->")
add_test("World *w; w.")
add_test("World *w; w->")
add_test("World *w; w.world.")
add_test("World *w; w.world->")
add_test("World *w; w->worldVar.")
add_test("World *w; w->worldVar->")

f = open("unittests/8.mm")
data = f.read()
f.close()
add_test(data[:data.rfind(".")+1])
add_test("""@implementation World3
- (void) something
{
    """, True)

add_test("""@implementation World4
- (void) myworld
{
    """, True)
add_test("World4 *w; w.")
add_test("World4 *w; w->")
add_test("World4 *w; [w ")

add_test("World5 *w; [w ")

# ---------------------------------------------------------


if platform.system() == "Darwin":
    tu = get_tu("unittests/9.mm")
    add_test("[NSString ", True)
    add_test("NSString *s; [s ", True)

    add_test("[NSMutableData ", True)
    add_test("NSMutableData *s; [s ", True)

    add_test("Test t; [t.", True)
    add_test("Test t; [t.context ", True)


# ---------------------------------------------------------

tu = get_tu("unittests/10.cpp")
add_test("new nms::")
add_test("function().")
add_test("function()->")
add_test("function2().")
add_test("function2()->")
add_test("ifunction().")
add_test("ifunction()->")
add_test("ifunction2().")
add_test("ifunction2()->")
add_test("a1.")
add_test("a1->")
add_test("a2.")
add_test("a2->")
add_test("nms::function().")
add_test("nms::function()->")
add_test("nms::function2().")
add_test("nms::function2()->")
add_test("nms::ffunction().")
add_test("nms::ffunction()->")
add_test("nms::ffunction2().")
add_test("nms::ffunction2()->")
add_test("nms::z1.")
add_test("nms::z1->")
add_test("nms::z2.")
add_test("nms::z2->")
add_test("using namespace nms; zfunction().")
add_test("using namespace nms; zfunction()->")
add_test("using namespace nms; zfunction2().")
add_test("using namespace nms; zfunction2()->")
add_test("using namespace nms; z1.")
add_test("using namespace nms; z1->")
add_test("using namespace nms; z2.")
add_test("using namespace nms; z2->")
add_test("void A::something() { function().")
add_test("B::getInstance()->")
add_test("TES")

# ---------------------------------------------------------

if (testsAdded or update) and not dryrun:
    f = gzip.GzipFile(GOLDFILE, "wb")
    pickle.dump(golden, f, -1)
    f.close()

print "All is well"
