# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

cmake_minimum_required(VERSION 3.21)

#####################################################################
# Project
#####################################################################

project(tracker VERSION 0.0.1 LANGUAGES CXX)

set(TRACKER_CXX_STANDARD 20 CACHE STRING "C++ standard for Tracker targets")

#####################################################################
# RobotVision integration
#####################################################################

# Configure robot_vision subproject options: no Python, no tests/benchmarks.
set(RV_CXX_STANDARD 20 CACHE STRING "C++ standard for RobotVision targets" FORCE)
set(BUILD_PYTHON_BINDINGS OFF CACHE BOOL "Disable Python bindings in robot_vision" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "Disable tests in robot_vision" FORCE)
set(BUILD_BENCHMARKS OFF CACHE BOOL "Disable benchmarks in robot_vision" FORCE)

# Add robot_vision as a subdirectory (relative to scenescape root).
add_subdirectory(
  ${CMAKE_CURRENT_LIST_DIR}/../controller/src/robot_vision
  ${CMAKE_BINARY_DIR}/robot_vision
)

#####################################################################
# Executable
#####################################################################

set(PROJECT_SOURCE_LIST
  ${CMAKE_CURRENT_SOURCE_DIR}/src/main.cpp
)

add_executable(${PROJECT_NAME}
  ${PROJECT_SOURCE_LIST}
)

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD ${TRACKER_CXX_STANDARD})
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_EXTENSIONS OFF)

target_link_libraries(${PROJECT_NAME}
  PRIVATE
    scenescape::security_options
    RobotVision
)
