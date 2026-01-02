# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

find_package(GTest REQUIRED)

# Tracker library sources for testing (exclude main.cpp)
set(TRACKER_LIB_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/logger.cpp
)

add_executable(tracker_tests
    placeholder_test.cpp
    logger_test.cpp
    ${TRACKER_LIB_SOURCES}
)

target_include_directories(tracker_tests
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc
)

target_link_libraries(tracker_tests
    PRIVATE
        GTest::gtest
        GTest::gtest_main
        quill::quill
)

include(GoogleTest)
gtest_discover_tests(tracker_tests)
