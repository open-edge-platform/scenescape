# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-controller
RUNTIME_OS_IMAGE := python:3.11-slim-bookworm
TARGET = scenescape-controller-runtime
USES_SCENE_COMMON := yes

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-controller-test" TARGET="scenescape-controller-test"
