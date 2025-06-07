# Copyright (C) 2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

COMMON_FOLDER := scene_common
IMAGE_FOLDERS := docker controller autocalibration manager percebro
EXTRA_BUILD_FLAGS :=
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))
SHELL := /bin/bash

# User can adjust number of parallel jobs (defaults to CPU count)
JOBS ?= $(shell nproc)
# User can adjust folders being built (defaults to all)
FOLDERS ?= $(IMAGE_FOLDERS)
# User can adjust build output folder (defaults to ./build)
BUILD_DIR ?= $(PWD)/build

ifneq (,$(filter DAILY TAG,$(BUILD_TYPE)))
  EXTRA_BUILD_FLAGS := rebuild
endif

ifneq (,$(filter rc beta-rc,$(TARGET_BRANCH)))
  EXTRA_BUILD_FLAGS := rebuild
endif

default: build

.PHONY: build
build: check-tag build-certificates build-images-parallel

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

.PHONY: $(IMAGE_FOLDERS)
$(IMAGE_FOLDERS):
	@echo "====> Building folder $@..."
	@$(MAKE) -C $@ http_proxy=$(http_proxy) https_proxy=$(https_proxy) no_proxy=$(no_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE ====> Building folder $@"

# Parallel wrapper handles parallel builds of folders specified in FOLDERS variable
.PHONY: build-images-parallel
build-images-parallel: build-common
	@echo "==> Running parallel builds of folders: $(FOLDERS)"
# Use a trap to catch errors and print logs if any error occurs in parallel build
	@set -e; trap 'grep --color=auto -i -r --include="*.log" "^error" $(BUILD_DIR) || true' EXIT; \
	$(MAKE) -j$(JOBS) $(FOLDERS)
	@echo "DONE ==> Parallel builds of folders: $(FOLDERS)"

.PHONY: demo
demo:
	@if [ -z "$$SUPASS" ] && { [ ! -d "./db" ] || [ -z "$$(ls -A ./db)" ]; }; then \
	    echo "Please set the SUPASS environment variable before starting the demo for the first time."; \
	    echo "The SUPASS environment variable is the super user password for logging into Intel® SceneScape."; \
	    exit 1; \
	fi
	@$(MAKE) -C docker ../docker-compose.yml
	docker compose up -d
	@echo ""
	@echo "To stop SceneScape, type:"
	@echo "    docker compose down"

.PHONY: list-dependencies
list-dependencies:
	@echo "Listing dependencies for all microservices..."
	@set -e; \
	for dir in $(IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir list-dependencies; \
	done
	@-find . -type f -name '*-apt-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-apt-deps.txt
	@-find . -type f -name '*-pip-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-pip-deps.txt
	@echo "The following dependency lists have been generated:"
	@find $(BUILD_DIR) -name '*-deps.txt' -print
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
	for dir in $(FOLDERS); do \
		$(MAKE) -C $$dir clean; \
	done
	@echo "Cleaning common folder..."
	@$(MAKE) -C $(COMMON_FOLDER) clean
	@echo "Cleaning certificates..."
	@make -C certificates clean
	@-rm -rf $(BUILD_DIR)
	@echo "DONE"

.PHONY: rebuild
rebuild: clean build
