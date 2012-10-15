class A
{
public:
    void afunction();

};
class B
{
public:
    void bfunction();
};
class C
{
public:
    void cfunction();
    A& operator->()
    {
        return a;
    }
    B& operator[](int index)
    {
        return b;
    }

private:
    A a;
    B b;

    A *singleA;
    A **doubleA;
    A ***tripleA;
    B singleB[1];
    B doubleB[1][1];
    B tripleB[1][1][1];

    A* getSingleA();
    A** getDoubleA();
    A*** getTripleA();

    A *asinglemix[1];
    A *adoublemix1[1][1];
    A **adoublemix2[1];

};

class Test
{
public:
    enum Enum
    {
        One,
        Two,
        Three
    };
    int testMember;
};

struct quat
{
    struct { float x1, y2, z3, w4; };
    union
    {
        struct { float x, y, z, w; };
        struct { float a, b, c, d; } test;
        float f[4];
    };
    struct test2 {float e, f, g, h; };
    Test::Enum myEnum;
};

class Test2
{
public:
    union
    {
        long A1;
        int  B1;
        char C1;
    };
    union
    {
        long A2;
        int  B2;
        char C2;
    } UnionMember;
    enum
    {
        A3,
        B3,
        C3
    };
    enum
    {
        A4,
        B4,
        C4
    } EnumMember;

    int Member;
};
