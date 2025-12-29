# SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

cmake_minimum_required(VERSION 3.21)

include(GNUInstallDirs)

project(RobotVision VERSION 1.1.0 LANGUAGES CXX)

set(RV_CXX_STANDARD 17 CACHE STRING "C++ standard for RobotVision targets")

option(BUILD_PYTHON_BINDINGS "Build Python bindings with pybind11" ON)
option(BUILD_TESTING "Build tests" OFF)
option(BUILD_BENCHMARKS "Build performance benchmarks" OFF)

# Security hardening flags (Intel Secure Coding Standards).
# Applied only for non-Debug builds (e.g. Release) so debugging stays easy.
add_library(rv_security_options INTERFACE)
add_library(rv::security_options ALIAS rv_security_options)

if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
  target_compile_options(rv_security_options INTERFACE
    -fstack-protector-strong
    -fstack-clash-protection
    -U_FORTIFY_SOURCE
    -D_FORTIFY_SOURCE=3
    -Wformat
    -Wformat-security
    -fno-strict-overflow
    -fno-delete-null-pointer-checks
  )

  target_link_options(rv_security_options INTERFACE
    -Wl,-z,relro,-z,now
    -Wl,-z,noexecstack
  )
endif()

set(ROBOT_VISION_BUILD_INSTALL_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/install)

# Required packages
find_package(OpenCV CONFIG REQUIRED)
find_package(Eigen3 CONFIG REQUIRED)
find_package(OpenMP REQUIRED)

# Ensure a unified OpenCV imported target exists.
# In our Ubuntu-based controller build we rely on system OpenCV
# (OpenCV_DIR is set to /usr/lib/x86_64-linux-gnu/cmake/opencv4).
# That config does not define a single opencv::opencv target, but
# instead exposes either opencv_world or an OpenCV_LIBS list. To keep
# RobotVision linking against a modern imported target everywhere,
# we synthesize opencv::opencv from those system-provided libraries.
if(NOT TARGET opencv::opencv)
  if(TARGET opencv_world)
    add_library(opencv::opencv INTERFACE IMPORTED)
    set_target_properties(opencv::opencv PROPERTIES
      INTERFACE_LINK_LIBRARIES opencv_world
    )
  elseif(DEFINED OpenCV_LIBS)
    add_library(opencv::opencv INTERFACE IMPORTED)
    set_target_properties(opencv::opencv PROPERTIES
      INTERFACE_LINK_LIBRARIES "${OpenCV_LIBS}"
    )
  else()
    message(FATAL_ERROR "OpenCV found but no opencv::opencv target or OpenCV_LIBS defined")
  endif()
endif()

if(BUILD_PYTHON_BINDINGS)
  find_package(Python REQUIRED COMPONENTS Interpreter Development)
  find_package(pybind11 CONFIG REQUIRED)
  message(STATUS "Python include dirs: ${Python_INCLUDE_DIRS} version: ${Python_VERSION} libs: ${Python_LIBRARIES}")
endif()

set(PROJECT_SOURCE_LIST
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/TrackedObject.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/CAModel.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/CVModel.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/CPModel.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/CTRVModel.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/UnscentedKalmanFilter.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/ObjectMatching.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/MultiModelKalmanEstimator.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/TrackManager.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/Classification.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/MultipleObjectTracker.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/TrackTracker.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/tracking/CameraUtils.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/apollo/connected_component_analysis.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/rv/apollo/multi_hm_bipartite_graph_matcher.cpp
)

add_library(${PROJECT_NAME} SHARED ${PROJECT_SOURCE_LIST} )

target_include_directories(${PROJECT_NAME}
PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  # ${OpenCV_INCLUDE_DIRS}  # Dropped as per new requirements
)

target_link_libraries(${PROJECT_NAME}
  PUBLIC
    Eigen3::Eigen
    opencv::opencv
    OpenMP::OpenMP_CXX
  PRIVATE
    rv::security_options
)

if(BUILD_PYTHON_BINDINGS)
  set(TRACKING_MODULE_SOURCE_LIST
    ${CMAKE_CURRENT_SOURCE_DIR}/python/src/robot_vision/extensions/tracking.cpp
  )

  pybind11_add_module(tracking MODULE ${TRACKING_MODULE_SOURCE_LIST})
  target_link_libraries(tracking PUBLIC ${PROJECT_NAME} Python::Python)

  pybind11_add_module(types MODULE  ${CMAKE_CURRENT_SOURCE_DIR}/python/src/robot_vision/extensions/types.cpp)
  target_link_libraries(types PUBLIC ${PROJECT_NAME} Python::Python)
endif()

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD ${RV_CXX_STANDARD})
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)

#####################################################################
# install
#####################################################################

install(TARGETS ${PROJECT_NAME} DESTINATION lib)

#####################################################################
# tests
#####################################################################

# Not working with ceres, ceres brings gtest as static lib gtest
if(BUILD_TESTING)
  include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/gtest.cmake)
  add_subdirectory(test)
endif(BUILD_TESTING)

#####################################################################
# benchmarks
#####################################################################

if(BUILD_BENCHMARKS)
  add_subdirectory(benchmarks)
endif(BUILD_BENCHMARKS)
