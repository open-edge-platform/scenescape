# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
project(frustum_gaussian VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---------------------------------------------------------------------------
# Compiler optimisation flags
# ---------------------------------------------------------------------------
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

option(FG_NATIVE_ARCH "Optimise for the build host CPU (non-portable binaries)" ON)

if(CMAKE_CXX_COMPILER_ID MATCHES "IntelLLVM|Intel")
  # Intel oneAPI DPC++/C++: full host ISA + inter-procedural optimisation
  add_compile_options(-xHost -ipo -qoverride-limits)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
  if(FG_NATIVE_ARCH)
    add_compile_options(-march=native)
  endif()
endif()

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

# Eigen 3.4 (header-only linear algebra — no link library needed)
find_package(Eigen3 3.4 REQUIRED NO_MODULE)

# Intel TBB — oneTBB 2021+ preferred, fall back to classic TBB
find_package(TBB 2021 QUIET)
if(NOT TBB_FOUND)
  find_package(TBB REQUIRED)
  message(STATUS "Using classic TBB (oneTBB 2021+ not found)")
else()
  message(STATUS "Using oneTBB ${TBB_VERSION}")
endif()

# Optional: pybind11 (only needed when building Python extension)
find_package(pybind11 QUIET)

# Optional: OpenVINO depth estimator head (future phase)
find_package(OpenVINO QUIET)
if(OpenVINO_FOUND)
  message(STATUS "OpenVINO ${OpenVINO_VERSION} found — depth estimator enabled")
else()
  message(STATUS "OpenVINO not found — depth estimator stub only")
endif()

# ---------------------------------------------------------------------------
# Core shared library: frustum_gaussian_core
# ---------------------------------------------------------------------------
add_library(frustum_gaussian_core SHARED
  src/frustum.cpp
  src/batch.cpp
)

target_include_directories(frustum_gaussian_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(frustum_gaussian_core
  PUBLIC  Eigen3::Eigen
  PRIVATE TBB::tbb
)

if(OpenVINO_FOUND)
  target_compile_definitions(frustum_gaussian_core PRIVATE FG_HAVE_OPENVINO)
  target_link_libraries(frustum_gaussian_core PRIVATE openvino::runtime)
endif()

set_target_properties(frustum_gaussian_core PROPERTIES
  VERSION   ${PROJECT_VERSION}
  SOVERSION ${PROJECT_VERSION_MAJOR}
  POSITION_INDEPENDENT_CODE ON
)

# ---------------------------------------------------------------------------
# Python extension module: _frustum_gaussian_cpp
# ---------------------------------------------------------------------------
if(pybind11_FOUND)
  pybind11_add_module(_frustum_gaussian_cpp
    python/bindings.cpp
  )
  target_link_libraries(_frustum_gaussian_cpp PRIVATE frustum_gaussian_core)

  if(SKBUILD)
    # Wheel build: both libraries live inside the package; resolve the core
    # shared library next to the extension module.
    set_target_properties(_frustum_gaussian_cpp PROPERTIES
      INSTALL_RPATH "$ORIGIN"
    )
  else()
    # Place the .so next to the Python package sources for editable installs
    set_target_properties(_frustum_gaussian_cpp PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY
        ${CMAKE_CURRENT_SOURCE_DIR}/../python/frustum_gaussian
    )
  endif()
else()
  message(STATUS "pybind11 not found — skipping Python extension")
endif()

# ---------------------------------------------------------------------------
# C++ unit tests (Google Test)
# ---------------------------------------------------------------------------
option(FG_BUILD_TESTS "Build C++ unit tests" ON)
if(FG_BUILD_TESTS)
  enable_testing()
  find_package(GTest CONFIG QUIET)
  if(NOT GTest_FOUND)
    find_package(GTest MODULE REQUIRED)
  endif()
  add_subdirectory(tests)
endif()

# ---------------------------------------------------------------------------
# Benchmarks (Google Benchmark)
# ---------------------------------------------------------------------------
option(FG_BUILD_BENCHMARKS "Build Google Benchmark suite" OFF)
if(FG_BUILD_BENCHMARKS)
  find_package(benchmark QUIET)
  if(benchmark_FOUND)
    add_subdirectory(benchmarks)
  else()
    message(STATUS "google-benchmark not found; to enable: install libbenchmark-dev")
  endif()
endif()

# ---------------------------------------------------------------------------
# Install rules
# ---------------------------------------------------------------------------
include(GNUInstallDirs)

if(SKBUILD)
  # Wheel build (scikit-build-core): install prefix is the wheel platlib root,
  # so install both libraries into the frustum_gaussian package directory.
  install(TARGETS frustum_gaussian_core
    LIBRARY DESTINATION frustum_gaussian
  )
  install(TARGETS _frustum_gaussian_cpp
    LIBRARY DESTINATION frustum_gaussian
  )
else()
  install(TARGETS frustum_gaussian_core
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  )

  install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

  if(pybind11_FOUND)
    install(TARGETS _frustum_gaussian_cpp
      LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    )
  endif()
endif()
