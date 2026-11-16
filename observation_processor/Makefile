# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-observation-processor
TARGET := scenescape-observation-processor-runtime
USES_SCENE_COMMON := yes
PYTHON ?= python3

include ../common.mk

# Regenerate the committed gRPC stubs from the published contract.
.PHONY: proto
proto:
	PYTHON="$(PYTHON)" bash generate.sh
