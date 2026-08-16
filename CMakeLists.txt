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
if(APPLE)
  target_compile_definitions(yapping_lua PRIVATE LUA_USE_MACOSX)
elseif(UNIX)
  target_compile_definitions(yapping_lua PRIVATE LUA_USE_LINUX)
endif()

FetchContent_Declare(
  ocgcore
  GIT_REPOSITORY https://github.com/Fluorohydride/ygopro-core.git
  GIT_TAG ee5c2ec7d6acfb583bfb7e26e6ee667db46677fa
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

FetchContent_Declare(
  lua53
  URL https://www.lua.org/ftp/lua-5.3.6.tar.gz
  URL_HASH SHA256=fc5fd69bb8736323f026672b1b7235da613d7177e72558893a0bdcd320466d60
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(lua53)
file(GLOB LUA53_SOURCES CONFIGURE_DEPENDS "${lua53_SOURCE_DIR}/src/*.c")
list(REMOVE_ITEM LUA53_SOURCES "${lua53_SOURCE_DIR}/src/lua.c" "${lua53_SOURCE_DIR}/src/luac.c")
add_library(yapping_lua53 STATIC ${LUA53_SOURCES})
target_include_directories(yapping_lua53 PUBLIC "${lua53_SOURCE_DIR}/src")
if(APPLE)
  target_compile_definitions(yapping_lua53 PRIVATE LUA_USE_MACOSX)
elseif(UNIX)
  target_compile_definitions(yapping_lua53 PRIVATE LUA_USE_LINUX)
endif()

FetchContent_Declare(
  ocgcore_ignis
  GIT_REPOSITORY https://github.com/edo9300/ygopro-core.git
  GIT_TAG 9a0c558c2d686542f7914a6d529fd7aa57746aed
  GIT_SHALLOW FALSE
  SOURCE_SUBDIR cmake-unused
)
FetchContent_MakeAvailable(ocgcore_ignis)

file(GLOB IGNIS_CORE_SOURCES CONFIGURE_DEPENDS "${ocgcore_ignis_SOURCE_DIR}/*.cpp")
add_library(yapping_ocgcore_ignis STATIC ${IGNIS_CORE_SOURCES})
target_include_directories(yapping_ocgcore_ignis PUBLIC "${ocgcore_ignis_SOURCE_DIR}")
target_link_libraries(yapping_ocgcore_ignis PUBLIC yapping_lua53)
target_compile_features(yapping_ocgcore_ignis PUBLIC cxx_std_17)
if(APPLE)
  set_source_files_properties(
    "${ocgcore_ignis_SOURCE_DIR}/processor_visit.cpp"
    PROPERTIES COMPILE_OPTIONS "-fno-exceptions")
endif()

pybind11_add_module(_ocgcore_ignis MODULE cpp/adapter_ignis.cpp)
target_link_libraries(_ocgcore_ignis PRIVATE yapping_ocgcore_ignis SQLite::SQLite3)
target_compile_features(_ocgcore_ignis PRIVATE cxx_std_17)
set_target_properties(
  yapping_lua53
  yapping_ocgcore_ignis
  _ocgcore_ignis
  PROPERTIES
  C_VISIBILITY_PRESET hidden
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON)
install(TARGETS _ocgcore_ignis DESTINATION yapping)
