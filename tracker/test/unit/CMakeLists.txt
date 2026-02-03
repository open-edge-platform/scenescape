# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

find_package(GTest REQUIRED)

# Tracker library sources for testing (exclude main.cpp)
set(TRACKER_LIB_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/logger.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/cli.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/config_loader.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_server.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_command.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/mqtt_client.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/message_handler.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/proxy_utils.cpp
)

add_executable(tracker_tests
    logger_test.cpp
    cli_test.cpp
    config_loader_test.cpp
    healthcheck_server_test.cpp
    healthcheck_command_test.cpp
    mqtt_client_test.cpp
    message_handler_test.cpp
    ${TRACKER_LIB_SOURCES}
)

target_include_directories(tracker_tests
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc
        ${CMAKE_CURRENT_SOURCE_DIR}
)

# Define resource paths for tests (configured at CMake time)
target_compile_definitions(tracker_tests
    PRIVATE
        TRACKER_SCHEMA_DIR="${PROJECT_SOURCE_DIR}/schema"
        TRACKER_TEST_DIR="${PROJECT_SOURCE_DIR}/test/unit"
        TRACKER_CONFIG_DIR="${PROJECT_SOURCE_DIR}/config"
)

target_link_libraries(tracker_tests
    PRIVATE
        GTest::gtest
        GTest::gtest_main
        GTest::gmock
        quill::quill
        CLI11::CLI11
        httplib::httplib
        rapidjson
        RobotVision
        scenescape::security_options
        PahoMqttCpp::paho-mqttpp3-static
)

set_property(TARGET tracker_tests PROPERTY CXX_STANDARD ${TRACKER_CXX_STANDARD})
set_property(TARGET tracker_tests PROPERTY CXX_STANDARD_REQUIRED ON)

include(GoogleTest)
gtest_discover_tests(tracker_tests
    DISCOVERY_MODE PRE_TEST
)
