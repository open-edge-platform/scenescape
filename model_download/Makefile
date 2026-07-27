# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

COMPOSE_PROJECT_NAME ?= scenescape
MODEL_VOLUME := $(COMPOSE_PROJECT_NAME)_vol-models

MODEL_DOWNLOADER_CONTAINER ?= $(COMPOSE_PROJECT_NAME)-model-download
MODEL_DOWNLOADER_IMAGE ?= intel/model-download:latest
MODEL_DOWNLOADER_HOST_PORT ?= 8200
MODEL_DOWNLOADER_CONTAINER_PORT ?= 8000
MODEL_DOWNLOADER_URL ?= http://127.0.0.1:$(MODEL_DOWNLOADER_HOST_PORT)
MODEL_DOWNLOADER_WAIT_TIMEOUT ?= 120

PARALLEL_DOWNLOADS ?= false
MODEL_CONFIG_OUTPUT_FILE ?= model_config.json
MODEL_CONFIG_PREFER_PRECISION ?= FP16
MODEL_CONFIG_SUBFOLDERS ?= omz,intel,public

# if models should be taken from other sources - add those sources here, e.g. --plugins omz,huggingface
# bear in mind that some sources may require additional configuration - check the model_downloader documentation for details
MODEL_DOWNLOADER_CMD ?= --plugins omz
MODEL_DOWNLOADER_RUN_ARGS ?=

MODEL_LIST ?= [{"name": "person-detection-retail-0013", "hub": "omz"},{"name": "person-vehicle-bike-detection-crossroad-1016", "hub": "omz"},{"name": "person-reidentification-retail-0277", "hub": "omz"},{"name": "age-gender-recognition-retail-0013", "hub": "omz"},{"name": "person-attributes-recognition-crossroad-0238", "hub": "omz"},{"name": "vehicle-attributes-recognition-barrier-0042", "hub": "omz"}]

.PHONY: install-models
install-models: create-models-volume start-model-downloader
	trap 'make stop-model-downloader' EXIT; \
	$(MAKE) download-models && \
	$(MAKE) generate-model-config && \
	$(MAKE) list-model-files && \
	$(MAKE) copy-config-files

.PHONY: create-models-volume
create-models-volume:
	@echo "Checking models volume $(MODEL_VOLUME)..."
	@if docker volume inspect "$(MODEL_VOLUME)" >/dev/null 2>&1; then \
		echo "Volume $(MODEL_VOLUME) already exists."; \
	else \
		echo "Creating volume $(MODEL_VOLUME)..."; \
		docker volume create "$(MODEL_VOLUME)" >/dev/null; \
	fi
	@echo "Setting volume permissions..."
	@docker run --rm -v "$(MODEL_VOLUME)":/dest alpine:3.23 chown -R $(shell id -u):$(shell id -g) /dest

.PHONY: start-model-downloader
start-model-downloader:
	@if [ "$$(docker inspect -f '{{.State.Running}}' "$(MODEL_DOWNLOADER_CONTAINER)" 2>/dev/null || true)" = "true" ]; then \
		echo "Container $(MODEL_DOWNLOADER_CONTAINER) is already running."; \
		exit 0; \
	fi
	@if docker container inspect "$(MODEL_DOWNLOADER_CONTAINER)" >/dev/null 2>&1; then \
		echo "Removing stale container $(MODEL_DOWNLOADER_CONTAINER)..."; \
		docker rm -f "$(MODEL_DOWNLOADER_CONTAINER)" >/dev/null; \
	fi
	@echo "Starting model_downloader container $(MODEL_DOWNLOADER_CONTAINER)..."
	@docker run -d \
		--name "$(MODEL_DOWNLOADER_CONTAINER)" \
		-p "$(MODEL_DOWNLOADER_HOST_PORT):$(MODEL_DOWNLOADER_CONTAINER_PORT)" \
		-v "$(MODEL_VOLUME)":/opt/models \
		-e HTTP_PROXY="$(HTTP_PROXY)" \
		-e HTTPS_PROXY="$(HTTPS_PROXY)" \
		-e NO_PROXY="$(NO_PROXY)" \
		-e http_proxy="$(http_proxy)" \
		-e https_proxy="$(https_proxy)" \
		-e no_proxy="$(no_proxy)" \
		$(MODEL_DOWNLOADER_RUN_ARGS) \
		"$(MODEL_DOWNLOADER_IMAGE)" $(MODEL_DOWNLOADER_CMD) >/dev/null

.PHONY: download-models
download-models:
	@echo "Requesting model download from $(MODEL_DOWNLOADER_URL)..."
	@MODEL_DOWNLOADER_URL="$(MODEL_DOWNLOADER_URL)" \
	MODEL_LIST='$(MODEL_LIST)' \
	PARALLEL_DOWNLOADS="$(PARALLEL_DOWNLOADS)" \
	MODEL_DOWNLOADER_WAIT_TIMEOUT="$(MODEL_DOWNLOADER_WAIT_TIMEOUT)" \
	python3 ./src/download_models.py

.PHONY: generate-model-config
generate-model-config:
	@echo "Generating model configuration file in $(MODEL_VOLUME)..."
	@docker run --rm \
		-v "$(MODEL_VOLUME)":/models \
		-v "$(abspath src)":/work/src \
		python:3.11-slim \
		python /work/src/generate_model_config.py \
			--models-path /models \
			--output-file "$(MODEL_CONFIG_OUTPUT_FILE)" \
			--prefer-precision "$(MODEL_CONFIG_PREFER_PRECISION)" \
			--subfolders "$(MODEL_CONFIG_SUBFOLDERS)"

.PHONY: list-model-files
list-model-files:
	@echo "Listing downloaded model files in $(MODEL_VOLUME)..."
	@docker run --rm -v "$(MODEL_VOLUME)":/models alpine:3.23 sh -c "find /models -type f | sort"

.PHONY: stop-model-downloader
stop-model-downloader:
	@docker rm -f "$(MODEL_DOWNLOADER_CONTAINER)" >/dev/null 2>&1 || true
	@echo "Stopped $(MODEL_DOWNLOADER_CONTAINER) if it existed."

copy-config-files:
	@echo "==> Copying config files..."
	@cd .. \
	; COMPOSE_PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-scenescape} \
	; APPDIR=/workspace \
	; HOSTDIR=$$PWD \
	; docker run --rm -v $$HOSTDIR:$$APPDIR:z \
	                  -v $${COMPOSE_PROJECT_NAME}_vol-models:/models \
					   python:3.12-slim \
					  python3 /workspace/model_download/src/copy-config-files /workspace /models
	@echo "DONE ==> Copying config files"
