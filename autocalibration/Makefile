# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-autocalibration
TEST_IMAGE := intel/scenescape-autocalibration-test
TARGET = autocalibration-runtime
TEST_TARGET = autocalibration-test
USES_SCENE_COMMON := yes

include ../common.mk

# Third-party sources are cloned on the host (not inside the Docker build) to avoid
# GitHub's unauthenticated-download rate limiting hitting container builds.
RELOC_REPO := https://github.com/cvg/Hierarchical-Localization.git
RELOC_COMMIT := c13273b
APRILTAG_REPO := https://github.com/duckietown/lib-dt-apriltags.git

.PHONY: vendor-deps
vendor-deps:
	@mkdir -p .vendor
	@if [ ! -d .vendor/reloc/.git ] || [ "$$(git -C .vendor/reloc rev-parse --short HEAD 2>/dev/null)" != "$(RELOC_COMMIT)" ]; then \
		rm -rf .vendor/reloc && \
		echo "==> Cloning Hierarchical-Localization@$(RELOC_COMMIT) (host)..." && \
		git clone -q $(RELOC_REPO) .vendor/reloc && \
		git -C .vendor/reloc reset -q --hard $(RELOC_COMMIT); \
	fi
	@if [ ! -d .vendor/apriltag-dev/.git ]; then \
		echo "==> Cloning lib-dt-apriltags (host)..."; \
		git clone --depth=1 $(APRILTAG_REPO) .vendor/apriltag-dev; \
	fi
	@cd .vendor/apriltag-dev && git submodule update --init

build-image: vendor-deps

.PHONY: clean-vendor
clean-vendor:
	rm -rf .vendor

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)"
