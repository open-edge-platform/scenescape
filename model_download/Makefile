# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

COMPOSE_PROJECT_NAME ?= scenescape
MODEL_VOLUME := $(COMPOSE_PROJECT_NAME)_vol-models

MODEL_DOWNLOADER_CONTAINER ?= $(COMPOSE_PROJECT_NAME)-model-download
MODEL_DOWNLOADER_IMAGE ?= intel/model-download:2026.2.0-ww32
MODEL_DOWNLOADER_HOST_PORT ?= 8200
MODEL_DOWNLOADER_CONTAINER_PORT ?= 8000
MODEL_DOWNLOADER_URL ?= http://127.0.0.1:$(MODEL_DOWNLOADER_HOST_PORT)
MODEL_DOWNLOADER_WAIT_TIMEOUT ?= 720
MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT ?= $(MODEL_DOWNLOADER_WAIT_TIMEOUT)

PARALLEL_DOWNLOADS ?= false
MODEL_CONFIG_FILE ?= models.json
MODEL_LIST ?=

# if models should be taken from other sources - add those sources here, e.g. --plugins omz,huggingface
# bear in mind that some sources may require additional configuration - check the model_downloader documentation for details
MODEL_DOWNLOADER_CMD ?= --plugins omz
MODEL_DOWNLOADER_RUN_ARGS ?=

.PHONY: install-models
install-models: create-models-volume start-model-downloader
	trap '$(MAKE) stop-model-downloader' EXIT; \
	$(MAKE) download-models && \
	$(MAKE) generate-model-config && \
	$(MAKE) list-model-files

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
        -e HF_HUB_ENABLE_HF_TRANSFER=1 \
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
	MODEL_CONFIG_FILE="$(abspath $(MODEL_CONFIG_FILE))" \
	MODEL_LIST='$(MODEL_LIST)' \
	PARALLEL_DOWNLOADS="$(PARALLEL_DOWNLOADS)" \
	MODEL_DOWNLOADER_WAIT_TIMEOUT="$(MODEL_DOWNLOADER_WAIT_TIMEOUT)" \
	MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT="$(MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT)" \
	python3 ./src/download_models.py

.PHONY: generate-model-config
generate-model-config:
	@echo "Generating model configuration file in $(MODEL_VOLUME)..."
	@docker run --rm \
		-v "$(MODEL_VOLUME)":/models \
		-v "$(abspath src)":/work/src \
		-v "$(abspath $(MODEL_CONFIG_FILE))":/work/models.json:ro \
		python:3.11-slim \
		python /work/src/generate_model_config.py \
			--models-path /models \
			--config-file /work/models.json

.PHONY: list-model-files
list-model-files:
	@echo "Listing downloaded model files in $(MODEL_VOLUME)..."
	@docker run --rm -v "$(MODEL_VOLUME)":/models alpine:3.23 sh -c "find /models -type f | sort"

.PHONY: stop-model-downloader
stop-model-downloader:
	@docker rm -f "$(MODEL_DOWNLOADER_CONTAINER)" >/dev/null 2>&1 || true
	@echo "Stopped $(MODEL_DOWNLOADER_CONTAINER) if it existed."
