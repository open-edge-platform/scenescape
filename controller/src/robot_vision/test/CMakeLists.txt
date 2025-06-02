# ----------------- BEGIN LICENSE BLOCK ---------------------------------
#
# INTEL CONFIDENTIAL
#
# Copyright (c) 2019-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were
# provided to you (License). Unless the License provides otherwise, you may not
# use, modify, copy, publish, distribute, disclose or transmit this software or
# the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express or
# implied warranties, other than those that are expressly stated in the License.
#
# ----------------- END LICENSE BLOCK -----------------------------------

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
