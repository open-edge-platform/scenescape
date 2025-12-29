# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# This file is licensed under Apache 2.0 License.

# RobotVision security options helpers.
#
# This module defines scene_define_security_options(), which creates an
# INTERFACE target with common security hardening flags. It replaces the
# previous implementation that lived under scene_common.
#
# Usage:
#   scene_define_security_options(<target_name>)
#
# The caller is responsible for creating any ALIAS targets (for example
# rv::security_options or Tracker::security_options) that point at the
# created INTERFACE library.

function(scene_define_security_options target_name)
	if(TARGET "${target_name}")
		return()
	endif()

	add_library("${target_name}" INTERFACE)

	# Security hardening flags (Intel Secure Coding Standards).
	# Applied only for non-Debug builds so debugging stays easy.
	if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
		target_compile_options("${target_name}" INTERFACE
			-fstack-protector-strong
			-fstack-clash-protection
			-U_FORTIFY_SOURCE
			-D_FORTIFY_SOURCE=3
			-Wformat
			-Wformat-security
			-fno-strict-overflow
			-fno-delete-null-pointer-checks
		)

		target_link_options("${target_name}" INTERFACE
			-Wl,-z,relro,-z,now
			-Wl,-z,noexecstack
		)
	endif()
endfunction()

