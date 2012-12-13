typedef struct _TEST {
int field;
int field2;
}TEST;

struct TEST1 : public TEST
{

};

struct TEST2 : public _TEST
{

};


namespace test {
    namespace test2
    {
        class A
        {
        public:
            int field;
            int field2;
        };
    }
}

typedef test::test2::A _A;
namespace a = test::test2;
typedef a::A _A2;

class B1 : public _A {};
class B2 : public test::test2::A {};
class B3 : public a::A {};
class B4 : public _A2 {};
