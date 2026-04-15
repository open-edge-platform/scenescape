# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

# DLStreamer Pipeline Server with Triton client support.
# This Makefile builds an optional Triton-enabled DLStreamer image.
# The stock Intel DLStreamer image does not require building.

IMAGE = scenescape-dlstreamer-triton
DOCKERFILE = Dockerfile.triton
HAS_PIP ?= yes
HAS_DPKG ?= yes

SHELL := /bin/bash
VERSION := $(shell cat ../version.txt)
BUILD_DIR ?= $(PWD)/build
LOG_FILE := $(BUILD_DIR)/$(IMAGE).log

# ANSI color codes
RED    := \033[0;31m
GREEN  := \033[0;32m
RESET  := \033[0m

default: build-image

$(BUILD_DIR):
	mkdir -p $@

.PHONY: build-image
build-image: $(BUILD_DIR) $(DOCKERFILE)
	@echo -e "$(GREEN)------- STARTING BUILD OF IMAGE: $(IMAGE):$(VERSION) -------$(RESET)"
	@{ \
	    set -e; \
	    set -o pipefail; \
	    if env BUILDKIT_PROGRESS=plain docker build $(REBUILDFLAGS) \
	        --build-arg http_proxy=$(http_proxy) \
	        --build-arg https_proxy=$(https_proxy) \
	        --build-arg no_proxy=$(no_proxy) \
	        $(EXTRA_BUILD_ARGS) \
	        --rm -t $(IMAGE):$(VERSION) \
	        -f ./$(DOCKERFILE) .. 2>&1 | tee $(LOG_FILE); \
	    then \
	        docker tag $(IMAGE):$(VERSION) $(IMAGE):latest; \
	        echo -e "$(GREEN)------- BUILD OF IMAGE $(IMAGE):$(VERSION) COMPLETED SUCCESSFULLY -------$(RESET)"; \
	    else \
	        echo -e "$(RED)------- BUILD OF IMAGE $(IMAGE):$(VERSION) FAILED. CHECK $(LOG_FILE) FOR DETAILS. -------$(RESET)"; \
	        grep --color=auto -i -r "^error" $(LOG_FILE); \
	        exit 1; \
	    fi \
	}

.PHONY: rebuild
rebuild:
	$(MAKE) REBUILDFLAGS="--no-cache"

.PHONY: clean
clean:
	@docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest || true
	@rm -f $(LOG_FILE) || true
