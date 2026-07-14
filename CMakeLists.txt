cmake_minimum_required(VERSION 3.20)
project(yapping LANGUAGES C CXX)

include(FetchContent)
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)
find_package(SQLite3 REQUIRED)

set(BUILD_SHARED_LIBS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

FetchContent_Declare(
  lua
  URL https://www.lua.org/ftp/lua-5.4.7.tar.gz
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(lua)
file(GLOB LUA_SOURCES CONFIGURE_DEPENDS "${lua_SOURCE_DIR}/src/*.c")
list(REMOVE_ITEM LUA_SOURCES "${lua_SOURCE_DIR}/src/lua.c" "${lua_SOURCE_DIR}/src/luac.c")
add_library(yapping_lua STATIC ${LUA_SOURCES})
target_include_directories(yapping_lua PUBLIC "${lua_SOURCE_DIR}/src")
target_compile_definitions(yapping_lua PRIVATE LUA_USE_LINUX)

FetchContent_Declare(
  ocgcore
  GIT_REPOSITORY https://github.com/Fluorohydride/ygopro-core.git
  GIT_TAG db4fd16a99991802511b9a89e0025dd2f51f5e36
  GIT_SHALLOW FALSE
  SOURCE_SUBDIR cmake-unused
)
FetchContent_MakeAvailable(ocgcore)

# OCGCore's C++ header includes Lua's C headers without a linkage wrapper.
# Patch only the fetched build tree; the pinned upstream source is unchanged.
file(READ "${ocgcore_SOURCE_DIR}/interpreter.h" OCG_INTERPRETER_H)
string(REPLACE
  "#include <lua.h>\n#include <lauxlib.h>\n#include <lualib.h>"
  "extern \"C\" {\n#include <lua.h>\n#include <lauxlib.h>\n#include <lualib.h>\n}"
  OCG_INTERPRETER_H "${OCG_INTERPRETER_H}")
file(WRITE "${ocgcore_SOURCE_DIR}/interpreter.h" "${OCG_INTERPRETER_H}")

file(GLOB OCGCORE_SOURCES CONFIGURE_DEPENDS "${ocgcore_SOURCE_DIR}/*.cpp")
add_library(yapping_ocgcore STATIC ${OCGCORE_SOURCES})
target_include_directories(yapping_ocgcore PUBLIC "${ocgcore_SOURCE_DIR}")
target_link_libraries(yapping_ocgcore PUBLIC yapping_lua)
target_compile_features(yapping_ocgcore PUBLIC cxx_std_17)

pybind11_add_module(_ocgcore MODULE cpp/adapter.cpp)
target_link_libraries(_ocgcore PRIVATE yapping_ocgcore SQLite::SQLite3)
target_compile_features(_ocgcore PRIVATE cxx_std_17)
install(TARGETS _ocgcore DESTINATION yapping)
