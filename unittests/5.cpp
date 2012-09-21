template<typename T>
class sp
{
public:
    T* operator->() {return mT;}
    T* get() {return mT;}
    T* operator[](int i);
private:
    T* mT;
};

template<typename T, typename T2>
class sp2
{
public:
    T* funca();
    T2* funcb();
    void dosomething(T t, T2* t2);
};

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
    sp2<A, B> m_sp2;
};
