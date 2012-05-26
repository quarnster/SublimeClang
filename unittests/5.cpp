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

