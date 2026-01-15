# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

# Create SceneScape security hardening options target.
#
# This module automatically creates an INTERFACE target (scenescape::security_options)
# with common security hardening flags for secure coding practices.
# The target is created when this module is included.
#
# The security flags are applied only for non-Debug builds so debugging
# remains easy. Projects can link against scenescape::security_options to inherit
# these hardening flags.

# Idempotency guard
if(DEFINED RV_SECURITY_OPTIONS_CONFIGURED)
  return()
endif()

# If target already exists, nothing to do
if(TARGET scenescape::security_options)
  set(RV_SECURITY_OPTIONS_CONFIGURED TRUE)
  return()
endif()

# Create the security options target
add_library(scenescape_security_options INTERFACE)
add_library(scenescape::security_options ALIAS scenescape_security_options)

# Security hardening flags for secure coding practices.
# Applied only for non-Debug builds so debugging stays easy.
if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
  target_compile_options(scenescape_security_options INTERFACE
    -fstack-protector-strong
    -fstack-clash-protection
    -U_FORTIFY_SOURCE
    -D_FORTIFY_SOURCE=3
    -Wformat
    -Wformat-security
    -fno-strict-overflow
    -fno-delete-null-pointer-checks
  )

  target_link_options(scenescape_security_options INTERFACE
    -Wl,-z,relro,-z,now
    -Wl,-z,noexecstack
  )
endif()

set(RV_SECURITY_OPTIONS_CONFIGURED TRUE)

