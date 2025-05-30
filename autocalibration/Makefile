# Makefile for building the autocalibration component

IMAGE=scenescape-camcalibration
BASE_OS_IMAGE=ubuntu:22.04
VERSION:=$(shell cat ../version.txt)
BUILD_DIR=./build
LOG_FILE=$(BUILD_DIR)/$(IMAGE).log
SHELL := /bin/bash

default: build-image

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
	$(MAKE) REBUILDFLAGS="--no-cache"

.PHONY: list-deps
list-deps:
	@mkdir -p $(BUILD_DIR)
	@docker run --rm --entrypoint pip $(IMAGE):$(VERSION) freeze --all > $(BUILD_DIR)/$(IMAGE)-pip-deps.txt
	@echo "Python dependencies listed in $(BUILD_DIR)/$(IMAGE)-pip-deps.txt"
	@docker run --rm $(BASE_OS_IMAGE) dpkg -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/system-packages.txt
	@docker run --rm --entrypoint dpkg $(IMAGE):$(VERSION) -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/autocalibration-packages.txt
	@grep -Fxv -f $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/autocalibration-packages.txt > $(BUILD_DIR)/$(IMAGE)-apt-deps.txt
	@rm -rf $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/autocalibration-packages.txt
	@echo "OS dependencies listed in $(BUILD_DIR)/$(IMAGE)-apt-deps.txt"

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)
	docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest || true