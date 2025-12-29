# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

BUILD_DIR ?= build
NAME ?= tracker

.PHONY: all build clean run docker-build docker-run

all: build

build:
	cmake -S . -B $(BUILD_DIR)
	cmake --build $(BUILD_DIR)

run: build
	./$(BUILD_DIR)/$(NAME)

clean:
	rm -rf $(BUILD_DIR)

docker-build:
	docker build -f Dockerfile -t $(NAME) ..

docker-run: docker-build
	docker run --rm $(NAME)