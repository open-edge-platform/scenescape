# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

SHELL := /bin/bash
VERSION:=$(shell cat ../version.txt)
BUILD_DIR ?= $(PWD)/build
LOG_FILE := $(BUILD_DIR)/$(IMAGE).log

$(shell mkdir -p $(BUILD_DIR))

# ANSI color codes
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

.PHONY: build-image
build-image: Dockerfile
	@echo -e "$(GREEN)------- STARTING BUILD OF IMAGE: $(IMAGE):$(VERSION) -------$(RESET)"
	@{ \
	    set -e; \
	    set -o pipefail; \
	    if env BUILDKIT_PROGRESS=plain docker build $(REBUILDFLAGS) \
	        --build-arg RUNTIME_OS_IMAGE=$(RUNTIME_OS_IMAGE) \
	        --build-arg http_proxy=$(http_proxy) \
	        --build-arg https_proxy=$(https_proxy) \
	        --build-arg no_proxy=$(no_proxy) \
	        --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	        --build-arg USER_ID=$$UID \
	        --build-arg FORCE_VAAPI=$(FORCE_VAAPI) \
	        --rm -t $(IMAGE):$(VERSION) \
	        -f ./Dockerfile .. 2>&1 | tee $(LOG_FILE); \
	    then \
	        docker tag $(IMAGE):$(VERSION) $(IMAGE):latest; \
	        echo -e "$(GREEN)------- BUILD OF IMAGE $(IMAGE):$(VERSION) COMPLETED SUCCESSFULLY -------$(RESET)"; \
	        echo "Log file created at $(LOG_FILE)"; \
	    else \
	        echo -e "$(RED)------- BUILD OF IMAGE $(IMAGE):$(VERSION) FAILED. CHECK $(LOG_FILE) FOR DETAILS. -------$(RESET)"; \
	        grep --color=auto -i -r "^error" $(LOG_FILE); \
	        exit 1; \
	    fi \
	}

.PHONY: rebuild
rebuild:
	$(MAKE) REBUILDFLAGS="--no-cache"

.PHONY: list-dependencies
list-dependencies:
	@if [[ -z $$(docker images | grep "^$(IMAGE)" | grep $(VERSION)) ]]; then \
	  echo "Error: the image $(IMAGE):$(VERSION) does not exist! Cannot generate dependency list."; \
	  echo "Please build the image first."; \
	  exit 1; \
	fi
	@docker run --rm --entrypoint pip $(IMAGE):$(VERSION) freeze --all > $(BUILD_DIR)/$(IMAGE)-pip-deps.txt
	@echo "Python dependencies listed in $(BUILD_DIR)/$(IMAGE)-pip-deps.txt"
	@docker run --rm $(RUNTIME_OS_IMAGE) dpkg -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/system-packages.txt
	@docker run --rm --entrypoint dpkg $(IMAGE):$(VERSION) -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/$(IMAGE)-packages.txt
	@grep -Fxv -f $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/$(IMAGE)-packages.txt > $(BUILD_DIR)/$(IMAGE)-apt-deps.txt
	@rm -rf $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/$(IMAGE)-packages.txt
	@echo "OS dependencies listed in $(BUILD_DIR)/$(IMAGE)-apt-deps.txt"

.PHONY: clean
clean:
	docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest || true
