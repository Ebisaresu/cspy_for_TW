add_library(BiDirectionalCpp "")

# Configure
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config.h.in
               ${CMAKE_CURRENT_BINARY_DIR}/config.h)

target_sources(
  BiDirectionalCpp PRIVATE bidirectional.cc digraph.cc labelling.cc
                           preprocessing.cc search.cc ref_callback.cc
                           node_window_ref.cc)

target_include_directories(
  BiDirectionalCpp
  PUBLIC $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}>
         $<BUILD_INTERFACE:${PROJECT_BINARY_DIR}>
         $<BUILD_INTERFACE:${spdlog_SOURCE_DIR}/include>)

target_compile_features(BiDirectionalCpp PUBLIC cxx_std_20)

set_target_properties(BiDirectionalCpp PROPERTIES CXX_EXTENSIONS TRUE
                                                  VERSION ${PROJECT_VERSION})
set_target_properties(
  BiDirectionalCpp
  PROPERTIES CXX_EXTENSIONS TRUE
             VERSION ${PROJECT_VERSION}
             PUBLIC_HEADER "${CMAKE_CURRENT_BINARY_DIR}/config.h"
             VERSION ${PROJECT_VERSION})

target_link_libraries(BiDirectionalCpp PRIVATE LEMON::LEMON)

if(MSVC)
  # spdlog is consumed header-only here: only its include directory is added
  # above, and the spdlog CMake target is never linked. The /utf-8 option that
  # target carries as a PUBLIC usage requirement therefore never reaches this
  # project, and the fmt implementation bundled with spdlog refuses to compile
  # without it:
  #   error C2338: static_assert failed:
  #   'Unicode support requires compiling with /utf-8'
  # PUBLIC, so that the SWIG wrapper, which includes the same headers through
  # bidirectional.h, is compiled with it too.
  target_compile_options(BiDirectionalCpp PUBLIC /utf-8)
  # spdlog reaches <windows.h>. Its min and max are function-like macros, and
  # the preprocessor expands those wherever the token is followed by an opening
  # parenthesis, including in the qualified std::min( and std::max( calls in
  # this code. NOMINMAX suppresses them. WIN32_LEAN_AND_MEAN only trims what
  # <windows.h> pulls in, which keeps later collisions less likely.
  target_compile_definitions(BiDirectionalCpp PUBLIC NOMINMAX
                                                     WIN32_LEAN_AND_MEAN)
endif()

add_library(${PROJECT_NAME}::BiDirectionalCpp ALIAS BiDirectionalCpp)

# Install
include(GNUInstallDirs)
install(
  TARGETS BiDirectionalCpp
  EXPORT ${PROJECT_NAME}Targets
  PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/bidirectional
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} # RUNTIME DESTINATION
          # ${CMAKE_INSTALL_BINDIR}
)
