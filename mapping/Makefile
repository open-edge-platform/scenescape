# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Model selection - can be overridden with MODEL_TYPE=vggt or MODEL_TYPE=mapanything
MODEL_TYPE ?= mapanything

IMAGE := intel/scenescape-mapping
TEST_IMAGE := intel/scenescape-mapping-test
TARGET = mapping-runtime
TEST_TARGET = mapping-test
USES_SCENE_COMMON := yes
ROOT_DIR := $(abspath ..)
VERSION := $(shell cat ../version.txt)

include ../common.mk

# Override docker build args to include MODEL_TYPE
EXTRA_BUILD_ARGS := --build-arg MODEL_TYPE=$(MODEL_TYPE)

# Model source is cloned on the host (not inside the Docker build) to avoid GitHub's
# unauthenticated-download rate limiting hitting container builds.
MAPANYTHING_REPO := https://github.com/facebookresearch/map-anything.git
MAPANYTHING_COMMIT := b84b28f
VGGT_REPO := https://github.com/facebookresearch/vggt.git
VGGT_COMMIT := 44b3afb

.PHONY: vendor-deps
vendor-deps:
	@mkdir -p .vendor
	@if [ "$(MODEL_TYPE)" = "mapanything" ]; then \
		if [ ! -d .vendor/model/.git ] || [ "$$(git -C .vendor/model rev-parse --short HEAD 2>/dev/null)" != "$(MAPANYTHING_COMMIT)" ]; then \
			rm -rf .vendor/model && \
			echo "==> Cloning map-anything@$(MAPANYTHING_COMMIT) (host)..." && \
			git clone -q $(MAPANYTHING_REPO) .vendor/model && \
			git -C .vendor/model reset -q --hard $(MAPANYTHING_COMMIT); \
		fi; \
	elif [ "$(MODEL_TYPE)" = "vggt" ]; then \
		if [ ! -d .vendor/model/.git ] || [ "$$(git -C .vendor/model rev-parse --short HEAD 2>/dev/null)" != "$(VGGT_COMMIT)" ]; then \
			rm -rf .vendor/model && \
			echo "==> Cloning vggt@$(VGGT_COMMIT) (host)..." && \
			git clone -q $(VGGT_REPO) .vendor/model && \
			git -C .vendor/model reset -q --hard $(VGGT_COMMIT); \
		fi; \
	else \
		echo "Invalid MODEL_TYPE: $(MODEL_TYPE). Must be 'mapanything' or 'vggt'" && exit 1; \
	fi

build-image: vendor-deps

.PHONY: clean-vendor
clean-vendor:
	rm -rf .vendor

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)" MODEL_TYPE=$(MODEL_TYPE)

.PHONY: build-vggt
build-vggt:
	$(MAKE) MODEL_TYPE=vggt IMAGE="intel/scenescape-mapping" VERSION=$(VERSION)-vggt

.PHONY: build-mapanything
build-mapanything:
	$(MAKE) MODEL_TYPE=mapanything IMAGE="intel/scenescape-mapping" VERSION=$(VERSION)-mapanything

.PHONY: build-all
build-all: build-vggt build-mapanything
	docker tag intel/scenescape-mapping:$(VERSION)-mapanything intel/scenescape-mapping:latest
	docker tag intel/scenescape-mapping:$(VERSION)-mapanything intel/scenescape-mapping:$(VERSION)

# Convenience targets
.PHONY: vggt mapanything
vggt: build-vggt
mapanything: build-mapanything

# Override list-dependencies to produce dep files for both MODEL_TYPE modes.
ifndef MAPPING_LIST_DEPS
.PHONY: list-dependencies
list-dependencies: build-vggt build-mapanything
	$(MAKE) MODEL_TYPE=vggt IMAGE=intel/scenescape-mapping VERSION=$(VERSION)-vggt MAPPING_LIST_DEPS=1 list-dependencies
	$(MAKE) MODEL_TYPE=mapanything IMAGE=intel/scenescape-mapping VERSION=$(VERSION)-mapanything MAPPING_LIST_DEPS=1 list-dependencies
endif

# Override generate-sbom to produce SBOMs for both MODEL_TYPE modes. Re-runs vendor-deps
# for each variant immediately before its own generate-sbom call (rather than relying on the
# build-vggt/build-mapanything prerequisites below): generate-sbom's buildx build reads
# .vendor/model straight off disk, and since both prerequisites run first, .vendor/model would
# otherwise still hold whichever variant was vendored last (mapanything) when the vggt
# generate-sbom call runs, silently SBOM-scanning the wrong source tree.
ifndef MAPPING_GENERATE_SBOM
.NOTPARALLEL: build-vggt build-mapanything
.PHONY: generate-sbom
generate-sbom: build-vggt build-mapanything
	$(MAKE) MODEL_TYPE=vggt vendor-deps
	$(MAKE) ROOT_DIR=$(ROOT_DIR) MODEL_TYPE=vggt IMAGE=intel/scenescape-mapping VERSION=$(VERSION)-vggt MAPPING_GENERATE_SBOM=1 generate-sbom
	$(MAKE) MODEL_TYPE=mapanything vendor-deps
	$(MAKE) ROOT_DIR=$(ROOT_DIR) MODEL_TYPE=mapanything IMAGE=intel/scenescape-mapping VERSION=$(VERSION)-mapanything MAPPING_GENERATE_SBOM=1 generate-sbom
endif
