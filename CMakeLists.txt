# From: https://github.com/Mizux/cmake-swig LICENSE: Apache License 2.0

# This file is just an orchestration
cmake_minimum_required(VERSION 3.14)
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# Apple: Don't modify install_name when touching RPATH.
if(POLICY CMP0068)
  cmake_policy(SET CMP0068 NEW)
endif()

# Define file(GENERATE) behavior for relative paths.
if(POLICY CMP0070)
  cmake_policy(SET CMP0070 NEW)
endif()

# target_sources: use absolute path for INTERFACE_SOURCES.
if(POLICY CMP0076)
  cmake_policy(SET CMP0076 NEW)
endif()

# option() honors normal variables. see:
# https://cmake.org/cmake/help/git-stage/policy/CMP0077.html
if(POLICY CMP0077)
  cmake_policy(SET CMP0077 NEW)
endif()

# SWIG: use standard target name.
if(POLICY CMP0078)
  cmake_policy(SET CMP0078 NEW)
endif()

# SWIG: use SWIG_MODULE_NAME property.
if(POLICY CMP0086)
  cmake_policy(SET CMP0086 NEW)
endif()

# Enable Python find by location
if(POLICY CMP0094)
  cmake_policy(SET CMP0094 NEW)
endif()

project(
  # Unchanged on purpose: PROJECT_NAME drives the C++ export set
  # (cspyTargets), the cspy:: namespace and cspyConfig.cmake. See cmake/cpp.cmake.
  cspy
  VERSION 1.1.0
  LANGUAGES CXX)
message(STATUS "project: ${PROJECT_NAME}")
message(STATUS "version: ${PROJECT_VERSION}")

# Python-facing names, deliberately decoupled from PROJECT_NAME.
# PYTHON_PACKAGE_NAME is the importable package ("import cspy_tw").
# PYTHON_DISTRIBUTION_NAME is what pip resolves ("pip install cspy-tw").
set(PYTHON_PACKAGE_NAME
    "cspy_tw"
    CACHE STRING "Importable Python package name (the 'import' name)")
set(PYTHON_DISTRIBUTION_NAME
    "cspy-tw"
    CACHE STRING "Distribution name used by pip (the 'pip install' name)")
message(STATUS "python package name: ${PYTHON_PACKAGE_NAME}")
message(STATUS "python distribution name: ${PYTHON_DISTRIBUTION_NAME}")

# Force default build type to Release
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE
      "Release"
      CACHE
        STRING
        "Choose the type of build, options are: Debug, Release (default), RelWithDebInfo and MinSizeRel."
        FORCE)
endif(NOT CMAKE_BUILD_TYPE)

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

# Layout build dir like install dir
include(GNUInstallDirs)
if(UNIX)
  option(BUILD_SHARED_LIBS "Build shared libraries(.so or .dyld)." ON)
  set(CMAKE_BUILD_WITH_INSTALL_RPATH TRUE)
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_LIBDIR})
  set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_LIBDIR})
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_BINDIR})
  # for multi-config build system (e.g. Xcode, ninja Multi-Config)
  foreach(OUTPUTCONFIG IN LISTS CMAKE_CONFIGURATION_TYPES)
    string(TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_LIBDIR})
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_LIBDIR})
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_BINDIR})
  endforeach()
else()
  option(BUILD_SHARED_LIBS "Build shared libraries (.dll)." OFF)
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_BINDIR})
  set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_BINDIR})
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY
      ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_BINDIR})
  # for multi-config builds (e.g. msvc)
  foreach(OUTPUTCONFIG IN LISTS CMAKE_CONFIGURATION_TYPES)
    string(TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_BINDIR})
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_BINDIR})
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG}
        ${CMAKE_BINARY_DIR}/${OUTPUTCONFIG}/${CMAKE_INSTALL_BINDIR})
  endforeach()
endif()

# By default only the ortools C++ library is built.
option(BUILD_CXX "Build C++ library" ON)
option(BUILD_PYTHON "Build Python Library" OFF)
option(BUILD_DOTNET "Build Dotnet Library" OFF)
set(LOG_LEVEL
    "WARN"
    CACHE
      STRING
      "Choose the logging level, options are: OFF (default), WARN, INFO, DEBUG, TRACE."
)

message(STATUS "Build C++ library: ${BUILD_CXX}, LOG_LEVEL= ${LOG_LEVEL}")
message(STATUS "Build Python: ${BUILD_PYTHON}")
message(STATUS "Build Dotnet: ${BUILD_DOTNET}")

# Two independently built copies of this code can end up in one Python process:
# the upstream "cspy" package and this fork, which is importable next to it. If
# each ships its own shared library, both export the same C++ symbols, and the
# symbols the compiler emits for inline functions, templates and vtables are
# weak. The dynamic loader coalesces weak definitions across the whole process,
# regardless of two level namespaces or of the file names of the libraries, so
# whichever package is loaded first supplies those definitions for both. The
# class layouts changed between the two versions, so this ends in a destructor
# from one version running on an object built by the other: wrong results first,
# then a heap corruption abort.
#
# Linking the core into the extension module and hiding every symbol that is not
# the module entry point leaves nothing for the loader to coalesce. The Windows
# build already worked this way; this makes every platform do the same.
if(BUILD_PYTHON)
  message(
    STATUS
      "Python: linking the C++ core into the extension module with hidden symbol visibility"
  )
  set(BUILD_SHARED_LIBS OFF)
  set(CMAKE_CXX_VISIBILITY_PRESET hidden)
  set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
  # A static library that is linked into a shared module has to be position
  # independent, and LEMON does not ask for that on its own.
  set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()

include(FetchContent)
set(FETCHCONTENT_QUIET OFF)
set(LEMON_BUILD_TESTING OFF)
# Remove shared libs for LEMON
set(BUILD_SHARED_LIBS_OLD ${BUILD_SHARED_LIBS})
set(BUILD_SHARED_LIBS OFF)
# Pinned to a commit rather than to the branch name "multiflow/dev". A branch
# name is a moving target: two builds of the same release tag would link against
# whatever that branch pointed at on the day they ran, and a force push upstream
# would silently change what users receive. Update this deliberately.
FetchContent_Declare(
  LEMON
  GIT_REPOSITORY "https://github.com/MultiFlow/LEMON.git"
  GIT_TAG "c047c06c5452a664bc8c82383dfccbecf1a6a87f")
FetchContent_MakeAvailable(LEMON)
set(BUILD_SHARED_LIBS ${BUILD_SHARED_LIBS_OLD})

# Add logger. Pinned to a commit for the same reason as LEMON above: "v1.x" is
# a branch, not a release tag.
FetchContent_Declare(
  spdlog
  GIT_REPOSITORY "https://github.com/gabime/spdlog.git"
  GIT_TAG "989d28dd768adef702538634857942db24e1058a")
FetchContent_MakeAvailable(spdlog)

enable_testing()
include(cpp)

if(WIN32
   AND (BUILD_PYTHON
        OR BUILD_JAVA
        OR BUILD_DOTNET))
  # Prefer a SWIG that is already available, for example the one that the "swig"
  # package from the Python Package Index puts on PATH inside the isolated build
  # environment of pip. Only fall back to downloading swigwin when there is
  # none, because that download overrides SWIG_EXECUTABLE unconditionally and it
  # goes over plain HTTP.
  find_program(SWIG_EXECUTABLE NAMES swig)
  if(NOT SWIG_EXECUTABLE)
    message(STATUS "Getting SWIG: ...")
    include(swig)
    message(STATUS "Getting SWIG: ...DONE")
  endif()
endif()

include(python)
include(dotnet)

# Fetch googletest and add C++ tests only if required
if(NOT (BUILD_PYTHON OR BUILD_DOTNET) AND BUILD_TESTING)
  set(FETCHCONTENT_QUIET OFF)
  # Prevent overriding the parent project's compiler/linker settings on Windows
  set(gtest_force_shared_crt
      ON
      CACHE BOOL "" FORCE)
  # Pinned to a commit for the same reason as LEMON and spdlog above: "main" is
  # a branch, so the C++ tests would otherwise be built against whatever
  # googletest happened to be that day.
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY "https://github.com/google/googletest.git"
    GIT_TAG "488c47cc68353ac94fda363e501c327e31261906")
  FetchContent_MakeAvailable(googletest)
  add_subdirectory(test/cc/)
endif()
