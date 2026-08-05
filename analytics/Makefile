# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-analytics
TARGET = scenescape-analytics-runtime
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="intel/scenescape-analytics-test" TARGET="scenescape-analytics-test"
