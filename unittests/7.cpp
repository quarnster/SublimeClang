typedef struct A
{
    int a;
    int b;
    int c;

} AArray [10];

class Test
{
public:
    A a;
    AArray array;
};

typedef struct TestStruct
{
    enum { test1=0, test2 };

    unsigned int testfield;

} TS[10];

struct TestStruct2
{
    enum MyEnum { test3, test4};
    typedef long long MyType;
    class MyClass
    {
        public:
            int member;
    };
    struct MyStruct {};
    int someMember;
};
Test *t;

#include <cstring>
size_t a;

char c;
bool b;
int i;
