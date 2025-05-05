# ----------------- BEGIN LICENSE BLOCK ---------------------------------
#
# INTEL CONFIDENTIAL
#
# Copyright (c) 2019-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were
# provided to you (License). Unless the License provides otherwise, you may not
# use, modify, copy, publish, distribute, disclose or transmit this software or
# the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express or
# implied warranties, other than those that are expressly stated in the License.
#
# ----------------- END LICENSE BLOCK -----------------------------------
cmake_minimum_required(VERSION 3.8)

include(FindPkgConfig)
include(GNUInstallDirs)
include(ExternalProject)
include(FetchContent)
include(CMakePackageConfigHelpers)

project(RobotVision VERSION 1.1.0)

set(CMAKE_CXX_STANDARD 14)
set(PROJECT_NAMESPACE rv)

set(ROBOT_VISION_BUILD_INSTALL_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/install)

option(BUILD_TESTING OFF)
set(PROJECT_BUILD_TESTING BUILD_TESTING)

# Required packages
find_package(OpenCV REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(Python REQUIRED COMPONENTS Interpreter Development)
find_package(pybind11 CONFIG REQUIRED)

message(STATUS ${Python_INCLUDE_DIRS} ${Python_VERSION} ${Python_LIBRARIES})

set(PROJECT_SOURCE_LIST
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/TrackedObject.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/CAModel.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/CVModel.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/CPModel.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/CTRVModel.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/UnscentedKalmanFilter.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/ObjectMatching.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/MultiModelKalmanEstimator.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/TrackManager.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/Classification.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/MultipleObjectTracker.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/tracking/TrackTracker.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/apollo/connected_component_analysis.cpp
  ${CMAKE_SOURCE_DIR}/src/rv/apollo/multi_hm_bipartite_graph_matcher.cpp
)

add_library(${PROJECT_NAME} SHARED ${PROJECT_SOURCE_LIST} )

target_include_directories(${PROJECT_NAME}
PUBLIC
${CMAKE_SOURCE_DIR}/include
${OpenCV_INCLUDE_DIRS}
${EIGEN3_INCLUDE_DIR}
${PYTHON_INCLUDE_DIRS}
${pybind11_INCLUDE_DIRS})

target_link_libraries(${PROJECT_NAME} PUBLIC ${OpenCV_LIBS} ${Python_LIBRARIES})

set(TRACKING_MODULE_SOURCE_LIST
  ${CMAKE_SOURCE_DIR}/python/src/robot_vision/extensions/tracking.cpp
)

pybind11_add_module(tracking MODULE ${TRACKING_MODULE_SOURCE_LIST})
target_link_libraries(tracking PUBLIC ${PROJECT_NAME})

pybind11_add_module(types MODULE  ${CMAKE_SOURCE_DIR}/python/src/robot_vision/extensions/types.cpp)
target_link_libraries(types PUBLIC ${PROJECT_NAME})

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD 14)

#####################################################################
# install
#####################################################################

install(TARGETS ${PROJECT_NAME} DESTINATION lib)

#####################################################################
# tests
#####################################################################

# Not working with ceres, ceres brings gtest as static lib gtest
if(PROJECT_BUILD_TESTING)
  include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)
  add_subdirectory(test)
endif(PROJECT_BUILD_TESTING)
