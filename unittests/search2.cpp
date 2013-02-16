#include <string.h>


void strncmp(...)
{
    return;
}

namespace something
{
void strncmp(...)
{
    return;
}

};

int strncmp(int a)
{
    return 0;
}

int  strncmp(const char *, const char *, size_t)
{
    return 0;
}

void strlen()
{
}

void Test::elsewhere()
{
}

int* returnsPointer()
{
    return NULL;
}

void elsewhere()
{
}

void Test::consttest() const
{

}

