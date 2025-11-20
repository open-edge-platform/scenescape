# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-cluster-analytics
RUNTIME_OS_IMAGE := python:3.12-slim
TARGET = scenescape-cluster-analytics-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-cluster-analytics-test" TARGET="scenescape-cluster-analytics-test"
