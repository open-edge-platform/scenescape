# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

find_package(GTest REQUIRED)

add_executable(tracker_tests
    placeholder_test.cpp
)

target_link_libraries(tracker_tests
    PRIVATE
        GTest::gtest
        GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(tracker_tests)
