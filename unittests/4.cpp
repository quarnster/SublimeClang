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
