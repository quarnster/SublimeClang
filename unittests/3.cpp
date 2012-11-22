#include <vector>
#include <string>

namespace blah = std::rel_ops;
namespace Test
{
    typedef std::vector<int> intvector;
    typedef std::vector<std::string> stringvector;
    class Class1
    {
        enum
        {
            E1_priv,
            E2_priv,
            E3_priv
        };
        public:
            enum
            {
                E1,
                E2,
                E3
            };
            Class1(int pub);
        private:
            Class1(char priv);
            int privatec1Member;
    };
    void Function1();
    int Field1;

    namespace Test2
    {
        namespace Test3
        {
            class T3Class
            {
                public:
                    static int t3Member;
            };
        }
    }
}
namespace a = Test;
namespace b = a::Test2;
namespace c = b::Test3;
namespace d = Test::Test2;
namespace e = Test::Test2::Test3;


namespace ZZZ
{
    using Test::Class1;
    using namespace Test::Test2::Test3;
    using namespace Test::Test2;

    namespace z = d;
};
