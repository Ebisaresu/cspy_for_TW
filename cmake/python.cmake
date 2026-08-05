if(NOT BUILD_PYTHON)
  return()
endif()

# Use latest UseSWIG module
cmake_minimum_required(VERSION 3.14)

if(NOT TARGET ${PROJECT_NAME}::BiDirectionalCpp)
  message(FATAL_ERROR "Python: missing BiDirectional TARGET")
endif()

# Will need swig
set(CMAKE_SWIG_FLAGS)
find_package(SWIG REQUIRED)
include(UseSWIG)

if(${SWIG_VERSION} VERSION_GREATER_EQUAL 4)
  list(APPEND CMAKE_SWIG_FLAGS "-doxygen")
endif()

if(UNIX AND NOT APPLE)
  list(APPEND CMAKE_SWIG_FLAGS "-DSWIGWORDSIZE64")
endif()

# Find Python using env variable from github workflows
find_package(Python3 ${pythonVersion} REQUIRED COMPONENTS Interpreter
                                                          Development)

if(Python3_VERSION VERSION_GREATER_EQUAL 3)
  list(APPEND CMAKE_SWIG_FLAGS "-py3;-DPY3")
endif()

# Swig wrap all libraries
add_subdirectory(src/cc/python)

# Python Packaging  #

# setup.py.in contains cmake variable e.g. @PROJECT_NAME@ and generator
# expression e.g. $<TARGET_FILE_NAME:labelling>
configure_file(python/setup.py.in
               ${CMAKE_CURRENT_BINARY_DIR}/python/setup.py.in @ONLY)
# The importable package reads its version from this generated module, so that
# PROJECT_VERSION in the top level CMakeLists.txt is the only place to edit.
configure_file(python/version.py.in
               ${CMAKE_CURRENT_BINARY_DIR}/python/_version.py @ONLY)
file(
  GENERATE
  OUTPUT python/$<CONFIG>/setup.py
  INPUT ${CMAKE_CURRENT_BINARY_DIR}/python/setup.py.in)

# Find if python module MODULE_NAME is available, if not install it to the
# Python user install directory.
function(search_python_module MODULE_NAME)
  execute_process(
    COMMAND ${Python3_EXECUTABLE} -c
            "import ${MODULE_NAME}; print(${MODULE_NAME}.__version__)"
    RESULT_VARIABLE _RESULT
    OUTPUT_VARIABLE MODULE_VERSION
    ERROR_QUIET OUTPUT_STRIP_TRAILING_WHITESPACE)
  if(${_RESULT} STREQUAL "0")
    message(
      STATUS
        "Found python module: ${MODULE_NAME} (found version \"${MODULE_VERSION}\")"
    )
  else()
    message(
      WARNING
        "Can't find python module \"${MODULE_NAME}\", user install it using pip..."
    )
    # No --user here: pip refuses it inside a virtual environment, which used to
    # leave the module missing and made the build fail later on with
    # "ModuleNotFoundError: No module named 'setuptools'".
    execute_process(
      COMMAND ${Python3_EXECUTABLE} -m pip install --upgrade ${MODULE_NAME}
              OUTPUT_STRIP_TRAILING_WHITESPACE)
  endif()
endfunction()

# Under scikit-build-core the wheel is produced by the build backend and not by
# setup.py, so neither setuptools nor wheel is needed at configure time.
if(NOT SKBUILD)
  search_python_module(setuptools)
  search_python_module(wheel)
endif()
# search_python_module(virtualenv)

# The shared library is only a separate file when BUILD_SHARED_LIBS is on. The
# top level CMakeLists.txt turns it off whenever BUILD_PYTHON is on, so normally
# the core is already linked into the extension module and there is nothing to
# copy; copying a static library into .libs/ would only put a stray archive
# inside the wheel. The branch is kept so that a deliberate shared build still
# produces a working package.
if(BUILD_SHARED_LIBS)
  set(COPY_SHARED_LIBRARY_COMMAND
      COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:BiDirectionalCpp>
              ${PYTHON_PACKAGE_NAME}/.libs)
else()
  unset(COPY_SHARED_LIBRARY_COMMAND)
endif()

add_custom_target(
  python_package ALL
  # Create appropriate package structure
  COMMAND ${CMAKE_COMMAND} -E make_directory ${PYTHON_PACKAGE_NAME}
          ${PYTHON_PACKAGE_NAME}/.libs ${PYTHON_PACKAGE_NAME}/algorithms/
  # Copy setup generated file
  COMMAND ${CMAKE_COMMAND} -E copy $<CONFIG>/setup.py setup.py
  # Copy python source code
  COMMAND ${CMAKE_COMMAND} -E copy_directory ${PROJECT_SOURCE_DIR}/src/python/
          ${PYTHON_PACKAGE_NAME}/
  # Inject the generated version module (single source of truth: PROJECT_VERSION)
  COMMAND
    ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/python/_version.py
    ${PYTHON_PACKAGE_NAME}/_version.py
  # License files, both next to setup.py (for license_files) and inside the
  # package (for package_data). Two mechanisms on purpose: older setuptools
  # ignores the license_files argument.
  COMMAND ${CMAKE_COMMAND} -E copy ${PROJECT_SOURCE_DIR}/LICENSE.txt LICENSE.txt
  COMMAND ${CMAKE_COMMAND} -E copy ${PROJECT_SOURCE_DIR}/NOTICE.txt NOTICE.txt
  COMMAND ${CMAKE_COMMAND} -E copy ${PROJECT_SOURCE_DIR}/LICENSE.txt
          ${PYTHON_PACKAGE_NAME}/LICENSE.txt
  COMMAND ${CMAKE_COMMAND} -E copy ${PROJECT_SOURCE_DIR}/NOTICE.txt
          ${PYTHON_PACKAGE_NAME}/NOTICE.txt
  # Long description shown on the package index page
  COMMAND ${CMAKE_COMMAND} -E copy
          ${PROJECT_SOURCE_DIR}/python/README_PACKAGE.md README.md
  COMMAND ${CMAKE_COMMAND} -E remove_directory dist
  COMMAND ${CMAKE_COMMAND} -E make_directory ${PYTHON_PACKAGE_NAME}/.libs
  COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:pyBiDirectionalCpp>
          ${PYTHON_PACKAGE_NAME}/algorithms/
  ${COPY_SHARED_LIBRARY_COMMAND}
  # copy swig generated python interface file
  COMMAND
    ${CMAKE_COMMAND} -E copy
    ${CMAKE_CURRENT_BINARY_DIR}/python/pyBiDirectionalCpp.py
    ${PYTHON_PACKAGE_NAME}/algorithms/
  BYPRODUCTS python/${PYTHON_PACKAGE_NAME} python/build python/dist
             python/${PYTHON_PACKAGE_NAME}.egg-info
  WORKING_DIRECTORY python)

# The plain CMake workflow ("cmake --build build") keeps producing a wheel in
# build/python/dist/. Under scikit-build-core the backend builds the wheel, so
# this step is skipped there to avoid building it twice.
if(NOT SKBUILD)
  add_custom_command(
    TARGET python_package
    POST_BUILD
    COMMAND ${Python3_EXECUTABLE} setup.py bdist_wheel
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/python)
endif()

# Hand the package tree that python_package has just assembled to
# scikit-build-core. install(DIRECTORY) copies the files unchanged, so the
# extension module reaches the wheel exactly as it was linked.
if(SKBUILD)
  install(
    DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/python/${PYTHON_PACKAGE_NAME}/
    DESTINATION ${SKBUILD_PLATLIB_DIR}/${PYTHON_PACKAGE_NAME}
    COMPONENT Python)
endif()

# Test Look for python module virtualenv
if(BUILD_TESTING)
  search_python_module(virtualenv)
  # Testing using a vitual environment
  set(VENV_EXECUTABLE ${Python3_EXECUTABLE} -m virtualenv)
  set(VENV_DIR ${CMAKE_CURRENT_BINARY_DIR}/venv)
  if(WIN32)
    set(VENV_Python_EXECUTABLE "${VENV_DIR}\\Scripts\\python.exe")
  else()
    set(VENV_Python_EXECUTABLE ${VENV_DIR}/bin/python)
  endif()
  # make a virtualenv to install our python package in it
  add_custom_command(
    TARGET python_package
    POST_BUILD
    COMMAND ${VENV_EXECUTABLE} -p ${Python3_EXECUTABLE} ${VENV_DIR}
    # Must not call it in a folder containing the setup.py otherwise pip call it
    # (i.e. "python setup.py bdist") while we want to consume the wheel package
    COMMAND ${VENV_Python_EXECUTABLE} -m pip install -r
            ${PROJECT_SOURCE_DIR}/python/requirements.dev.txt
    COMMAND
      ${VENV_Python_EXECUTABLE} -m pip install
      --find-links=${CMAKE_CURRENT_BINARY_DIR}/python/dist --no-index
      ${PYTHON_DISTRIBUTION_NAME}
    BYPRODUCTS ${VENV_DIR}
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
  # run the tests within the virtualenv Test to be run from build/
  add_test(NAME python_unittest
           COMMAND ${VENV_Python_EXECUTABLE} -m unittest discover -s
                   ${PROJECT_SOURCE_DIR}/test/python/)
endif()

if(CMAKE_BUILD_TYPE EQUAL "Release")
  # TODO
endif()
