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

IMAGE := scenescape-model-installer
RUNTIME_OS_IMAGE := openvino/ubuntu22_dev:2024.6.0

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
