
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


