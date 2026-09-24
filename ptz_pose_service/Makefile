# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-ptz-pose-service
TARGET = ptz-pose-service-runtime
USES_SCENE_COMMON := yes

include ../common.mk

# dlstreamer.onvif (pure-python ONVIF discovery/PTZ library) is cloned on the host
# (not inside the Docker build) to avoid GitHub's unauthenticated-download rate
# limiting hitting container builds. Pin to the commit this service was validated
# against; bump deliberately.
DLSTREAMER_REPO := https://github.com/open-edge-platform/dlstreamer.git
DLSTREAMER_COMMIT := b9ba103e

.PHONY: vendor-deps
vendor-deps:
	@mkdir -p .vendor
	@if [ ! -d .vendor/dlstreamer/.git ] || [ "$$(git -C .vendor/dlstreamer rev-parse --short HEAD 2>/dev/null)" != "$(DLSTREAMER_COMMIT)" ]; then \
		rm -rf .vendor/dlstreamer && \
		echo "==> Cloning dlstreamer@$(DLSTREAMER_COMMIT) (host)..." && \
		git clone -q $(DLSTREAMER_REPO) .vendor/dlstreamer && \
		git -C .vendor/dlstreamer reset -q --hard $(DLSTREAMER_COMMIT); \
	fi

build-image: vendor-deps

.PHONY: clean-vendor
clean-vendor:
	rm -rf .vendor
