# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-cluster-analytics
RUNTIME_OS_IMAGE := ubuntu:24.04@sha256:353675e2a41babd526e2b837d7ec780c2a05bca0164f7ea5dbbd433d21d166fc
TARGET = scenescape-cluster-analytics-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-cluster-analytics-test" TARGET="scenescape-cluster-analytics-test"
