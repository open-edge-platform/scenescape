# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

find_package(GTest REQUIRED)
find_package(gRPC REQUIRED)
find_package(stduuid REQUIRED)
find_package(OpenSSL REQUIRED)

# Tracker library sources for testing (exclude main.cpp)
set(TRACKER_LIB_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/logger.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/cli.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/config_loader.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/scene_loader.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/api_scene_loader.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/manager_rest_client.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/coordinate_transformer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_server.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/healthcheck_command.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/mqtt_client.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/message_handler.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/scene_registry.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/time_chunk_buffer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/time_chunk_scheduler.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/tracking_worker.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/track_publisher.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/proxy_utils.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/time_utils.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/topic_utils.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/telemetry.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/metrics.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/observability_context.cpp
)

add_executable(tracker_tests
    logger_test.cpp
    cli_test.cpp
    config_loader_test.cpp
    coordinate_transformer_test.cpp
    healthcheck_server_test.cpp
    healthcheck_command_test.cpp
    mqtt_client_test.cpp
    message_handler_test.cpp
    scene_registry_test.cpp
    time_chunk_buffer_test.cpp
    tracking_worker_test.cpp
    proxy_utils_test.cpp
    track_publisher_test.cpp
    time_chunk_scheduler_test.cpp
    callback_guard_test.cpp
    topic_utils_test.cpp
    time_utils_test.cpp
    uuid_test.cpp
    id_map_test.cpp
    api_scene_loader_test.cpp
    manager_rest_client_test.cpp
    telemetry_test.cpp
    metrics_test.cpp
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

# Use C++20 standard (required for tracking_types.hpp)
target_compile_features(tracker_tests PRIVATE cxx_std_20)

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
        OpenMP::OpenMP_CXX
        scenescape::security_options
        PahoMqttCpp::paho-mqttpp3-static
        OpenSSL::SSL
        OpenSSL::Crypto
        stduuid::stduuid
        opentelemetry-cpp::opentelemetry-cpp
        opentelemetry-cpp::opentelemetry_exporter_in_memory
        grpc::grpc
)

# In-memory metric exporter static libs for testing.
# The Conan component marks these as header-only (LIBS empty),
# but the .a archives exist in the package lib dir.
find_library(OTEL_EXPORTER_IN_MEMORY_LIB
    NAMES opentelemetry_exporter_in_memory
    REQUIRED
)
find_library(OTEL_EXPORTER_IN_MEMORY_METRIC_LIB
    NAMES opentelemetry_exporter_in_memory_metric
    REQUIRED
)
target_link_libraries(tracker_tests PRIVATE
    ${OTEL_EXPORTER_IN_MEMORY_LIB}
    ${OTEL_EXPORTER_IN_MEMORY_METRIC_LIB}
)

set_property(TARGET tracker_tests PROPERTY CXX_STANDARD ${TRACKER_CXX_STANDARD})
set_property(TARGET tracker_tests PROPERTY CXX_STANDARD_REQUIRED ON)

include(GoogleTest)
gtest_discover_tests(tracker_tests
    DISCOVERY_MODE PRE_TEST
)
