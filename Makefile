# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

COMMON_FOLDER := scene_common
SUB_FOLDERS := docker controller autocalibration manager percebro
SUPASS := supass
EXTRA_BUILD_FLAGS :=
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))
SHELL:=/bin/bash

ifneq (,$(filter DAILY TAG,$(BUILD_TYPE)))
  EXTRA_BUILD_FLAGS := rebuild
endif

ifneq (,$(filter rc beta-rc,$(TARGET_BRANCH)))
  EXTRA_BUILD_FLAGS := rebuild
endif

default: build

.PHONY: build
build: check-tag build-certificates build-images

.PHONY: check-tag
check-tag:
ifeq ($(BUILD_TYPE),TAG)
	@echo "Checking if tag matches version.txt..."
	@if grep --quiet "$(BRANCH_NAME)" version.txt; then \
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

.PHONY: run_tests
run_tests:
	@echo "Running tests..."
	$(MAKE) --trace -C  tests -j 1 SUPASS=$(SUPASS) || (echo "Tests failed" && exit 1)

.PHONY: run_performance_tests
run_performance_tests:
	@echo "Running performance tests..."
	$(MAKE) -C tests performance_tests -j 1 SUPASS=$(SUPASS) || (echo "Performance tests failed" && exit 1)

.PHONY: run_stability_tests
run_stability_tests:
ifeq ($(BUILD_TYPE),DAILY)
	@$(MAKE) -C tests system-stability SUPASS=$(SUPASS) HOURS=4
else
	@$(MAKE) -C tests system-stability SUPASS=$(SUPASS)
endif

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
