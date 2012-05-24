import translationunitcache
import os
import pickle

opts = []

golden = {}
testsAdded = False
tu = None
currfile = None

GOLDFILE = "unittests/gold.txt"


if os.access(GOLDFILE, os.R_OK):
    f = open(GOLDFILE)
    golden = pickle.load(f)
    f.close()


def add_test(currtest):
    global off
    global testsAdded
    output = tu.cache.complete(currtest, "")

    key = "%s-%s" % (currfile, currtest)

    if output == None:
        output = []
    if not key in golden:
        golden[key] = output
        testsAdded = True
    else:
        gold = golden[key]
        if len(gold) != len(output):
            raise Exception("Length differs for test: %s %s" % (currfile, currtest))
        for i in range(len(gold)):
            if gold[i] != output[i]:
                raise Exception("Mismatch in test:\n%s\n%s\n%s != %s" % (currfile, currtest, gold[i], output[i]))


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
add_test("")

# ---------------------------------------------------------

tu = get_tu("unittests/2.cpp")
add_test("Class1 c;\nc.")
add_test("void Class1::publicFunction() {")
add_test("void Class2::something() {")
add_test("Class1::")
add_test("void Class2::something() { Class1::")
add_test("Class3 c3; c3.")
add_test("void Class2::something() { Class3::")
add_test("void Class2::something() { Class3 c3; c3.")
add_test("void Class2::something() { this->")
add_test("void Class1::something() { this->")

# ---------------------------------------------------------

tu = get_tu("unittests/3.cpp")
add_test("std::")
add_test("std2::")
add_test("Test::")
add_test("namespace Test { ")
add_test(" ")
add_test("using namespace Test; ")
add_test("using namespace Test;\nusing namespace std; ")
add_test("std::vector<Test::Class1> t; t.")
add_test("using namespace Class1; std::vector<Class1> t; t.")
add_test("using namespace std; vector<Test::Class1> t; t.")
add_test("vector<Test::Class1> t; t.")

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

if testsAdded:
    f = open(GOLDFILE, "w")
    pickle.dump(golden, f)
    f.close()

# for key in golden:
#     print key
#     for line in golden[key]:
#         print "\t%s" % str(line)

print "All is well"
