# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

# Find and normalize OpenCV target interface for consistent linking.
#
# This module handles:
# 1. Finding OpenCV via find_package
# 2. Normalizing the target interface
#
# System OpenCV installations (Ubuntu libopencv-dev) provide inconsistent
# CMake interfaces - some expose opencv_world, others OpenCV_LIBS.
# This module creates a unified opencv::opencv namespace target for
# RobotVision to link against consistently across all build environments.

# Idempotency guard
if(DEFINED RV_OPENCV_TARGET_CONFIGURED)
  return()
endif()

# Find OpenCV
find_package(OpenCV CONFIG REQUIRED)

# If opencv::opencv already exists, nothing to do
if(TARGET opencv::opencv)
  set(RV_OPENCV_TARGET_CONFIGURED TRUE)
  return()
endif()

# Create opencv::opencv from available targets/variables
if(TARGET opencv_world)
  add_library(opencv::opencv INTERFACE IMPORTED)
  set_target_properties(opencv::opencv PROPERTIES
    INTERFACE_LINK_LIBRARIES opencv_world
  )
elseif(DEFINED OpenCV_LIBS)
  add_library(opencv::opencv INTERFACE IMPORTED)
  set_target_properties(opencv::opencv PROPERTIES
    INTERFACE_LINK_LIBRARIES "${OpenCV_LIBS}"
  )
else()
  message(FATAL_ERROR "OpenCV found but no opencv::opencv target or OpenCV_LIBS defined")
endif()

set(RV_OPENCV_TARGET_CONFIGURED TRUE)
