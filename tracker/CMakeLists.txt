# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

cmake_minimum_required(VERSION 3.21)

#####################################################################
# Version from version.txt
#####################################################################

file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../version.txt" VERSION_CONTENT)
string(STRIP "${VERSION_CONTENT}" SCENESCAPE_VERSION)

# Extract major.minor.patch (strip any suffix like -dev)
string(REGEX MATCH "^[0-9]+\\.[0-9]+\\.[0-9]+" VERSION_SEMVER "${SCENESCAPE_VERSION}")

# Git commit hash: can be passed via -DGIT_COMMIT or GIT_COMMIT env var at build time
set(GIT_COMMIT "" CACHE STRING "Git commit hash (optional at configure, can use GIT_COMMIT env var at build)")
if(GIT_COMMIT)
  message(STATUS "Tracker version: ${SCENESCAPE_VERSION} (${GIT_COMMIT})")
else()
  message(STATUS "Tracker version: ${SCENESCAPE_VERSION} (GIT_COMMIT will be read from env at build time)")
endif()

#####################################################################
# Project
#####################################################################

project(tracker VERSION ${VERSION_SEMVER} LANGUAGES CXX)

set(TRACKER_CXX_STANDARD 20 CACHE STRING "C++ standard for Tracker targets")
option(BUILD_TESTS "Build unit tests" OFF)

# Enable coverage for debug builds
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} --coverage -fprofile-arcs -ftest-coverage")
  set(CMAKE_EXE_LINKER_FLAGS_DEBUG "${CMAKE_EXE_LINKER_FLAGS_DEBUG} --coverage")
endif()

#####################################################################
# Conan dependencies
#####################################################################

# Find Conan-installed packages
find_package(quill REQUIRED)
find_package(CLI11 REQUIRED)
find_package(simdjson REQUIRED)
find_package(httplib REQUIRED)
find_package(RapidJSON REQUIRED)

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
  ${CMAKE_CURRENT_SOURCE_DIR}/src/logger.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/cli.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/healthcheck_server.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src/healthcheck_command.cpp
)

add_executable(${PROJECT_NAME}
  ${PROJECT_SOURCE_LIST}
)

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD ${TRACKER_CXX_STANDARD})
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)
set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_EXTENSIONS OFF)

target_include_directories(${PROJECT_NAME}
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

# Inject version info as compile definitions
# GIT_COMMIT: use CMake variable if set, otherwise read from environment at build time
target_compile_definitions(${PROJECT_NAME}
  PRIVATE
    TRACKER_SERVICE_NAME="${PROJECT_NAME}"
    TRACKER_SERVICE_VERSION="${SCENESCAPE_VERSION}"
    $<IF:$<BOOL:${GIT_COMMIT}>,TRACKER_GIT_COMMIT="${GIT_COMMIT}",TRACKER_GIT_COMMIT="$ENV{GIT_COMMIT}">
)

target_link_libraries(${PROJECT_NAME}
  PRIVATE
    scenescape::security_options
    RobotVision
    quill::quill
    CLI11::CLI11
    simdjson::simdjson
    httplib::httplib
    rapidjson
)

#####################################################################
# Unit Tests
#####################################################################

if(BUILD_TESTS)
  enable_testing()
  add_subdirectory(test/unit)
endif()
