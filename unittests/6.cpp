struct mystruct {float x; float y; float z;} m;
typedef struct {float a; float b; float c; } mystruct2;

enum myenum
{
    I1,
    I2,
    I3
};

class A
{
public:
    enum
    {
        E1,
        E2,
        E3
    };

    enum NamedEnum
    {
        E4
    };

    union
    {
        float f;
        int i;
    };
    mystruct2 ms;
};


static int variable;
class MyStaticClass
{
public:
    static int publicStaticField;
    int publicField;

    template<typename T>
    static void publicStaticTemplateFunction(T& arg);
    template<typename T>
    void publicTemplateFunction(T& arg);
protected:
    static int protectedStaticField;
    int protectedField;
    template<typename T>
    static void protectedStaticTemplateFunction(T& arg);
    template<typename T>
    void protectedTemplateFunction(T& arg);
private:
    static int privateStaticField;
    int privateField;
    template<typename T>
    static void privateStaticTemplateFunction(T& arg);
    template<typename T>
    void privateTemplateFunction(T& arg);
};

class Child : public MyStaticClass
{
};
