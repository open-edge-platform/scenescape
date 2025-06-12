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

# ================ Makefile for Intel® SceneScape ====================

# =========================== Variables ==============================
SHELL := /bin/bash

# Build folders
COMMON_FOLDER := scene_common
IMAGE_FOLDERS := autocalibration broker controller manager model_installer percebro

# Build flas
EXTRA_BUILD_FLAGS :=
REBUILDFLAGS :=

# Image variables
IMAGE_PREFIX := scenescape
SOURCES_IMAGE := $(IMAGE_PREFIX)-sources
VERSION := $(shell cat ./version.txt)

# Secrets building variables
# * Ensure SECRETSDIR is absolute, so that it works correctly in recursive make calls
SECRETSDIR := $(PWD)/secrets
MQTTUSERS := "percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES := $(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))
CERTDOMAIN := scenescape.intel.com

# User configurable variables
# - User can adjust build output folder (defaults to $PWD/build)
BUILD_DIR ?= $(PWD)/build
# - User can adjust folders being built (defaults to all)
FOLDERS ?= $(IMAGE_FOLDERS)
# - User can adjust number of parallel jobs (defaults to CPU count)
JOBS ?= $(shell nproc)
# - User can adjust the target branch
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))

# Ensure BUILD_DIR is absolute, so that it works correctly in recursive make calls
ifeq ($(filter /%,$(BUILD_DIR)),)
BUILD_DIR := $(PWD)/$(BUILD_DIR)
endif

# ========================= Default Target ===========================

default: build-all

.PHONY: build-all
build-all: build-secrets build-images install-models

# ========================== CI specific =============================

ifneq (,$(filter DAILY TAG,$(BUILD_TYPE)))
  EXTRA_BUILD_FLAGS := rebuild
endif

ifneq (,$(filter rc beta-rc,$(TARGET_BRANCH)))
  EXTRA_BUILD_FLAGS := rebuild
endif

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

# ========================= Build Images =============================

$(BUILD_DIR):
	mkdir -p $@

# Build common base image
.PHONY: build-common
build-common:
	@echo "==> Building common base image..."
	@$(MAKE) -C $(COMMON_FOLDER) http_proxy=$(http_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE ==> Building common base image"

# Build targets for each service folder
.PHONY: $(IMAGE_FOLDERS)
$(IMAGE_FOLDERS):
	@echo "====> Building folder $@..."
	@$(MAKE) -C $@ http_proxy=$(http_proxy) https_proxy=$(https_proxy) no_proxy=$(no_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE ====> Building folder $@"

# Dependency on the common base image
autocalibration controller manager percebro: build-common

# Parallel wrapper handles parallel builds of folders specified in FOLDERS variable
.PHONY: build-images
build-images: $(BUILD_DIR)
	@echo "==> Running parallel builds of folders: $(FOLDERS)"
# Use a trap to catch errors and print logs if any error occurs in parallel build
	@set -e; trap 'grep --color=auto -i -r --include="*.log" "^error" $(BUILD_DIR) || true' EXIT; \
	$(MAKE) -j$(JOBS) $(FOLDERS)
	@echo "DONE ==> Parallel builds of folders: $(FOLDERS)"

# ===================== Cleaning and Rebuilding =======================

.PHONY: rebuild
rebuild: clean build-images

.PHONY: rebuild-all
rebuild-all: clean-all build-all

.PHONY: clean
clean:
	@echo "==> Cleaning up all build artifacts..."
	@for dir in $(FOLDERS); do \
		$(MAKE) -C $$dir clean; \
	done
	@echo "Cleaning common folder..."
	@$(MAKE) -C $(COMMON_FOLDER) clean
	@-rm -rf $(BUILD_DIR)
	@echo "DONE ==> Cleaning up all build artifacts"

.PHONY: clean-all
clean-all: clean clean-secrets clean-volumes
	@echo "==> Cleaning all..."
	@-rm -f docker-compose.yml
	@echo "DONE ==> Cleaning all"

.PHONY: clean-volumes
clean-volumes:
	@echo "Cleaning up all volumes..."
	@docker volume rm -f \
		scenescape_vol-datasets \
		scenescape_vol-db \
		scenescape_vol-media \
		scenescape_vol-migrations \
		scenescape_vol-dlstreamer-pipeline-server-pipeline-root || true
	@echo "DONE ==> Cleaning up all volumes"

# ===================== 3rd Party Dependencies =======================
.PHONY: list-dependencies
list-dependencies: $(BUILD_DIR)
	@echo "==> Listing dependencies for all microservices..."
	@set -e; \
	for dir in $(IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir list-dependencies; \
	done
	@-find . -type f -name '*-apt-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-apt-deps.txt
	@-find . -type f -name '*-pip-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-pip-deps.txt
	@echo "The following dependency lists have been generated:"
	@find $(BUILD_DIR) -name '*-deps.txt' -print
	@echo "DONE ==> Listing dependencies for all microservices"

.PHONY: build-sources-image
build-sources-image: Dockerfile-sources
	@echo "==> Building the image with 3rd party sources..."
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(SOURCES_IMAGE):$(VERSION) . \
	&& docker tag $(SOURCES_IMAGE):$(VERSION) $(SOURCES_IMAGE):latest
	@echo "DONE ==> Building the image with 3rd party sources"

# ======================= Model Installer ============================

.PHONY: install-models
install-models:
	@$(MAKE) -C model_installer install-models

# =========================== Run Tests ==============================

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

# ===================== Docker Compose Demo ==========================

.PHONY: demo
demo: docker-compose.yml
	@if [ -z "$$SUPASS" ]; then \
	    echo "Please set the SUPASS environment variable before starting the demo for the first time."; \
	    echo "The SUPASS environment variable is the super user password for logging into Intel® SceneScape."; \
	    exit 1; \
	fi
	docker compose up -d
	@echo ""
	@echo "To stop SceneScape, type:"
	@echo "    docker compose down"

docker-compose.yml: ./sample_data/docker-compose-example.yml
	@sed -e "s/image: $(IMAGE_PREFIX)\(-.*\)\?/image: $(IMAGE_PREFIX)\1:$(VERSION)/" $< > $@

# ======================= Secrets Management =========================

.PHONY: build-secrets
build-secrets: certificates authfiles
	chmod go-rwx $(SECRETSDIR)

.PHONY: certificates
certificates:
	@make -C ./tools/certificates CERTPASS=$$(openssl rand -base64 12)

%.auth:
	@set -e; \
	MQTTUSERS=$(MQTTUSERS); \
	for uid in $${MQTTUSERS}; do \
	    JSONFILE=$${uid%=*}; \
	    USERPASS=$${uid##*=}; \
	    case $${USERPASS} in \
	        *:* ) ;; \
	        * ) USERPASS=$${USERPASS}:$$(openssl rand -base64 12); \
	    esac; \
	    USER=$${USERPASS%:*}; \
	    PASS=$${USERPASS##*:}; \
	    if [ $(SECRETSDIR)/$${JSONFILE} = $@ ]; then \
	        echo '{"user": "'$${USER}'", "password": "'$${PASS}'"}' > $@; \
	        chmod 0600 $@; \
	    fi; \
	done

authfiles: $(AUTHFILES)

.PHONY: clean-secrets
clean-secrets:
	@echo "==> Cleaning secrets..."
	@-rm -rf $(SECRETSDIR)
	@echo "DONE ==> Cleaning secrets"
