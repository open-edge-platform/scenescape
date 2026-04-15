# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

IMAGE := scenescape-controller
RUNTIME_OS_IMAGE := registry1-docker-io.repo.cci.nokia.net/ubuntu:noble-20260113@sha256:cd1dba651b3080c3686ecf4e3c4220f026b521fb76978881737d24f200828b2b
TARGET = scenescape-controller-runtime

# PROJECT_RELATIVE_DIRS is needed for GIT_REVISION and GIT_REVISION_SHORT.
# Some projects might depend on some other directory outside of their "top folder".
# Set this before including common.mk, do not put these into quotes
PROJECT_RELATIVE_DIRS:=. ../scene_common

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-controller-test" TARGET="scenescape-controller-test"
