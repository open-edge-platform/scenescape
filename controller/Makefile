# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-controller
RUNTIME_OS_IMAGE := ubuntu:24.04@sha256:a08e551cb33850e4740772b38217fc1796a66da2506d312abe51acda354ff061
TARGET = scenescape-controller-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-controller-test" TARGET="scenescape-controller-test"
