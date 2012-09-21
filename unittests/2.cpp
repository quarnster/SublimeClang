
class Class1
{
public:
    void publicFunction();
    int publicField;
    static void publicStaticFunction();
private:
    void privateFunction();
    int privateField;
    static void privateStaticFunction();
protected:
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
