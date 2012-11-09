class A
{
public:
    int hello;
};

class B
{
public:
    int world;
};

class SomeDefaultClass {};

template<typename T, typename T2>
class BaseClass
{
public:
    T   mT;
    T2  mT2;
};
template<typename T, typename T2=SomeDefaultClass> class Test
{
public:
    typedef BaseClass<T, T2>  BaseType;

    T *GetT();
    T2 *GetT2();

    BaseType *GetBase();
};

Test<A> test;
