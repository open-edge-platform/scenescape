# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-controller
TEST_IMAGE := intel/scenescape-controller-test
TARGET = scenescape-controller-runtime
TEST_TARGET = scenescape-controller-test
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)"
