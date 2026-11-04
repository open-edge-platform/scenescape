# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-positioning
TEST_IMAGE := intel/scenescape-positioning-test
TARGET = scenescape-positioning-runtime
TEST_TARGET = scenescape-positioning-test
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)"