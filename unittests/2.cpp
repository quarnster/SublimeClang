
class Class1
{
public:
    Class1(int pub);
    void publicFunction();
    int publicField;
    static void publicStaticFunction();
private:
    Class1(int pri);
    void privateFunction();
    int privateField;
    static void privateStaticFunction();
protected:
    Class1(int pro);
    void protectedFunction();
    static void protectedStaticFunction();
    int protectedField;

    static Class1* getInstance();
};

class Class2 : public Class1
{
private:
    void c2PrivateFunction();
    int c2PrivateField;
};

typedef Class2 Class3;

typedef struct
{
    int something;
} Test;

Test t2[1];
