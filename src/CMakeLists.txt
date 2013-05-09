cmake_minimum_required(VERSION 2.8)

include(CheckCXXSourceCompiles)

if(${CMAKE_SYSTEM_NAME} MATCHES "Windows")
    if(MSVC)
        set(LIBPREFIX lib)
    endif()
    if(CMAKE_CL_64 OR CMAKE_SIZEOF_VOID_P EQUAL 8)
        set(LIBSUFFIX _x64)
    endif()

    foreach(flag_var
            CMAKE_CXX_FLAGS CMAKE_CXX_FLAGS_DEBUG CMAKE_CXX_FLAGS_RELEASE
            CMAKE_CXX_FLAGS_MINSIZEREL CMAKE_CXX_FLAGS_RELWITHDEBINFO)
       if(${flag_var} MATCHES "/MD")
          string(REGEX REPLACE "/MD" "/MT" ${flag_var} "${${flag_var}}")
       endif(${flag_var} MATCHES "/MD")
    endforeach(flag_var)
    set(LLVM_USE_CRT_${CMAKE_BUILD_TYPE} MT)
endif()

if(NOT CMAKE_OSX_ARCHITECTURES AND NOT CMAKE_CROSS_COMPILING)
    set(CMAKE_OSX_ARCHITECTURES i386 x86_64 CACHE STRING "Change architecture for a smaller build" FORCE)
endif()
IF(NOT CMAKE_BUILD_TYPE)
    SET(CMAKE_BUILD_TYPE Release CACHE STRING
            "Choose the type of build, options are: None Debug Release RelWithDebInfo MinSizeRel."
        FORCE)
ENDIF(NOT CMAKE_BUILD_TYPE)
include_directories(
    .
)

set(CLANG_VERSION 3.2 CACHE STRING "Clang version to use")
set(LLVM_TARGETS_TO_BUILD "X86" CACHE STRING "LLVM targets to build")

if(NOT DEFINED BUILD_LIBCLANG)
    set(BUILD_LIBCLANG False)
endif()

macro(figure_out_cxx11_flags)
    set(SOURCE "#include <tr1/memory>\nint main(int argc, char** argv) { std::tr1::shared_ptr<int> sp; return 0;}")
    check_cxx_source_compiles("${SOURCE}" TR1_MEMORY)
    if(${TR1_MEMORY})
        set(CX11FLAGS "-DSUBLIMECLANG_USE_TR1")
    else()
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
            find_package(Boost REQUIRED)
            include_directories(${Boost_INCLUDE_DIR})
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
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/../internals)
    if(NOT APPLE)
        set(EXTRA_LIBRARY_DIRECTORY /usr/lib64/llvm)
    endif()
    link_directories(${CMAKE_LIBRARY_OUTPUT_DIRECTORY} /usr/local/lib /usr/lib ${EXTRA_LIBRARY_DIRECTORY})
    add_library(${TARGETLIB} SHARED main.cpp )
    target_link_libraries(
        ${TARGETLIB}
        ${CX11LIBS}
        ${LIBPREFIX}clang${LIBSUFFIX}
    )

    include(CheckFunctionExists)
    set(CMAKE_REQUIRED_FLAGS "-isysroot / -L\"${CMAKE_LIBRARY_OUTPUT_DIRECTORY}\" -L/usr/local/lib -L/usr/lib")
    set(CMAKE_REQUIRED_LIBRARIES clang LLVM-${CLANG_VERSION})
    check_function_exists(clang_getExpansionLocation HAS_RIGHT_CLANG)
    if(NOT HAS_RIGHT_CLANG)
        # Try again, but this time without LLVM-${CLANG_VERSION}
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
        message("    4. Extract the downloaded archive and copy the libclang.so to ${PROJECT_SOURCE_DIR}/../internals")
        message("    5. Run cmake .. again.")
        message("")
        message("This time if the libclang.so is useable, it'll skip the downloading and compilation of libclang.")
        set(BUILD_LIBCLANG True)
    endif()

    unset(CMAKE_REQUIRED_FLAGS)
    unset(CMAKE_REQUIRED_LIBRARIES)

endif()
set(COPY_TARGET "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/libclang${LIBSUFFIX}${CMAKE_SHARED_LIBRARY_SUFFIX}")

if(BUILD_LIBCLANG)
    if(NOT EXISTS ${PROJECT_BINARY_DIR}/llvm.tar.gz)
        message("Downloading llvm...")
        file(DOWNLOAD http://www.llvm.org/releases/${CLANG_VERSION}/llvm-${CLANG_VERSION}.src.tar.gz ${PROJECT_BINARY_DIR}/llvm.tar.gz)
    endif()
    if(NOT EXISTS ${PROJECT_BINARY_DIR}/clang.tar.gz)
        message("Downloading clang...")
        file(DOWNLOAD http://www.llvm.org/releases/${CLANG_VERSION}/clang-${CLANG_VERSION}.src.tar.gz ${PROJECT_BINARY_DIR}/clang.tar.gz)
    endif()

    if(NOT EXISTS ${PROJECT_BINARY_DIR}/llvm)
        message("Extracting LLVM")
        execute_process(COMMAND ${CMAKE_COMMAND} -E tar xfz llvm.tar.gz WORKING_DIRECTORY ${PROJECT_BINARY_DIR})
        execute_process(COMMAND ${CMAKE_COMMAND} -E rename llvm-${CLANG_VERSION}.src llvm WORKING_DIRECTORY ${PROJECT_BINARY_DIR})

        if(${CMAKE_SYSTEM_NAME} MATCHES "Windows")
            message(FATAL_ERROR "CMake can't extract clang.tar.gz due to http://public.kitware.com/Bug/view.php?id=13251\nPlease manually extract it and put it in llvm/tools/clang")
        else()
            message("Extracting Clang")
            execute_process(COMMAND ${CMAKE_COMMAND} -E tar xfz clang.tar.gz WORKING_DIRECTORY ${PROJECT_BINARY_DIR})
            execute_process(COMMAND ${CMAKE_COMMAND} -E rename clang-${CLANG_VERSION}.src llvm/tools/clang WORKING_DIRECTORY ${PROJECT_BINARY_DIR})
        endif()
    endif()
    if(MSVC)
        # TODO: Is this only for specific windows sdk versions?
        set(F "llvm\\lib\\Support\\Windows\\DynamicLibrary.inc")
        file(READ ${F} TEMP)
        string(REPLACE "ULONG ModuleBase" "DWORD64 ModuleBase" TEMP2 ${TEMP})
        if(NOT TEMP EQUAL TEMP2)
            message("Patching ${F}")
            file(WRITE ${F} TEMP2)
        endif()
    endif()

    if(NOT EXISTS ${PROJECT_BINARY_DIR}/native AND CMAKE_CROSSCOMPILING)
        execute_process(COMMAND ln -s ${PROJECT_BINARY_DIR}/../build2/llvm_out native WORKING_DIRECTORY ${PROJECT_BINARY_DIR})
    endif()
    add_subdirectory(${PROJECT_BINARY_DIR}/llvm ${PROJECT_BINARY_DIR}/llvm_out EXCLUDE_FROM_ALL)
    set_target_properties(libclang PROPERTIES OUTPUT_NAME "${LIBPREFIX}clang${LIBSUFFIX}")

    string(REPLACE "\\" "" COPY_TARGET ${COPY_TARGET})

    add_custom_target(copy ALL
                    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:libclang> ${COPY_TARGET}
                    DEPENDS libclang
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )

    if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
        add_custom_target(libclang_namechange ALL
                        COMMAND install_name_tool -id "@loader_path/libclang.dylib" $<TARGET_FILE:libclang>
                        VERBATIM
                    )
        add_dependencies(copy libclang_namechange)
    endif()
    add_dependencies(${TARGETLIB} copy)
endif()

if(${CMAKE_SYSTEM_NAME} MATCHES "Windows" AND NOT DEFINED WIN_RELEASE)
    if(MSVC)
        set(MYPATTERN "[ \t\r\n]+([0-9]+)[ \t]+([0-9A-F]+)[ \t]+([0-9A-F]+)[ \t]+([a-zA-Z0-9_]+)")
        execute_process(COMMAND dumpbin /exports ${COPY_TARGET} OUTPUT_VARIABLE libclangdump)
        string(REGEX MATCHALL ${MYPATTERN} libclangdump ${libclangdump})
        string(REGEX REPLACE ${MYPATTERN} "\t\\4\t@\\1\n" libclangdump ${libclangdump})
        set(libclangdump "LIBRARY\tLIBCLANG${LIBSUFFIX}\nEXPORTS\n${libclangdump}")
        file(WRITE "${PROJECT_BINARY_DIR}/libclang${LIBSUFFIX}.def" ${libclangdump})
        add_custom_command(OUTPUT libclang${LIBSUFFIX}.def
            COMMAND dumpbin /exports ${COPY_TARGET}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
            DEPENDS ${COPY_TARGET}
            COMMENT "Creating libclang.def")
        add_custom_command(OUTPUT libclang${LIBSUFFIX}.lib
            COMMAND lib /def:libclang${LIBSUFFIX}.def /out:libclang${LIBSUFFIX}.lib
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
            DEPENDS libclang${LIBSUFFIX}.def
            COMMENT "Creating libclang.lib")
        add_custom_target(linklib ALL DEPENDS libclang${LIBSUFFIX}.lib)
        add_dependencies(${TARGETLIB} linklib)
    endif()
    add_custom_target(copy2 ALL
                    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:${TARGETLIB}> ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}
                    WORKING_DIRECTORY  ${PROJECT_BINARY_DIR}
                    DEPENDS ${TARGETLIB}
                    VERBATIM
    )
endif()

if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
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
                        COMMAND cp -r ../../../internals internals
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
                        DEPENDS ${PROJECT_SOURCE_DIR}/../internals/libclang.dll ${PROJECT_SOURCE_DIR}/../internals/libcache.dll
                        DEPENDS ${PROJECT_SOURCE_DIR}/../internals/libclang_x64.dll ${PROJECT_SOURCE_DIR}/../internals/libcache_x64.dll
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release
    )

    add_custom_target(unittest
                        COMMAND cp -r ../../../unittests unittests
                        COMMAND python unittests/unittest.py
                        COMMAND find . -name \"unittest*\" -exec rm -rf {} +
                        COMMAND find . -name \"*.pyc\" -exec rm -rf {} +
                        DEPENDS prepare
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release)

    set(VERSION_SCRIPT "import re, sys\\; assert re.search\\(r\\\"\\\\d+\\\\.\\\\d+\\\\.\\\\d+\\\", sys.stdin.read\\(\\)\\).group\\(0\\) == '\"${SUBLIMECLANG_VERSION}\"'")

    add_custom_target(verify_versions
                    COMMAND strings libcache_x64.dll | python -c "${VERSION_SCRIPT}"
                    COMMAND strings libcache.dll | python -c "${VERSION_SCRIPT}"
                    COMMAND strings libcache.dylib | python -c "${VERSION_SCRIPT}"
                    DEPENDS prepare
                    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release/internals
    )
    set(PACKAGE_NAME SublimeClang-${SUBLIMECLANG_VERSION}.sublime-package)
    add_custom_target(sublime-package
                        COMMAND zip -r ${PACKAGE_NAME} *
                        DEPENDS verify_versions
                        DEPENDS unittest
                        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release
    )

    add_custom_target(upload
        COMMAND scp ${PACKAGE_NAME} quarn@frs.sourceforge.net:/home/frs/project/sublimeclang/${PACKAGE_NAME}
        DEPENDS sublime-package
        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/release)
endif()

if(DEFINED WIN_RELEASE)
    macro(win_build DIR TARGET LIB)
        if(${TARGET} MATCHES "/x86")
            set(CLANGLIB libclang.dll)
            set(PYTHON c:\\Python27\\python)
        else()
            set(CLANGLIB libclang_x64.dll)
            set(PYTHON c:\\Python27_x64\\python)
        endif()

        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${DIR}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/cmds.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "call \\\"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\SetEnv.cmd\\\" /Release ${TARGET}" > cmds.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "\\\"${CMAKE_COMMAND}\\\" -DCMAKE_BUILD_TYPE=MinSizeRel -G \\\"NMake Makefiles\\\" \\\"${PROJECT_SOURCE_DIR}\\\"" >> cmds.bat
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/build.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo "call \\\"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\SetEnv.cmd\\\" /Release ${TARGET}" > build.bat
            COMMAND ${CMAKE_COMMAND} ARGS -E echo nmake >> build.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_BINARY_DIR}/${DIR}/Makefile
            COMMAND cmds.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}/cmds.bat
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_command(OUTPUT ${PROJECT_SOURCE_DIR}/../internals/${LIB}
            COMMAND build.bat
            DEPENDS ${PROJECT_BINARY_DIR}/${DIR}/Makefile ${PROJECT_BINARY_DIR}/${DIR}/build.bat
            WORKING_DIRECTORY ${PROJECT_BINARY_DIR}/${DIR}
        )
        add_custom_target(build_${LIB} ALL
            DEPENDS ${PROJECT_SOURCE_DIR}/../internals/${LIB}
        )

        add_custom_target(unittest_${LIB} ALL
            COMMAND ${CMAKE_COMMAND} -E chdir .. ${PYTHON} unittests/unittest.py -disableplatformspecific -nogotoimp -nogotodef #TODO
            DEPENDS build_${LIB}
            WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
        )
    endmacro()

    win_build(buildx86 "/x86" libcache.dll)
    win_build(buildx64 "/x64" libcache_x64.dll)
endif()

