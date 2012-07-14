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
};

int main(int argc, char const *argv[])
{
    quat q;
    quat::test2 t;
    return 0;
}
