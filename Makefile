# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

COMMON_FOLDER := scene_common
SUB_FOLDERS := docker controller autocalibration manager percebro
EXTRA_BUILD_FLAGS :=
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))
SHELL:=/bin/bash

ifeq ($(or $(findstring DAILY,$(BUILD_TYPE)),$(findstring TAG,$(BUILD_TYPE))),true)
	EXTRA_BUILD_FLAGS := rebuild
endif
ifeq ($(or $(TARGET_BRANCH)),rc beta-rc)
	EXTRA_BUILD_FLAGS := rebuild
endif

default: build

.PHONY: build
build: check-tag build-certificates build-images

.PHONY: check-tag
check-tag:
ifeq ($(BUILD_TYPE),TAG)
	@echo "Checking if tag matches version.txt..."
	@if grep --quiet $(BRANCH_NAME) version.txt; then \
		echo "Perfect - Tag and Version is matching"; \
	else \
		echo "There is some mismatch between Tag and Version"; \
		exit 1; \
	fi
endif

.PHONY: build-certificates
build-certificates:
	@make -C certificates CERTPASS=$$(openssl rand -base64 12)

# Build common base image
.PHONY: build-common
build-common:
	@$(MAKE) -C $(COMMON_FOLDER) http_proxy=$(http_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE"

# Build docker images for all microservices
.PHONY: build-images
build-images: build-common
	@echo "Building docker images in parallel..."
	@trap 'echo "Interrupted! Exiting..."; exit 1' INT; \
	for dir in $(SUB_FOLDERS); do \
		$(MAKE) http_proxy=$(http_proxy) -C $$dir $(EXTRA_BUILD_FLAGS) & \
	done; wait
	@$(MAKE) -C docker ../docker-compose.yml
	@echo "DONE"

.PHONY: list-dependencies
list-dependencies:
	@echo "Listing dependencies for all microservices..."
	for dir in $(SUB_FOLDERS); do \
		$(MAKE) -C $$dir list-deps; \
	done
#TODO: generate a summary files with all dependencies
	@echo "DONE"

.PHONY: clean
clean:
	@echo "Cleaning up all microservices..."
	for dir in $(SUB_FOLDERS); do \
		$(MAKE) -C $$dir clean; \
	done
	@echo "Cleaning common folder..."
	@$(MAKE) -C $(COMMON_FOLDER) clean
	@echo "DONE"
	@echo "Cleaning certificates..."
	@make -C certificates clean
	@echo "DONE"

.PHONY: rebuild
rebuild: clean build
