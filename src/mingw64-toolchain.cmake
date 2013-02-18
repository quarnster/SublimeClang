set(CMAKE_SYSTEM_NAME Windows)

set(CMAKE_C_COMPILER   /Developer/mingw64/bin/x86_64-w64-mingw32-gcc)
set(CMAKE_CXX_COMPILER /Developer/mingw64/bin/x86_64-w64-mingw32-g++)
set(CMAKE_RC_COMPILER  /Developer/mingw64/bin/x86_64-w64-mingw32-windres)


set(CMAKE_CXX_FLAGS_DEBUG "-gdwarf-2" CACHE STRING "c++ Debug flags" )
add_definitions("-mabi=ms -mms-aggregate-return")

set(CMAKE_SHARED_LINKER_FLAGS "-static-libgcc -static-libstdc++")

set(CMAKE_FIND_ROOT_PATH /Developer/mingw64/mingw)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)

set(CMAKE_CROSSCOMPILING True)
