# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.PHONY: build rebuild test clean help

# Variables
SERVICE_NAME := mqtt_client_bridge
IMAGE_NAME := $(SERVICE_NAME)
DOCKER_BUILDKIT := 1
BUILD_DIR ?= ../build

help:
	@echo "$(SERVICE_NAME) Makefile targets:"
	@echo "  build              Build Docker image"
	@echo "  rebuild            Clean and rebuild Docker image"
	@echo "  test               Run container (for testing)"
	@echo "  clean              Remove Docker image"
	@echo "  logs               Show container logs"

build:
	@echo "Building $(IMAGE_NAME)..."
	docker build --build-arg ROS_DISTRO=jazzy -t $(IMAGE_NAME):latest .
	@echo "Build complete: $(IMAGE_NAME):latest"

rebuild: clean build

clean:
	@echo "Cleaning up $(IMAGE_NAME)..."
	docker rmi -f $(IMAGE_NAME):latest 2>/dev/null || true

logs:
	docker logs -f $$(docker ps --filter "ancestor=$(IMAGE_NAME):latest" -q)

.PHONY: build
