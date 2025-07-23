# SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

#####################################################################
# robot vision tests
#####################################################################
set(EXEC_NAME RobotVisionTests)

set(CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)

set(TEST_SOURCES
  main.cpp
  TrackingTests.cpp
)

add_executable(${EXEC_NAME} ${TEST_SOURCES})

target_compile_options(${EXEC_NAME} PRIVATE -fno-access-control)

target_include_directories(${EXEC_NAME}
  PRIVATE
  ${CMAKE_SOURCE_DIR}/include
)

target_link_libraries(${EXEC_NAME}
  PRIVATE
  ${PROJECT_NAME}
  GTest::gtest_main
)
add_test(NAME ${EXEC_NAME} COMMAND ${EXEC_NAME})
