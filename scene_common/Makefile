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

IMAGE=scenescape-common-base
VERSION:=$(shell cat ../version.txt)
BASE_OS_IMAGE=ubuntu:22.04
BUILD_DIR=build
LOG_FILE=$(BUILD_DIR)/$(IMAGE).log
SHELL:=/bin/bash

default: build-image

.PHONY: build-image
build-image: Dockerfile
	@echo "------- STARTING BUILD OF IMAGE: $(IMAGE):$(VERSION) -------"
	@mkdir -p $(BUILD_DIR)
	@-env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) \
	    --build-arg BASE_OS_IMAGE=$(BASE_OS_IMAGE) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	    --build-arg USER_ID=$$UID \
	    --rm -t $(IMAGE):$(VERSION) -f ./Dockerfile .. 2>&1 | tee $(LOG_FILE); \
	status=$${PIPESTATUS[0]}; \
	if [ $$status -eq 0 ]; then \
		docker tag $(IMAGE):$(VERSION) $(IMAGE):latest; \
		echo -e "\033[0;32m------- BUILD OF IMAGE $(IMAGE):$(VERSION) COMPLETED SUCCESSFULLY -------\033[0m"; \
		echo "Log file created at $(LOG_FILE)"; \
	else \
		echo -e "\033[0;31m------- BUILD OF IMAGE $(IMAGE):$(VERSION) FAILED. CHECK $(LOG_FILE) FOR DETAILS. -------\033[0m"; \
		exit 1; \
	fi

.PHONY: rebuild
rebuild:
	make build-image REBUILDFLAGS="--no-cache"

.PHONY: clean
clean:
	docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest || true
