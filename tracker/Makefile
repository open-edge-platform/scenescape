# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Integration with common.mk for Docker image builds
IMAGE := scenescape-tracker
RUNTIME_OS_IMAGE := gcr.io/distroless/cc-debian13@sha256:d93602c2e8facf19435442a3fd19306e77505ca722aad08e7de659f6df43e147
TARGET ?= runtime
HAS_PIP := no

include ../common.mk

# Local build configuration
NAME ?= tracker

# Source files for formatting (will be populated as we add more sources)
SRC_FILES := $(wildcard src/*.cpp) $(wildcard inc/*.hpp) $(wildcard test/unit/*.cpp)

.PHONY: all dependencies-release dependencies-debug dependencies-profile \
        build-release build-debug build-profile run-release run-debug \
        test-unit test-service clean-local clean-all install-tools install-deps \
        run-image

all: build-release

#####################################################################
# System setup (run once)
#####################################################################

install-tools:
	@echo "Installing development tools via pipx..."
	@command -v pipx >/dev/null || (echo "pipx not found. Run: sudo apt install pipx" && exit 1)
	pipx install conan
	pipx install cmake
	pipx install ninja
	@echo "✓ Tools installed. Run 'pipx ensurepath' if needed"

install-deps:
	@echo "Installing system dependencies..."
	sudo apt-get update
	sudo apt-get install -y --no-install-recommends \
		build-essential \
		pkg-config \
		libopencv-dev \
		libeigen3-dev \
		libopenblas-dev
	@echo "✓ System dependencies installed"

#####################################################################
# Conan dependency installation
#####################################################################

dependencies-release:
	@echo "Installing release dependencies..."
	conan install . \
		--output-folder=build-release \
		--build=missing \
		-s build_type=Release \
		-c tools.cmake.cmaketoolchain:generator=Ninja

dependencies-debug:
	@echo "Installing debug dependencies..."
	conan install . \
		--output-folder=build-debug \
		--build=missing \
		-s build_type=Debug \
		-c tools.cmake.cmaketoolchain:generator=Ninja

dependencies-profile:
	@echo "Installing profile dependencies..."
	conan install . \
		--output-folder=build-profile \
		--build=missing \
		-s build_type=RelWithDebInfo \
		-c tools.cmake.cmaketoolchain:generator=Ninja

#####################################################################
# CMake build targets
#####################################################################

build-release: dependencies-release
	@echo "Building release..."
	cmake --preset conan-release -G Ninja -DBUILD_TESTS=OFF
	cmake --build build-release -j

build-debug: dependencies-debug
	@echo "Building debug..."
	cmake --preset conan-debug -G Ninja -DBUILD_TESTS=ON
	cmake --build build-debug -j

build-profile: dependencies-profile
	@echo "Building profile..."
	cmake --preset conan-relwithdebinfo -G Ninja -DBUILD_TESTS=OFF
	cmake --build build-profile -j

#####################################################################
# Run targets
#####################################################################

run-release: build-release
	./build-release/$(NAME)

run-debug: build-debug
	./build-debug/$(NAME)

#####################################################################
# Test targets
#####################################################################

test-unit: build-debug
	@echo "Running unit tests..."
	cd build-debug && ctest --output-on-failure

test-service:
	@echo "Running service tests..."
	cd test/service && pytest -v --tb=short

#####################################################################
# Docker build targets (via common.mk)
#####################################################################

build-image-debug:
	$(MAKE) build-image TARGET=debug IMAGE=scenescape-tracker-debug

run-image:
	docker run --rm -it $(IMAGE):$(VERSION)

#####################################################################
# Clean targets
#####################################################################

clean-all: clean clean-local

clean-local:
	rm -rf build-release build-debug build-profile