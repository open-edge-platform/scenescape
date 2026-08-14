# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE=intel/scenescape-common-base

# No ARG RUNTIME_OS_IMAGE in the Dockerfile, so parse it straight from the FROM line for list-dependencies to work properly.
RUNTIME_OS_IMAGE := $(shell awk '/^FROM /{print $$2; exit}' Dockerfile)

include ../common.mk
