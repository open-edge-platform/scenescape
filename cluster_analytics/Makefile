# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-cluster-analytics
TEST_IMAGE := intel/scenescape-cluster-analytics-test
TARGET = scenescape-cluster-analytics-runtime
TEST_TARGET = scenescape-cluster-analytics-test
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: build-demo
build-demo:
	$(MAKE) IMAGE="scenescape-cluster-analytics-demo" TARGET="scenescape-cluster-analytics-demo"

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)"
