# SPDX-FileCopyrightText: 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#####################################################################
# robot vision benchmarks
#####################################################################
find_package(benchmark QUIET)

if(NOT benchmark_FOUND)
    message(STATUS "Google Benchmark not found on system; fetching v1.9.4 via FetchContent")
    include(FetchContent)
    set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
    set(BENCHMARK_ENABLE_GTEST_TESTS OFF CACHE BOOL "" FORCE)
    set(BENCHMARK_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        googlebenchmark
        GIT_REPOSITORY https://github.com/google/benchmark.git
        GIT_TAG v1.9.4
    )
    FetchContent_MakeAvailable(googlebenchmark)
endif()

message(STATUS "Building Robot Vision benchmarks.")

file(READ "${PROJECT_SOURCE_DIR}/include/rv/tracking/ObjectMatching.hpp" RV_OBJECT_MATCHING_HPP)
string(FIND "${RV_OBJECT_MATCHING_HPP}" "PositionMahalanobis" RV_POSITION_MAHALANOBIS_POS)

set(BENCHMARK_EXEC_NAME RobotVisionBenchmarks)

set(BENCHMARK_SOURCES
    MultipleObjectTrackerBenchmark.cpp
)

add_executable(${BENCHMARK_EXEC_NAME} ${BENCHMARK_SOURCES})

set_property(TARGET ${BENCHMARK_EXEC_NAME} PROPERTY CXX_STANDARD ${RV_CXX_STANDARD})
set_property(TARGET ${BENCHMARK_EXEC_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)

target_compile_options(${BENCHMARK_EXEC_NAME} PRIVATE
    -fno-access-control
    -O3
    -DNDEBUG
)

if(NOT RV_POSITION_MAHALANOBIS_POS EQUAL -1)
    target_compile_definitions(${BENCHMARK_EXEC_NAME} PRIVATE
        RV_HAS_POSITION_MAHALANOBIS=1
        RV_HAS_ASSOCIATION_MAX_RADIUS=1
    )
    message(STATUS "Benchmarks: PositionMahalanobis + max_radius track API enabled")
else()
    message(STATUS "Benchmarks: building without PositionMahalanobis (legacy tree)")
endif()

target_include_directories(${BENCHMARK_EXEC_NAME}
    PRIVATE
    ${PROJECT_SOURCE_DIR}/include
)

# Custom main() parses --people/--cameras/--association-config; do not link benchmark_main.
target_link_libraries(${BENCHMARK_EXEC_NAME}
    PRIVATE
    ${PROJECT_NAME}
    scenescape::security_options
    benchmark::benchmark
    pthread
)

add_custom_target(run_benchmark_track
    COMMAND ${BENCHMARK_EXEC_NAME}
    DEPENDS ${BENCHMARK_EXEC_NAME}
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    COMMENT "Running MultipleObjectTracker track() peak-FPS benchmark"
)

install(TARGETS ${BENCHMARK_EXEC_NAME}
    RUNTIME DESTINATION bin/benchmarks
    COMPONENT benchmarks
)
