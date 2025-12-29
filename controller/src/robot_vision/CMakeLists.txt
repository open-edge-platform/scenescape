# SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

cmake_minimum_required(VERSION 3.21)

#####################################################################
# Project
#####################################################################

project(RobotVision VERSION 1.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
include(cmake/security_options.cmake)  # scene_define_security_options()
include(cmake/opencv_shim.cmake)       # rv_ensure_opencv_target()

set(RV_CXX_STANDARD 17 CACHE STRING "C++ standard for RobotVision targets")

option(BUILD_PYTHON_BINDINGS "Build Python bindings with pybind11" ON)
option(BUILD_TESTING "Build tests" OFF)
option(BUILD_BENCHMARKS "Build performance benchmarks" OFF)

# Shared security hardening flags (reused by tracker via rv::security_options).
scene_define_security_options(rv_security_options)
add_library(rv::security_options ALIAS rv_security_options)

#####################################################################
# Dependencies
#####################################################################

find_package(OpenCV CONFIG REQUIRED)
find_package(Eigen3 CONFIG REQUIRED)
find_package(OpenMP REQUIRED)

# Normalize OpenCV usage to the synthetic opencv::opencv imported target.
rv_ensure_opencv_target()

if(BUILD_PYTHON_BINDINGS)
  find_package(Python REQUIRED COMPONENTS Interpreter Development)
  find_package(pybind11 CONFIG REQUIRED)
  message(STATUS "Python include dirs: ${Python_INCLUDE_DIRS} version: ${Python_VERSION} libs: ${Python_LIBRARIES}")
endif()

#####################################################################
# Library
#####################################################################

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
)

target_link_libraries(${PROJECT_NAME}
  PUBLIC
    Eigen3::Eigen
    opencv::opencv
    OpenMP::OpenMP_CXX
  PRIVATE
    rv::security_options
)

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD ${RV_CXX_STANDARD})
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)

#####################################################################
# Python bindings
#####################################################################

if(BUILD_PYTHON_BINDINGS)
  set(TRACKING_MODULE_SOURCE_LIST
    ${CMAKE_CURRENT_SOURCE_DIR}/python/src/robot_vision/extensions/tracking.cpp
  )

  pybind11_add_module(tracking MODULE ${TRACKING_MODULE_SOURCE_LIST})
  target_link_libraries(tracking PUBLIC ${PROJECT_NAME} Python::Python)

  pybind11_add_module(types MODULE  ${CMAKE_CURRENT_SOURCE_DIR}/python/src/robot_vision/extensions/types.cpp)
  target_link_libraries(types PUBLIC ${PROJECT_NAME} Python::Python)
endif()



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
  enable_testing()
  add_subdirectory(test)
endif(BUILD_TESTING)

#####################################################################
# benchmarks
#####################################################################

if(BUILD_BENCHMARKS)
  add_subdirectory(benchmarks)
endif(BUILD_BENCHMARKS)
