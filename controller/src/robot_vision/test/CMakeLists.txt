# SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

#####################################################################
# robot vision tests
#####################################################################
set(EXEC_NAME RobotVisionTests)

set(TEST_SOURCES
  main.cpp
  TrackingTests.cpp
)

add_executable(${EXEC_NAME} ${TEST_SOURCES})

set_property(TARGET ${EXEC_NAME} PROPERTY CXX_STANDARD ${RV_CXX_STANDARD})
set_property(TARGET ${EXEC_NAME} PROPERTY CXX_STANDARD_REQUIRED ON)

target_compile_options(${EXEC_NAME} PRIVATE -fno-access-control)

target_include_directories(${EXEC_NAME}
  PRIVATE
  ${PROJECT_SOURCE_DIR}/include
)

target_link_libraries(${EXEC_NAME}
  PRIVATE
  ${PROJECT_NAME}
  scenescape::security_options
  GTest::gtest_main
)
add_test(NAME ${EXEC_NAME} COMMAND ${EXEC_NAME})
