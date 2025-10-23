# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-mapping
RUNTIME_OS_IMAGE := ubuntu:22.04
TARGET = mapping-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-mapping-test" TARGET="mapping-test"