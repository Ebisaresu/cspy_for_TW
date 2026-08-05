set_property(SOURCE bidirectional.i PROPERTY CPLUSPLUS ON)
set_property(SOURCE bidirectional.i PROPERTY SWIG_MODULE_NAME
                                             pyBiDirectionalCpp)
swig_add_library(
  pyBiDirectionalCpp
  TYPE SHARED
  LANGUAGE python OUTPUT_DIR ${CMAKE_BINARY_DIR}/python/
  SOURCES bidirectional.i)

set_property(TARGET pyBiDirectionalCpp
             PROPERTY SWIG_USE_TARGET_INCLUDE_DIRECTORIES ON)
target_include_directories(
  pyBiDirectionalCpp PRIVATE ${PROJECT_SOURCE_DIR}/src/cc
                             ${Python3_INCLUDE_DIRS})

# note: macOS is APPLE and also UNIX !
if(APPLE)
  set_target_properties(
    pyBiDirectionalCpp
    PROPERTIES SUFFIX ".so"
               INSTALL_RPATH
               # The extension module lives in <package>/algorithms/ and the
               # shared library in <package>/.libs/, so ../.libs is the shortest
               # path and does not depend on the package name at all. The last
               # entry is kept for backwards compatibility.
               "@loader_path;@loader_path/../.libs;@loader_path/../../${PYTHON_PACKAGE_NAME}/.libs"
    )
  # "-undefined dynamic_lookup" leaves the CPython symbols to be resolved by the
  # interpreter that loads this module, which is the standard way to link a
  # CPython extension on macOS.
  #
  # "-flat_namespace" used to be here as well and was removed on purpose. It
  # turns every symbol reference in this module into a search of the whole
  # process, so with the upstream "cspy" package also loaded the fork would call
  # into the upstream library instead of its own and report, for example, a
  # termination reason of "not_run" after a successful run. Two level namespaces
  # bind each reference to the library it was linked against.
  set_property(
    TARGET pyBiDirectionalCpp
    APPEND
    PROPERTY LINK_FLAGS "-undefined dynamic_lookup")
elseif(UNIX)
  set_target_properties(
    pyBiDirectionalCpp
    PROPERTIES
      INSTALL_RPATH
      "$ORIGIN:$ORIGIN/../.libs:$ORIGIN/../../${PYTHON_PACKAGE_NAME}/.libs")
endif()
target_link_libraries(pyBiDirectionalCpp PRIVATE BiDirectionalCpp LEMON::LEMON)

# Variable PYTHON_LIBRARIES can contains keyword `optimized` which won't be
# interpreted inside a generator expression. i.e. we can't use:
# $<$<PLATFORM_ID:Windows>:${PYTHON_LIBRARIES}> see:
# https://cmake.org/cmake/help/git-stage/command/target_link_libraries.html#command:target_link_libraries
if(MSVC)
  target_link_libraries(pyBiDirectionalCpp PRIVATE ${Python3_LIBRARIES})
endif()
