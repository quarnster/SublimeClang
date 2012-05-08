cmake_minimum_required(VERSION 2.8)


set(CMAKE_CXX_FLAGS "-g -Wall")
IF(NOT CMAKE_BUILD_TYPE)
    SET(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING
        "Choose the type of build, options are: None Debug Release RelWithDebInfo MinSizeRel."
        FORCE)
ENDIF(NOT CMAKE_BUILD_TYPE)
include_directories(
    .
)

link_directories(${PROJECT_SOURCE_DIR}/..)
add_library(cache SHARED main.cpp )

target_link_libraries(
    cache
    clang
)

if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
     add_custom_command(TARGET cache
        POST_BUILD
        COMMAND install_name_tool -change /usr/local/lib/libclang.dylib libclang.dylib libcache.dylib
        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )
endif()
