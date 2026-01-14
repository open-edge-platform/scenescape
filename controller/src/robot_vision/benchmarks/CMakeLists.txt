# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#####################################################################
# robot vision benchmarks
#####################################################################
# Check if benchmark library is available
find_package(benchmark QUIET)

if(benchmark_FOUND)
    message(STATUS "Google Benchmark found. Building benchmarks.")
    
    set(BENCHMARK_EXEC_NAME RobotVisionBenchmarks)
    
    set(BENCHMARK_SOURCES
        MultipleObjectTrackerBenchmark.cpp
    )
    
    add_executable(${BENCHMARK_EXEC_NAME} ${BENCHMARK_SOURCES})

    set_property(TARGET ${BENCHMARK_EXEC_NAME} PROPERTY CXX_STANDARD ${RV_CXX_STANDARD})
    set_property(TARGET ${BENCHMARK_EXEC_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)
    
    target_compile_options(${BENCHMARK_EXEC_NAME} PRIVATE 
        -fno-access-control
        -O3  # Optimize for benchmarking
        -DNDEBUG  # Disable debug assertions
    )
    
    target_include_directories(${BENCHMARK_EXEC_NAME}
        PRIVATE
        ${PROJECT_SOURCE_DIR}/include
    )
    
    target_link_libraries(${BENCHMARK_EXEC_NAME}
        PRIVATE
        ${PROJECT_NAME}
        scenescape::security_options
        benchmark::benchmark
        benchmark::benchmark_main
    )
    
    # Add custom target to run the 50-people tracking benchmark
    add_custom_target(run_benchmark_50_people
        COMMAND ${BENCHMARK_EXEC_NAME}
        DEPENDS ${BENCHMARK_EXEC_NAME}
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "Running 50-people tracking benchmark"
    )
    
    # Installation target for benchmarks
    install(TARGETS ${BENCHMARK_EXEC_NAME}
        RUNTIME DESTINATION bin/benchmarks
        COMPONENT benchmarks
    )
    
else()
    message(STATUS "Google Benchmark not found. Skipping benchmark build.")
    message(STATUS "To install Google Benchmark:")
    message(STATUS "  sudo apt-get install libbenchmark-dev  # Ubuntu/Debian")
    message(STATUS "  brew install google-benchmark         # macOS")
    message(STATUS "  Or build from source: https://github.com/google/benchmark")
endif()
