# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-autocalibration
TEST_IMAGE := scenescape-autocalibration-test
RUNTIME_OS_IMAGE := python:3.11-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
TARGET = autocalibration-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="autocalibration-test"
