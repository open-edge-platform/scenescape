# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-autocalibration
RUNTIME_OS_IMAGE := ubuntu:22.04
TARGET = autocalibration-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-autocalibration-test" TARGET="autocalibration-test"
