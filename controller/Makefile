# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

IMAGE := scenescape-controller
RUNTIME_OS_IMAGE := ubuntu:24.04
TARGET = scenescape-controller-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-controller-test" TARGET="scenescape-controller-test"
