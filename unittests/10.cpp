
#define TEST(a, b) a+b

class A
{
public:
    int variable;
};

A& function();
A* function2();

int ifunction();
int* ifunction2();

A a1;
A* a2;

namespace nms
{
    class Z
    {
        public:
            Z() {}
            int zvariable;
    };
    Z& function();
    Z* function2();
    Z z1;
    Z* z2;
}

namespace nms
{
    class Z2
    {
        public:
            int z2variable;
    };
    Z2& zfunction();
    Z2* zfunction2();

    float ffunction();
    float* ffunction2();
}

class B
{
public:
    static B* getInstance();

    int bvariable;
};

namespace na
{
    namespace nb
    {
        namespace nc = nms;
    }
}

namespace na
{
    namespace nb
    {
        class NBClass
        {

        };
    }
}

namespace na2
{
    namespace nb2
    {
        namespace nc2 = na;
    }
}

namespace na3 = nms;
namespace na4 = na2::nb2::nc2::nb;
namespace na5 = na2;
