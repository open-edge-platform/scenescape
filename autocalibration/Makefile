# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-camcalibration
RUNTIME_OS_IMAGE := ubuntu:22.04
TARGET = camcalibration-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-camcalibration-test" TARGET="camcalibration-test"
