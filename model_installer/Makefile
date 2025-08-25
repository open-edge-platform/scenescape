# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-model-installer
RUNTIME_OS_IMAGE := ubuntu:24.04

include ../common.mk

install-models: build-image
	@echo "==> Installing Open Model Zoo models..."
	@echo "Creating models volume if it doesn't exist..."
	@cd .. \
	; COMPOSE_PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-scenescape} \
	; docker volume create $${COMPOSE_PROJECT_NAME}_vol-models 2>/dev/null || true \
	; echo "Setting up volume permissions..." \
	; docker run --rm -v $${COMPOSE_PROJECT_NAME}_vol-models:/dest alpine:latest chown $(shell id -u):$(shell id -g) /dest \
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
	             /workspace/model_installer/src/install-omz-models $$MODELS --precisions $$PRECISIONS
	@echo "DONE ==> Installing Open Model Zoo models"
