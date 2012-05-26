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

    union
    {
        float f;
        int i;
    };
};
