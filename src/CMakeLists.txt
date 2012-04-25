cmake_minimum_required(VERSION 2.8)

find_package(Boost REQUIRED COMPONENTS regex)


set(CMAKE_CXX_FLAGS "-g -Wall -DSQLITE_THREADSAFE=2 -DSQLITE_DEFAULT_CACHE_SIZE=-50000 -DSQLITE_TEMP_STORE=3")
IF(NOT CMAKE_BUILD_TYPE)
  SET(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING
      "Choose the type of build, options are: None Debug Release RelWithDebInfo MinSizeRel."
      FORCE)
ENDIF(NOT CMAKE_BUILD_TYPE)

include_directories(
    .
    ${Boost_INCLUDE_DIRS}
)

#SET(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
SET(CMAKE_SKIP_BUILD_RPATH  FALSE)
SET(CMAKE_BUILD_WITH_INSTALL_RPATH TRUE)
#SET(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

SET(CMAKE_INSTALL_RPATH "\\$ORIGIN/../lib:\\$ORIGIN/:.")
link_directories(${PROJECT_SOURCE_DIR}/..)
add_library(nativeindexer SHARED main.cpp sqlite/sqlite3.c)
#set_target_properties(nativeindexer PROPERTIES INSTALL_RPATH ".")

target_link_libraries(nativeindexer clang ${Boost_LIBRARIES})


if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
     add_custom_command(TARGET nativeindexer
        POST_BUILD
        COMMAND install_name_tool -change /usr/local/lib/libclang.dylib libclang.dylib libnativeindexer.dylib
        WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    )
endif()
