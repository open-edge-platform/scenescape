# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-analytics
TEST_IMAGE := intel/scenescape-analytics-test
TARGET = scenescape-analytics-runtime
TEST_TARGET = scenescape-analytics-test
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)"
