# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

IMAGE := scenescape-model-installer
RUNTIME_OS_IMAGE := debian:12-slim

include ../common.mk

install-models: build-image
	@echo "==> Installing Open Model Zoo models..."
	@cd .. \
	; APPDIR=/workspace \
	; HOSTDIR=$$PWD \
	; IMAGE=$(IMAGE):latest \
	; MODELS=--$${MODELS:-default} \
	; PRECISIONS=$${PRECISIONS:-FP32} \
	; docker run --rm -v $$HOSTDIR:$$APPDIR:z \
	             -e HTTP_PROXY=$$http_proxy \
	             -e HTTPS_PROXY=$$https_proxy \
	             -e http_proxy=$$http_proxy \
	             -e https_proxy=$$https_proxy \
	             -e MODEL_DIR=/workspace/model_installer/models \
	             -u $$UID \
	             -l user=$$USER $$IMAGE \
	             /workspace/model_installer/src/install-omz-models $$MODELS --precisions $$PRECISIONS
	@echo "DONE ==> Installing Open Model Zoo models"
