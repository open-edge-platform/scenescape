# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-mapping
RUNTIME_OS_IMAGE := python:3.11-slim-bookworm
TARGET = mapping-runtime

# Model selection - can be overridden with MODEL_TYPE=vggt or MODEL_TYPE=mapanything
MODEL_TYPE ?= mapanything

include ../common.mk

# Override docker build args to include MODEL_TYPE
EXTRA_BUILD_ARGS := --build-arg MODEL_TYPE=$(MODEL_TYPE)

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-mapping-test" TARGET="mapping-test" MODEL_TYPE=$(MODEL_TYPE)

.PHONY: build-vggt
build-vggt:
	$(MAKE) MODEL_TYPE=vggt IMAGE="scenescape-mapping-vggt"

.PHONY: build-mapanything
build-mapanything:
	$(MAKE) MODEL_TYPE=mapanything IMAGE="scenescape-mapping-mapanything"

.PHONY: build-all
build-all: build-vggt build-mapanything

# Convenience targets
.PHONY: vggt mapanything
vggt: build-vggt
mapanything: build-mapanything
