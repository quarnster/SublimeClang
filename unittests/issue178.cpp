typedef struct _TEST {
int field;
int field2;
}TEST;

struct TEST1 : public TEST
{

};

struct TEST2 : public _TEST
{

};
