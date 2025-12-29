# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

# Ensure a unified OpenCV imported target exists.
#
# In our Ubuntu-based controller build we rely on system OpenCV
# (OpenCV_DIR is set to /usr/lib/x86_64-linux-gnu/cmake/opencv4).
# That config does not define a single opencv::opencv target, but
# instead exposes either opencv_world or an OpenCV_LIBS list. To keep
# RobotVision linking against a modern imported target everywhere,
# we synthesize opencv::opencv from those system-provided libraries.

function(rv_ensure_opencv_target)
  if(TARGET opencv::opencv)
    return()
  endif()

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
endfunction()
