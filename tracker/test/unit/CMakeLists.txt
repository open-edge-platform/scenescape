# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

find_package(GTest REQUIRED)

# Tracker library sources for testing (exclude main.cpp)
set(TRACKER_LIB_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/logger.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/cli.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_server.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_command.cpp
)

add_executable(tracker_tests
    logger_test.cpp
    cli_test.cpp
    healthcheck_server_test.cpp
    healthcheck_command_test.cpp
    ${TRACKER_LIB_SOURCES}
)

target_include_directories(tracker_tests
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc
        ${CMAKE_CURRENT_SOURCE_DIR}/..
)

target_compile_definitions(tracker_tests
    PRIVATE
        TEST_SCHEMA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../../schema"
)

target_link_libraries(tracker_tests
    PRIVATE
        GTest::gtest
        GTest::gtest_main
        GTest::gmock
        quill::quill
        CLI11::CLI11
        simdjson::simdjson
        httplib::httplib
        rapidjson
        RobotVision
        scenescape::security_options
)

include(GoogleTest)
gtest_discover_tests(tracker_tests)
