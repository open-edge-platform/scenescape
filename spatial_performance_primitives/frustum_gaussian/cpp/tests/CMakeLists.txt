# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

add_executable(frustum_gaussian_core_tests core_test.cpp)
target_link_libraries(frustum_gaussian_core_tests
  PRIVATE frustum_gaussian_core GTest::gtest_main)
add_test(NAME frustum_gaussian_core_tests COMMAND frustum_gaussian_core_tests)