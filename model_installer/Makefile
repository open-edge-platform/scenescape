# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-model-installer
RUNTIME_OS_IMAGE := ubuntu:24.04

include ../common.mk

install-models: install-omz-models copy-config-files

create-models-volume:
	@echo "Checking if models volume exists..." \
	; COMPOSE_PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-scenescape} \
	; if docker volume inspect $${COMPOSE_PROJECT_NAME}_vol-models >/dev/null 2>&1; then \
		echo "Volume $${COMPOSE_PROJECT_NAME}_vol-models already exists."; \
		exit 0; \
	fi \
	; echo "Creating models volume..." \
	; cd .. \
	; docker volume create $${COMPOSE_PROJECT_NAME}_vol-models \
	; echo "Setting up volume permissions..." \
	; docker run --rm -v $${COMPOSE_PROJECT_NAME}_vol-models:/dest alpine:latest chown $(shell id -u):$(shell id -g) /dest

install-omz-models: create-models-volume build-image
	@echo "==> Installing Open Model Zoo models..."
	@cd .. \
	; COMPOSE_PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-scenescape} \
	; APPDIR=/workspace \
	; HOSTDIR=$$PWD \
	; IMAGE=$(IMAGE):latest \
	; MODELS=--$${MODELS:-default} \
	; PRECISIONS=$${PRECISIONS:-FP32} \
	; docker run --rm -v $$HOSTDIR:$$APPDIR:z \
	             -v $${COMPOSE_PROJECT_NAME}_vol-models:/opt/intel/openvino/deployment_tools/intel_models \
	             -e HTTP_PROXY=$$http_proxy \
	             -e HTTPS_PROXY=$$https_proxy \
	             -e http_proxy=$$http_proxy \
	             -e https_proxy=$$https_proxy \
	             -e MODEL_DIR=/opt/intel/openvino/deployment_tools/intel_models \
	             -u $$UID \
	             -l user=$$USER $$IMAGE \
	             /workspace/model_installer/src/install-omz-models $$MODELS --precisions $$PRECISIONS --model_proc
	@echo "DONE ==> Installing Open Model Zoo models"

copy-config-files: create-models-volume
	@echo "==> Copying config files..."
	@cd .. \
	; COMPOSE_PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-scenescape} \
	; APPDIR=/workspace \
	; HOSTDIR=$$PWD \
	; IMAGE=$(IMAGE):latest \
	; docker run --rm -v $$HOSTDIR:$$APPDIR:z \
	                  -v $${COMPOSE_PROJECT_NAME}_vol-models:/models python:3.12-slim \
					  /workspace/model_installer/src/copy-config-files /workspace /models
	@echo "DONE ==> Copying config files"
