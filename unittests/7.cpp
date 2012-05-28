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
