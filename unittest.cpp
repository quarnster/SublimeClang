#include <vector>

class A
{
public:
    int test;
};

A a;
a.test;

std::vector<A> v;

v.front().test;


typedef std::vector<A> AV;

AV av;
av.front().test;

class B
{
public:
    AV variable;

    std::vector<A> variable2;
};

B b;
b.variable.front().test;
b.variable2.front().test;


class B2
{
public:
    std::vector<AV> variable;
    std::vector<std::vector<A> > variable2;
};

B2 b2;
b2.variable.front().back().test;
b2.variable2.front().back().test;


class B3
{
public:
    std::vector<std::vector<AV> > variable;
    std::vector<std::vector<std::vector<A> > > variable2;
};

B3 b3;
b3.variable.front().back().front().test;
b3.variable2.front().back().front().test;

