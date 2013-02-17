set(CMAKE_SYSTEM_NAME Windows)

set(CMAKE_C_COMPILER   /Developer/mingw32/bin/i686-w64-mingw32-gcc)
set(CMAKE_CXX_COMPILER /Developer/mingw32/bin/i686-w64-mingw32-g++)
set(CMAKE_RC_COMPILER  /Developer/mingw32/bin/i686-w64-mingw32-windres)


set(CMAKE_SHARED_LINKER_FLAGS "-static-libgcc -static-libstdc++")

set(CMAKE_FIND_ROOT_PATH /Developer/mingw32/mingw)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)

set(CMAKE_CROSSCOMPILING True)
