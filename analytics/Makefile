# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-analytics
TARGET = scenescape-analytics-runtime
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-analytics-test" TARGET="scenescape-analytics-test"
