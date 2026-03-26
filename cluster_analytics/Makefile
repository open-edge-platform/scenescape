# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-cluster-analytics
TARGET = scenescape-cluster-analytics-runtime
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-cluster-analytics-test" TARGET="scenescape-cluster-analytics-test"
