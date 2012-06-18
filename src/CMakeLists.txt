cmake_minimum_required(VERSION 2.8)

if(NOT ${CMAKE_SYSTEM_NAME} MATCHES "Windows")
set(CMAKE_CXX_FLAGS "-g -Wall")
else()
    set(LIBPREFIX lib)
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

set(TARGETLIB ${LIBPREFIX}cache${LIBSUFFIX})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/..)


link_directories(${PROJECT_SOURCE_DIR}/..)
add_library(${TARGETLIB} SHARED main.cpp )
target_link_libraries(
    ${TARGETLIB}
    ${LIBPREFIX}clang${LIBSUFFIX}
)
if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
     add_custom_command(TARGET ${TARGETLIB}
        POST_BUILD
        COMMAND install_name_tool -change /tmp/llvm-3.1.src/build/lib/liblibclang.3.1.dylib libclang.dylib $<TARGET_FILE:cache>
        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )
elseif(${CMAKE_SYSTEM_NAME} MATCHES "Windows")

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

    add_custom_target(copy ALL
                    COMMAND copy ${TARGETLIB}.dll ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}
                    DEPENDS ${TARGETLIB}
    )
elseif(${CMAKE_SYSTEM_NAME} MATCHES "Linux")
    include(CheckFunctionExists)
    set(CMAKE_REQUIRED_FLAGS -L${CMAKE_LIBRARY_OUTPUT_DIRECTORY} -L/usr/local/lib -L/usr/lib)
    set(CMAKE_REQUIRED_LIBRARIES clang)
    check_function_exists(clang_getExpansionLocation HAS_RIGHT_CLANG)
    if(NOT HAS_RIGHT_CLANG)
        message("Either libclang wasn't found, or it's not useable as it doesn't have clang_getExpansionLocation.")
        message("libclang will be downloaded and compiled as part of the buildprocess.")
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
        add_custom_command(OUTPUT llvm/build/CMakeCache.txt
                        DEPENDS llvm
                        COMMAND cmake -DLLVM_TARGETS_TO_BUILD="X86" ..
                        WORKING_DIRECTORY llvm/build
        )

        add_custom_command(OUTPUT llvm/build/lib/liblibclang.so.3.1
                        COMMAND make -j 4 libclang
                        DEPENDS llvm/build/CMakeCache.txt
                        WORKING_DIRECTORY llvm/build
        )
        add_custom_command(OUTPUT ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang.so
                        COMMAND cp llvm/build/lib/liblibclang.so.3.1 ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang.so
                        DEPENDS llvm/build/lib/liblibclang.so.3.1
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
        )
        add_custom_target(libclang ALL DEPENDS ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang.so)
        add_dependencies(${TARGETLIB} libclang)
    endif()

endif()


add_custom_command(OUTPUT release
                    COMMAND mkdir release
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR})

add_custom_target(sublime-package
                    COMMAND rm -rf *
                    COMMAND find ../../.. -maxdepth 1 -type f -iregex \".*/[^.].*\" -exec cp {} . "\;"
                    COMMAND cp -r ../../../parsehelp parsehelp
                    COMMAND cp -r ../../../clang clang
                    COMMAND mkdir src
                    COMMAND find ../../../src -maxdepth 1 -type f  -exec cp {} src "\;"
                    COMMAND find ../../../src -maxdepth 1 -type d -not -regex \".*/build\" -not -regex \".*/src\" -exec cp -r {} src "\;"
                    COMMAND find . -name \".git*\" -exec rm -rf {} +
                    COMMAND find . -name \"*.pyc\" -exec rm -rf {} +
                    COMMAND find . -name \"unittest*\" -exec rm -rf {} +
                    COMMAND find . -name \"*.sublime-workspace\" -exec rm -rf {} +
                    COMMAND find . -name \"lib*.so\" -exec rm -rf {} +
                    COMMAND zip -r SublimeClang.sublime-package *
                    DEPENDS ${TARGETLIB} ${PROJECT_BINARY_DIR}/release
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release)
