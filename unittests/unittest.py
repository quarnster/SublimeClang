import translationunitcache
import os

opts = []


def add_test(output, golden_output_file):
    if output == None:
        output = []
    output = [str(a)+"\n" for a in output]
    if os.access(golden_output_file, os.R_OK):
        f = open(golden_output_file)
        golden_output = f.readlines()
        f.close()
        failed = len(golden_output) != len(output)
        if not failed:
            for i in range(len(output)):
                if output[i] != golden_output[i]:
                    print "output: %s\ngold: %s" % (output[i], golden_output[i])
                    failed = True
                    break
        if failed:
            raise Exception("Test failed: %s" % golden_output_file)
    else:
        f = open(golden_output_file, "w")
        f.writelines(output)
        f.close()


def get_tu(filename):
    myopts = []
    myopts.extend(opts)
    myopts.append("-x")
    myopts.append("c++")
    return translationunitcache.tuCache.get_translation_unit(filename, myopts)

# ---------------------------------------------------------

tu = get_tu("unittests/1.cpp")
add_test(tu.cache.complete("", ""), "unittests/1.txt")

# ---------------------------------------------------------

tu = get_tu("unittests/2.cpp")
add_test(tu.cache.complete("Class1 c;\nc.", ""), "unittests/2.txt")
add_test(tu.cache.complete("void Class1::publicFunction() {", ""), "unittests/2_1.txt")
add_test(tu.cache.complete("void Class2::something() {", ""), "unittests/2_2.txt")
add_test(tu.cache.complete("Class1::", ""), "unittests/2_3.txt")
add_test(tu.cache.complete("void Class2::something() { Class1::", ""), "unittests/2_4.txt")
add_test(tu.cache.complete("Class3 c3; c3.", ""), "unittests/2_5.txt")
add_test(tu.cache.complete("void Class2::something() { Class3::", ""), "unittests/2_6.txt")
add_test(tu.cache.complete("void Class2::something() { Class3 c3; c3.", ""), "unittests/2_7.txt")
add_test(tu.cache.complete("void Class2::something() { this->", ""), "unittests/2_8.txt")
add_test(tu.cache.complete("void Class1::something() { this->", ""), "unittests/2_9.txt")

# ---------------------------------------------------------

tu = get_tu("unittests/3.cpp")
add_test(tu.cache.complete("std::", ""), "unittests/3.txt")
add_test(tu.cache.complete("std2::", ""), "unittests/3_1.txt")
add_test(tu.cache.complete("Test::", ""), "unittests/3_2.txt")
add_test(tu.cache.complete("namespace Test { ", ""), "unittests/3_3.txt")
add_test(tu.cache.complete(" ", ""), "unittests/3_4.txt")
add_test(tu.cache.complete("using namespace Test; ", ""), "unittests/3_5.txt")
add_test(tu.cache.complete("using namespace Test;\nusing namespace std; ", ""), "unittests/3_6.txt")
add_test(tu.cache.complete("std::vector<Test::Class1> t; t.", ""), "unittests/3_7.txt")
add_test(tu.cache.complete("using namespace Class1; std::vector<Class1> t; t.", ""), "unittests/3_8.txt")
add_test(tu.cache.complete("using namespace std; vector<Test::Class1> t; t.", ""), "unittests/3_9.txt")
add_test(tu.cache.complete("vector<Test::Class1> t; t.", ""), "unittests/3_10.txt")

print "All is well"
