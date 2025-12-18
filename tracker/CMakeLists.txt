# Tracker Service - CMake Configuration
# Minimum CMake version required (3.28 for modern features)
cmake_minimum_required(VERSION 3.28)
project(Tracker)

# Use C++20 standard and require it (no fallback to older standards)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Enable OpenMP for parallel processing
find_package(OpenMP REQUIRED)

# Generate compile_commands.json for IDE support (VSCode, etc.)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find required external packages
find_package(PahoMqttCpp REQUIRED)  # MQTT client library
find_package(simdjson REQUIRED)     # Fast JSON parser for deserialization
find_package(RapidJSON REQUIRED)    # Fast JSON serialization
find_package(Eigen3 REQUIRED)       # Eigen library for linear algebra (needed by robot_vision)
find_package(OpenCV REQUIRED)       # OpenCV library (needed by robot_vision)
find_package(opentelemetry-cpp REQUIRED)  # OpenTelemetry metrics and tracing
find_package(quill REQUIRED)         # High-performance structured logging library
find_package(httplib REQUIRED)       # HTTP/HTTPS client library for Manager API
find_package(GTest CONFIG REQUIRED)  # GoogleTest for unit tests

# Disable testing and Python bindings for robot_vision dependency
set(BUILD_TESTING OFF CACHE BOOL "Disable testing" FORCE)
set(BUILD_PYTHON_BINDINGS OFF CACHE BOOL "Disable Python bindings" FORCE)

# Pass Conan-generated package config path to robot_vision subdirectory
set(CMAKE_PREFIX_PATH ${CMAKE_PREFIX_PATH} CACHE PATH "CMake prefix path for finding packages")

# Add robot vision library as a subdirectory
add_subdirectory(../controller/src/robot_vision ${CMAKE_CURRENT_BINARY_DIR}/robot_vision)

# Link Eigen and OpenCV to RobotVision (needed by the subdirectory library)
target_link_libraries(RobotVision PUBLIC Eigen3::Eigen opencv::opencv)

# Define the tracker executable with source files
add_executable(tracker 
    src/main.cpp 
    src/mqtt_client.cpp 
    src/mqtt_msg.cpp 
    src/time_utils.cpp
    src/tracker.cpp 
    src/entities.cpp 
    src/publisher.cpp 
    src/config.cpp 
    src/scene_config.cpp 
    src/logger.cpp 
    src/metrics_manager.cpp 
    src/trace_manager.cpp 
    src/message_handler.cpp 
    src/time_chunk_buffer.cpp 
    src/time_chunk_processor.cpp 
    src/time_chunk_scheduler.cpp 
    src/config_fetcher.cpp
    src/config/file_config_source.cpp
    src/config/api_config_source.cpp
    src/config/config_source_factory.cpp
)

# Add include directories for headers
target_include_directories(tracker PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/inc)  # Public headers
target_include_directories(tracker PRIVATE ../controller/src/robot_vision/include) # Robot vision headers

# Define compile definitions for httplib SSL support
target_compile_definitions(tracker PRIVATE CPPHTTPLIB_OPENSSL_SUPPORT)

# Link required libraries
target_link_libraries(tracker PRIVATE RobotVision)                        # Robot vision library (tracker functionality)
target_link_libraries(tracker PRIVATE PahoMqttCpp::paho-mqttpp3-static)  # MQTT client 
target_link_libraries(tracker PRIVATE simdjson::simdjson)                # JSON deserialization
target_link_libraries(tracker PRIVATE rapidjson)                         # JSON serialization
target_link_libraries(tracker PRIVATE Eigen3::Eigen)                      # Eigen library for linear algebra
target_link_libraries(tracker PRIVATE quill::quill)                      # High-performance structured logging library
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_metrics)         # OpenTelemetry metrics
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_trace)           # OpenTelemetry tracing
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_exporter_otlp_http_metric)  # OTLP HTTP metrics exporter
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_exporter_otlp_http)         # OTLP HTTP trace exporter
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_exporter_otlp_http_client)  # OTLP HTTP client
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_common)           # OpenTelemetry common utilities
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_resources)        # OpenTelemetry resources
target_link_libraries(tracker PRIVATE opentelemetry-cpp::opentelemetry_http_client_curl) # HTTP client for OTLP
target_link_libraries(tracker PRIVATE httplib::httplib)                # HTTP/HTTPS client for Manager API
target_link_libraries(tracker PRIVATE OpenMP::OpenMP_CXX)  # OpenMP for parallel processing
target_link_libraries(tracker PRIVATE absl::time)


# ---- Unit Tests ----
enable_testing()
add_executable(tracker_unit_tests
    test/cpp/mqtt_msg_tests.cpp
    src/time_utils.cpp
)
target_include_directories(tracker_unit_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/inc)

target_link_libraries(tracker_unit_tests PRIVATE GTest::gtest_main)
target_link_libraries(tracker_unit_tests PRIVATE absl::time)
add_test(NAME tracker_unit_tests COMMAND tracker_unit_tests)
