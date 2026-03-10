# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL := /bin/bash
VERSION := $(shell cat ../version.txt)
BUILD_DIR ?= $(PWD)/build
ROOT_DIR := $(PWD)
LOG_FILE := $(BUILD_DIR)/$(IMAGE).log
HAS_PIP ?= yes
HAS_DPKG ?= yes
USES_SCENE_COMMON ?= no
# Read the SHA-pinned image from the Dockerfile ARG default — single source of truth
RUNTIME_OS_IMAGE ?= $(shell sed -n 's/^ARG RUNTIME_OS_IMAGE=//p' Dockerfile)

default: build-image

$(BUILD_DIR):
	mkdir -p $@

# ANSI color codes
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

.PHONY: build-image
build-image: $(BUILD_DIR) Dockerfile
	@echo -e "$(GREEN)------- STARTING BUILD OF IMAGE: $(IMAGE):$(VERSION) -------$(RESET)"
	@{ \
	    set -e; \
	    set -o pipefail; \
	    TARGET_ARG=""; \
	    if [ -n "$(TARGET)" ]; then TARGET_ARG="--target $(TARGET)"; fi; \
	    if env BUILDKIT_PROGRESS=plain docker build $(REBUILDFLAGS) $$TARGET_ARG \
	        --build-arg http_proxy=$(http_proxy) \
	        --build-arg https_proxy=$(https_proxy) \
	        --build-arg no_proxy=$(no_proxy) \
	        --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	        --build-arg FORCE_VAAPI=$(FORCE_VAAPI) \
	        $(EXTRA_BUILD_ARGS) \
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
list-dependencies: $(BUILD_DIR)
	@if [[ -z $$(docker images | grep "^$(IMAGE)" | grep $(VERSION)) ]]; then \
	  echo "Error: the image $(IMAGE):$(VERSION) does not exist! Cannot generate dependency list."; \
	  echo "Please build the image first."; \
	  exit 1; \
	fi
	@if [[ "$(HAS_PIP)" == "yes" ]]; then \
	  docker run --rm --entrypoint pip $(IMAGE):$(VERSION) freeze --all > $(BUILD_DIR)/$(IMAGE)-pip-deps.txt; \
	  echo "Python dependencies listed in $(BUILD_DIR)/$(IMAGE)-pip-deps.txt"; \
	fi
	@if [[ "$(HAS_DPKG)" == "yes" ]]; then \
	  if [[ -z "$(RUNTIME_OS_IMAGE)" ]]; then \
	    echo "Error: RUNTIME_OS_IMAGE is not set for $(IMAGE). Ensure 'ARG RUNTIME_OS_IMAGE=<image>' is present in $(CURDIR)/Dockerfile."; \
	    exit 1; \
	  fi; \
	  docker run --rm $(RUNTIME_OS_IMAGE) dpkg -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/$(IMAGE)-system-packages.txt; \
	  docker run --rm --entrypoint dpkg $(IMAGE):$(VERSION) -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/$(IMAGE)-packages.txt; \
	  grep -Fxv -f $(BUILD_DIR)/$(IMAGE)-system-packages.txt $(BUILD_DIR)/$(IMAGE)-packages.txt > $(BUILD_DIR)/$(IMAGE)-apt-deps.txt || true; \
	  rm -rf $(BUILD_DIR)/$(IMAGE)-system-packages.txt $(BUILD_DIR)/$(IMAGE)-packages.txt; \
	  echo "OS dependencies listed in $(BUILD_DIR)/$(IMAGE)-apt-deps.txt"; \
	fi

.PHONY: check-buildkit
check-buildkit:
	@if ! docker buildx inspect 2>&1 | grep -q "Driver:.*docker-container"; then \
	  echo "Error: generate-sbom requires a BuildKit container builder (current builder uses an incompatible driver)."; \
	  echo "Create one with:"; \
	  echo "  docker buildx create --use --name=scenescape-buildkit-container --driver=docker-container \\"; \
	  echo "    --driver-opt=env.http_proxy=\$$http_proxy,env.https_proxy=\$$https_proxy,env.HTTP_PROXY=\$$HTTP_PROXY,env.HTTPS_PROXY=\$$HTTPS_PROXY,default-load=true"; \
	  exit 1; \
	fi

.PHONY: generate-sbom
generate-sbom: $(BUILD_DIR) check-buildkit
# if the Dockerfile is based on scene_common/Dockerfile, prepend it to get the full context as a work-around for docker buildx limitations
	@if [[ -z "$(RUNTIME_OS_IMAGE)" ]]; then \
	  echo "Error: RUNTIME_OS_IMAGE is not set for $(IMAGE). Ensure 'ARG RUNTIME_OS_IMAGE=<image>' is present in $(CURDIR)/Dockerfile."; \
	  exit 1; \
	fi
	@if [[ "$(USES_SCENE_COMMON)" == "yes" ]]; then \
	  echo "ARG RUNTIME_OS_IMAGE=${RUNTIME_OS_IMAGE}" > $(BUILD_DIR)/sbom-$(IMAGE).Dockerfile; \
	  cat $(ROOT_DIR)/scene_common/Dockerfile ./Dockerfile >> $(BUILD_DIR)/sbom-$(IMAGE).Dockerfile; \
	else \
	  cp ./Dockerfile $(BUILD_DIR)/sbom-$(IMAGE).Dockerfile; \
	fi
	@mkdir -p $(BUILD_DIR)/sboms
	docker buildx build \
	--sbom=true \
	--build-arg http_proxy=$(http_proxy) \
	--build-arg https_proxy=$(https_proxy) \
	--build-arg no_proxy=$(no_proxy) \
	--build-arg BUILDKIT_SBOM_SCAN_STAGE=$(TARGET) \
	--build-arg RUNTIME_OS_IMAGE=$(RUNTIME_OS_IMAGE) \
	--target $(TARGET) \
	-f $(BUILD_DIR)/sbom-$(IMAGE).Dockerfile \
	$(ROOT_DIR) \
	-o type=tar,dest=$(BUILD_DIR)/sboms/$(IMAGE).tar
	@cd $(BUILD_DIR)/sboms && \
	tar -xf $(IMAGE).tar sbom.spdx.json && \
	mv sbom.spdx.json $(IMAGE)-sbom.spdx.json && \
	rm $(IMAGE).tar $(BUILD_DIR)/sbom-$(IMAGE).Dockerfile
	@echo "SBOM generated at $(BUILD_DIR)/sboms/"

.PHONY: clean
clean:
	@docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest || true
	@rm -f $(BUILD_DIR)/$(IMAGE)-*deps.txt $(LOG_FILE) || true
