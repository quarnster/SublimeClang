cmake_minimum_required(VERSION 2.8)

include(CheckCXXSourceCompiles)

if(NOT ${CMAKE_SYSTEM_NAME} MATCHES "Windows")
set(CMAKE_CXX_FLAGS "-g -Wall")
else()
    if(MSVC)
        set(LIBPREFIX lib)
    endif()
    if(CMAKE_CL_64)
        set(LIBSUFFIX _x64)
    endif()

    foreach(flag_var
            CMAKE_CXX_FLAGS CMAKE_CXX_FLAGS_DEBUG CMAKE_CXX_FLAGS_RELEASE
            CMAKE_CXX_FLAGS_MINSIZEREL CMAKE_CXX_FLAGS_RELWITHDEBINFO)
       if(${flag_var} MATCHES "/MD")
          string(REGEX REPLACE "/MD" "/MT" ${flag_var} "${${flag_var}}")
       endif(${flag_var} MATCHES "/MD")
    endforeach(flag_var)
endif()

if(NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES i386 x86_64 CACHE STRING "Change architecture for a smaller build" FORCE)
endif()
IF(NOT CMAKE_BUILD_TYPE)
    SET(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING
            "Choose the type of build, options are: None Debug Release RelWithDebInfo MinSizeRel."
        FORCE)
ENDIF(NOT CMAKE_BUILD_TYPE)
include_directories(
    .
)

if(NOT DEFINED BUILD_LIBCLANG)
    set(BUILD_LIBCLANG False)
endif()

if(NOT DEFINED PARALLEL_COMPILES)
    set(PARALLEL_COMPILES 4)
endif()

macro(figure_out_cxx11_flags)
    set(SOURCE "#include <memory>\nint main(int argc, char** argv) { std::shared_ptr<int> sp; return 0;}")
    set(options "\;" "-std=c++11\;" "-std=c++11 -stdlib=libc++\;c++" "-std=gnu++11\;")
    list(LENGTH options options_len)
    math(EXPR options_len ${options_len}-1)
    foreach(var RANGE 0 ${options_len})
        list(GET options ${var} flags)
        list(GET flags 0 option)
        set(CMAKE_REQUIRED_FLAGS ${option})
        set(test_var HAVE_STD_SHARED_PTR${var})
        check_cxx_source_compiles("${SOURCE}" ${test_var})
        if(${${test_var}})
            list(GET flags 0 CX11FLAGS)
            list(GET flags 1 CX11LIBS)
            break()
        endif()
    endforeach(var)
    if(NOT DEFINED CX11FLAGS)
        unset(CMAKE_REQUIRED_FLAGS)
        set(SOURCE "#include <tr1/memory>\nint main(int argc, char** argv) { std::tr1::shared_ptr<int> sp; return 0;}")
        check_cxx_source_compiles("${SOURCE}" TR1_MEMORY)
        if(${TR1_MEMORY})
            set(CX11FLAGS "-DSUBLIMECLANG_USE_TR1")
        else()
            find_package(Boost REQUIRED)
            include_directories(${Boost_INCLUDE_DIR}/boost/tr1/tr1)
        endif()
    endif()
endmacro()

if(NOT DEFINED WIN_RELEASE)
    figure_out_cxx11_flags()
    file(READ "${PROJECT_SOURCE_DIR}/../package.json" TEMP)
    string(REGEX MATCH "(\"version\": \")([0-9]+\\.[0-9]+\\.[0-9]+)" TEMP ${TEMP})
    set(SUBLIMECLANG_VERSION ${CMAKE_MATCH_2})
    add_definitions(-DSUBLIMECLANG_VERSION="${CMAKE_MATCH_2}" ${CX11FLAGS})
    set(TARGETLIB ${LIBPREFIX}cache${LIBSUFFIX})
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/..)
    link_directories(${PROJECT_SOURCE_DIR}/.. /usr/local/lib /usr/lib /usr/lib64/llvm)
    add_library(${TARGETLIB} SHARED main.cpp )
    target_link_libraries(
        ${TARGETLIB}
        ${CX11LIBS}
        ${LIBPREFIX}clang${LIBSUFFIX}
    )
endif()

if(${CMAKE_SYSTEM_NAME} MATCHES "Windows" AND NOT DEFINED WIN_RELEASE)

    if(MSVC)
        set(MYPATTERN "[ \t\r\n]+([0-9]+)[ \t]+([0-9A-F]+)[ \t]+([0-9A-F]+)[ \t]+([a-zA-Z0-9_]+)")
        execute_process(COMMAND dumpbin /exports ${PROJECT_SOURCE_DIR}/../libclang${LIBSUFFIX}.dll OUTPUT_VARIABLE libclangdump)
        string(REGEX MATCHALL ${MYPATTERN} libclangdump ${libclangdump})
        string(REGEX REPLACE ${MYPATTERN} "\t\\4\t@\\1\n" libclangdump ${libclangdump})
        set(libclangdump "LIBRARY\tLIBCLANG${LIBSUFFIX}\nEXPORTS\n${libclangdump}")
        file(WRITE "${PROJECT_BINARY_DIR}/libclang${LIBSUFFIX}.def" ${libclangdump})
        add_custom_command(OUTPUT libclang${LIBSUFFIX}.lib
            COMMAND lib /def:libclang${LIBSUFFIX}.def /out:libclang${LIBSUFFIX}.lib
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
            COMMENT "Creating libclang.lib")
        add_custom_target(linklib ALL DEPENDS libclang${LIBSUFFIX}.lib)
        add_dependencies(${TARGETLIB} linklib)
    endif()
    get_target_property(cache_LOCATION ${TARGETLIB} LOCATION)
    add_custom_target(copy ALL
                    COMMAND ${CMAKE_COMMAND} -E copy ${cache_LOCATION} ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}
                    WORKING_DIRECTORY  ${PROJECT_BINARY_DIR}
                    DEPENDS ${TARGETLIB}
    )

elseif(NOT ${CMAKE_SYSTEM_NAME} MATCHES "Windows")
    include(CheckFunctionExists)
    string(REPLACE " " "\\ " CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_LIBRARY_OUTPUT_DIRECTORY} )
    set(CMAKE_REQUIRED_FLAGS "-isysroot / -L${CMAKE_LIBRARY_OUTPUT_DIRECTORY} -L/usr/local/lib -L/usr/lib")
    set(CMAKE_REQUIRED_LIBRARIES clang LLVM-3.1)
    check_function_exists(clang_getExpansionLocation HAS_RIGHT_CLANG)
    if(NOT HAS_RIGHT_CLANG)
        # Try again, but this time without LLVM-3.1
        set(CMAKE_REQUIRED_LIBRARIES clang)
        check_function_exists(clang_getExpansionLocation HAS_RIGHT_CLANG2)
    endif()
    if(NOT HAS_RIGHT_CLANG AND NOT HAS_RIGHT_CLANG2)
        message("Either libclang wasn't found, or it's not useable as it doesn't have clang_getExpansionLocation.")
        message("libclang will be downloaded and compiled as part of the buildprocess.")
        message("If you'd rather download a precompiled binary version for your distribution:")
        message("    1. Hit ctrl+c now")
        message("    2. Clean up the current configuration: rm -rf *")
        message("    3. Go to http://llvm.org/releases/download.html and find a release matching your distribution")
        message("    4. Extract the downloaded archive and copy the libclang.so to ${PROJECT_SOURCE_DIR}/../")
        message("    5. Run cmake .. again.")
        message("")
        message("This time if the libclang.so is useable, it'll skip the downloading and compilation of libclang.")
        set(BUILD_LIBCLANG True)
    endif()

endif()

if(BUILD_LIBCLANG)
    if(NOT EXISTS ./llvm.tar.gz)
        message("Downloading llvm...")
        file(DOWNLOAD http://www.llvm.org/releases/3.1/llvm-3.1.src.tar.gz ./llvm.tar.gz)
    endif()
    if(NOT EXISTS ./clang.tar.gz)
        message("Downloading clang...")
        file(DOWNLOAD http://www.llvm.org/releases/3.1/clang-3.1.src.tar.gz ./clang.tar.gz)
    endif()

    add_custom_command(OUTPUT llvm
                    COMMAND tar xfz llvm.tar.gz
                    COMMAND tar xfz clang.tar.gz
                    COMMAND mv llvm-3.1.src llvm
                    COMMAND mv clang-3.1.src llvm/tools/clang
                    COMMAND mkdir llvm/build
    )
    set(OSX_TEMP "\"${CMAKE_OSX_ARCHITECTURES}\"")
    string(REPLACE ";" "\;" OSX_TEMP "${OSX_TEMP}")
    add_custom_command(OUTPUT llvm/build/CMakeCache.txt
                    DEPENDS llvm
                    COMMAND cmake -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} -DLLVM_TARGETS_TO_BUILD="X86" -DCMAKE_OSX_ARCHITECTURES=${OSX_TEMP} ..
                    WORKING_DIRECTORY llvm/build
    )

    if(${CMAKE_SYSTEM_NAME} MATCHES "Linux")
        set(LIBCLANG_NAME "liblibclang.so.3.1")
    elseif(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
        set(LIBCLANG_NAME "liblibclang.3.1.dylib")
    else()
        message(FATAL_ERROR "Platform doesn't support building libclang at the moment. You'll have to manually tweak the CMakeLists.txt")
    endif()

    add_custom_command(OUTPUT llvm/build/lib/${LIBCLANG_NAME}
                    COMMAND make -j ${PARALLEL_COMPILES} libclang
                    DEPENDS llvm/build/CMakeCache.txt
                    WORKING_DIRECTORY llvm/build
    )

    set(COPY_TARGET "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang${CMAKE_SHARED_LIBRARY_SUFFIX}")
    string(REPLACE "\\" "" COPY_TARGET ${COPY_TARGET})
    add_custom_command(OUTPUT ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang${CMAKE_SHARED_LIBRARY_SUFFIX}
                    COMMAND ${CMAKE_COMMAND} -E copy llvm/build/lib/${LIBCLANG_NAME} ${COPY_TARGET}
                    DEPENDS llvm/build/lib/${LIBCLANG_NAME}
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )

    add_custom_target(libclang ALL DEPENDS ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang${CMAKE_SHARED_LIBRARY_SUFFIX})
    add_dependencies(${TARGETLIB} libclang)
endif()



if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
    add_custom_command(TARGET ${TARGETLIB}
                    POST_BUILD
                    COMMAND install_name_tool -change "${PROJECT_BINARY_DIR}/llvm/build/lib/${LIBCLANG_NAME}" libclang.dylib $<TARGET_FILE:cache>
                    COMMAND install_name_tool -change "/tmp/llvm-3.1.src/build/lib/liblibclang.3.1.dylib" libclang.dylib $<TARGET_FILE:cache>
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/../../)
    add_custom_command(OUTPUT release
                        COMMAND mkdir release
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR})

    add_custom_target(clean_release
                        COMMAND rm -rf *
                        DEPENDS ${PROJECT_BINARY_DIR}/release
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release
    )
    add_custom_target(prepare
                        COMMAND find ../../.. -maxdepth 1 -type f -iregex \".*/[^.].*\" -exec cp {} . "\;"
                        COMMAND cp -r ../../../parsehelp parsehelp
                        COMMAND cp -r ../../../clang clang
                        COMMAND mkdir src
                        COMMAND find ../../../src -maxdepth 1 -type f  -exec cp {} src "\;"
                        COMMAND find ../../../src -maxdepth 1 -type d -not -regex \".*/build.*\" -not -regex \".*/src\" -exec cp -r {} src "\;"
                        COMMAND find . -name \".git*\" -exec rm -rf {} +
                        COMMAND find . -name \"*.cache\" -exec rm -rf {} +
                        COMMAND find . -name \"*.sublime-workspace\" -exec rm -rf {} +
                        COMMAND find . -name \"lib*.so\" -exec rm -rf {} +
                        COMMAND find . -name \"*,cover\" -exec rm -rf {} +
                        COMMAND find . -name \".coverage\" -exec rm -rf {} +
                        DEPENDS ${TARGETLIB} ${PROJECT_BINARY_DIR}/release clean_release
                        DEPENDS ${PROJECT_SOURCE_DIR}/../libclang.dll ${PROJECT_SOURCE_DIR}/../libcache.dll
                        DEPENDS ${PROJECT_SOURCE_DIR}/../libclang_x64.dll ${PROJECT_SOURCE_DIR}/../libcache_x64.dll
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release
    )

    add_custom_target(unittest
                        COMMAND cp -r ../../../unittests unittests
                        COMMAND python unittests/unittest.py
                        COMMAND find . -name \"unittest*\" -exec rm -rf {} +
                        COMMAND find . -name \"*.pyc\" -exec rm -rf {} +
                        DEPENDS prepare
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release)

    add_custom_target(sublime-package
                        COMMAND zip -r SublimeClang-${SUBLIMECLANG_VERSION}.sublime-package *
                        DEPENDS unittest
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release
    )
endif()

if(DEFINED WIN_RELEASE)
    if(NOT EXISTS ./SublimeClang.sublime-package)
        message("Downloading current SublimeClang release...")
        file(DOWNLOAD http://cloud.github.com/downloads/quarnster/SublimeClang/SublimeClang.sublime-package ./SublimeClang.sublime-package)
    endif()
    add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/source
        COMMAND ${CMAKE_COMMAND} -E make_directory source
        COMMAND ${CMAKE_COMMAND} -E chdir source ${CMAKE_COMMAND} -E tar xf ../SublimeClang.sublime-package
        COMMAND ${CMAKE_COMMAND} -E copy_if_different source/libclang.dll ${PROJECT_SOURCE_DIR}/../libclang.dll
        COMMAND ${CMAKE_COMMAND} -E copy_if_different source/libclang_x64.dll ${PROJECT_SOURCE_DIR}/../libclang_x64.dll
        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )
    macro(win_build DIR TARGET LIB)
        if(${TARGET} MATCHES "/x86")
            set(CLANGLIB libclang.dll)
            set(PYTHON c:\\Python27\\python)
        else()
            set(CLANGLIB libclang_x64.dll)
            set(PYTHON c:\\Python27_x64\\python)
        endif()
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/../${CLANGLIB}
            COMMAND ${CMAKE_COMMAND} -E copy_if_different source/${CLANGLIB} ${PROJECT_SOURCE_DIR}/../${CLANGLIB}
            DEPENDS ${PROJECT_BINARY_DIR}/source
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
        )

        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${DIR}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/cmds.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "call \\\"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\SetEnv.cmd\\\" /Release ${TARGET}" > cmds.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "\\\"${CMAKE_COMMAND}\\\" -DCMAKE_BUILD_TYPE=MinSizeRel -G \\\"NMake Makefiles\\\" \\\"${PROJECT_SOURCE_DIR}\\\"" >> cmds.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR} ${PROJECT_BINARY_DIR}/source
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/build.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "call \\\"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\SetEnv.cmd\\\" /Release ${TARGET}" > build.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo nmake >> build.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/CMakeCache.txt
            COMMAND cmds.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}/cmds.bat ${PROJECT_BINARY_DIR}/../${CLANGLIB}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_SOURCE_DIR}/../${LIB}
            COMMAND build.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}/CMakeCache.txt ${PROJECT_BINARY_DIR}/${DIR}/build.bat
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_target(build_${LIB} ALL
            DEPENDS ${PROJECT_SOURCE_DIR}/../${LIB}
        )

        add_custom_target(unittest_${LIB} ALL
            COMMAND ${CMAKE_COMMAND} -E chdir .. ${PYTHON} unittests/unittest.py -disableplatformspecific
            DEPENDS build_${LIB}
            WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
        )
    endmacro()

    win_build(buildx86 "/x86" libcache.dll)
    win_build(buildx64 "/x64" libcache_x64.dll)
endif()

