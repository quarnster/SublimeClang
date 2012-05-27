cmake_minimum_required(VERSION 2.8)


if(NOT ${CMAKE_SYSTEM_NAME} MATCHES "Windows")
set(CMAKE_CXX_FLAGS "-g -Wall")
else()
    set(LIBPREFIX lib)
    if(CMAKE_CL_64)
        set(LIBSUFFIX _x64)
    endif()

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

endif()

