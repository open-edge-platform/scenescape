# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Integration with common.mk for Docker image builds
IMAGE := scenescape-tracker
RUNTIME_OS_IMAGE := gcr.io/distroless/cc-debian13@sha256:d93602c2e8facf19435442a3fd19306e77505ca722aad08e7de659f6df43e147
TARGET ?= runtime
BUILD_TYPE ?= Release
HAS_PIP := no
EXTRA_BUILD_ARGS := --build-arg GIT_COMMIT=$(shell git rev-parse --short HEAD) --build-arg BUILD_TYPE=$(BUILD_TYPE)

include ../common.mk

# Local build configuration
NAME ?= tracker
GIT_COMMIT ?= $(shell git rev-parse --short HEAD)

# Source files for formatting
SRC_FILES := $(wildcard src/*.cpp) $(wildcard inc/*.hpp) $(wildcard test/unit/*.cpp)

.PHONY: all dependencies-release dependencies-debug dependencies-profile \
        build-release build-debug build-profile run-release run-debug \
        test-unit test-unit-coverage test-service clean install-tools install-deps \
        run-image run-image-debug format-cpp lint-cpp format-python lint-python install-hooks \
        lint-dockerfile lint-trivy lint-all coverage-html coverage-xml coverage-report

all: build-release

#####################################################################
# System setup (run once)
#####################################################################

install-tools:
	@echo "Installing development tools via pipx..."
	@command -v pipx >/dev/null || (echo "pipx not found. Run: sudo make install-deps" && exit 1)
	pipx install conan
	pipx install cmake
	pipx install ninja
	@echo "✓ Tools installed. Run 'pipx ensurepath' if needed"

install-deps:
	@echo "Installing system dependencies..."
	apt-get update
	apt-get install -y --no-install-recommends \
		build-essential \
		pkg-config \
		libopencv-dev \
		libeigen3-dev \
		libopenblas-dev \
		clang-format \
		pipx
	@echo "✓ System dependencies installed"

#####################################################################
# Code formatting
#####################################################################

format-cpp:
	@echo "Formatting source files..."
	@if [ -n "$(SRC_FILES)" ]; then \
		clang-format -i $(SRC_FILES); \
		echo "✓ Formatted $$(echo $(SRC_FILES) | wc -w) files"; \
	else \
		echo "No source files to format"; \
	fi

format-python:
	@echo "Formatting Python files..."
	@if ! command -v autopep8 >/dev/null 2>&1; then \
		echo "autopep8 not found. Install: pip install autopep8"; \
		exit 1; \
	fi
	@cd test/service && autopep8 --in-place --indent-size=2 --max-line-length=120 *.py
	@echo "✓ Python files formatted"

install-hooks:
	@echo "Installing git pre-commit hook..."
	@mkdir -p ../.git/hooks
	@echo '#!/bin/bash' > ../.git/hooks/pre-commit
	@echo 'cd tracker && make lint-cpp && make lint-python' >> ../.git/hooks/pre-commit
	@chmod +x ../.git/hooks/pre-commit
	@echo "✓ Pre-commit hook installed (C++ and Python linting)"

#####################################################################
# Linting and security scanning
#####################################################################

lint-cpp:
	@echo "Checking code formatting..."
	@if [ -n "$(SRC_FILES)" ]; then \
		clang-format --dry-run --Werror $(SRC_FILES) && echo "✓ All files properly formatted"; \
	else \
		echo "No source files to check"; \
	fi

lint-dockerfile:
	@echo "Linting Dockerfile with hadolint..."
	@command -v hadolint >/dev/null || (echo "hadolint not found. Install: wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 && chmod +x /usr/local/bin/hadolint" && exit 1)
	@hadolint --failure-threshold error Dockerfile && echo "✓ Dockerfile lint passed"

lint-python:
	@echo "Linting Python files..."
	@if ! command -v autopep8 >/dev/null 2>&1; then \
		echo "autopep8 not found. Install: pip install autopep8"; \
		exit 1; \
	fi
	@cd test/service && autopep8 --diff --exit-code --indent-size=2 --max-line-length=120 *.py && echo "✓ Python lint passed"

lint-trivy:
	@echo "Running Trivy security scan..."
	@command -v trivy >/dev/null || (echo "trivy not found. Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/" && exit 1)
	@trivy fs --severity LOW,MEDIUM,HIGH,CRITICAL --scanners vuln,misconfig,secret --exit-code 1 . && echo "✓ Trivy scan passed"

lint-all: lint-cpp lint-python lint-dockerfile lint-trivy
	@echo "✓ All linting checks passed"

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
	cmake --preset conan-release -DBUILD_TESTS=OFF -DGIT_COMMIT=$(GIT_COMMIT)
	cmake --build build-release -j

build-debug: dependencies-debug
	@echo "Building debug..."
	cmake --preset conan-debug -DBUILD_TESTS=ON -DGIT_COMMIT=$(GIT_COMMIT)
	cmake --build build-debug -j

build-profile: dependencies-profile
	@echo "Building profile..."
	cmake --preset conan-relwithdebinfo -DBUILD_TESTS=OFF -DGIT_COMMIT=$(GIT_COMMIT)
	cmake --build build-profile -j

#####################################################################
# Run targets
#####################################################################

run-release: build-release
	. build-release/conanrun.sh && ./build-release/$(NAME)

run-debug: build-debug
	. build-debug/conanrun.sh && ./build-debug/$(NAME)

#####################################################################
# Test targets
#####################################################################

test-unit: build-debug
	@echo "Running unit tests..."
	. build-debug/conanrun.sh && cd build-debug && ctest --output-on-failure

test-unit-coverage: build-debug
	@echo "Running unit tests with coverage..."
	@command -v lcov >/dev/null || (echo "lcov not found. Install: sudo apt-get install lcov" && exit 1)
	@command -v gcovr >/dev/null || (echo "gcovr not found. Install: pip install gcovr" && exit 1)
	@echo "Cleaning previous coverage data..."
	@find build-debug -name "*.gcda" -delete
	@echo "Running tests..."
	. build-debug/conanrun.sh && cd build-debug && ctest --output-on-failure
	@echo "Generating coverage reports..."
	$(MAKE) coverage-html
	$(MAKE) coverage-xml
	$(MAKE) coverage-report

coverage-html:
	@echo "Generating HTML coverage report with lcov..."
	@mkdir -p build-debug/coverage/html
	@lcov --capture --directory build-debug \
		--output-file build-debug/coverage/coverage.info \
		--rc branch_coverage=1 \
		--ignore-errors mismatch,gcov,unused \
		--quiet 2>/dev/null
	@lcov --remove build-debug/coverage/coverage.info \
		'/usr/*' \
		'*/test/*' \
		'*/.conan/*' \
		'*/.conan2/*' \
		'*/robot_vision/*' \
		'*/controller/*' \
		'*/build-debug/_deps/*' \
		'*/external/*' \
		'*/third_party/*' \
		'*/src/main.cpp' \
		--output-file build-debug/coverage/coverage-filtered.info \
		--rc branch_coverage=1 \
		--ignore-errors unused \
		--quiet 2>/dev/null
	@genhtml build-debug/coverage/coverage-filtered.info \
		--output-directory build-debug/coverage/html \
		--title "Tracker Service Coverage" \
		--branch-coverage \
		--function-coverage \
		--demangle-cpp \
		--ignore-errors mismatch \
		--quiet 2>/dev/null
	@echo "✓ HTML coverage report: build-debug/coverage/html/index.html"

coverage-xml:
	@echo "Generating Cobertura XML coverage report with gcovr..."
	@mkdir -p build-debug/coverage
	@gcovr build-debug \
		--root . \
		--exclude '.*test.*' \
		--exclude '.*/build-debug/.*' \
		--exclude '.*/usr/.*' \
		--exclude '.*/.conan/.*' \
		--exclude '.*/.conan2/.*' \
		--exclude '.*robot_vision.*' \
		--exclude '.*controller.*' \
		--exclude '.*external.*' \
		--exclude '.*third_party.*' \
		--exclude '.*main\.cpp' \
		--xml-pretty \
		--xml build-debug/coverage/coverage.xml \
		--exclude-unreachable-branches \
		--print-summary \
		> /dev/null
	@echo "✓ Cobertura XML report: build-debug/coverage/coverage.xml"

coverage-report:
	@echo ""
	@echo "========================================="
	@echo "Coverage Summary"
	@echo "========================================="
	@gcovr build-debug \
		--root . \
		--exclude '.*test.*' \
		--exclude '.*/build-debug/.*' \
		--exclude '.*/usr/.*' \
		--exclude '.*/.conan/.*' \
		--exclude '.*/.conan2/.*' \
		--exclude '.*robot_vision.*' \
		--exclude '.*controller.*' \
		--exclude '.*external.*' \
		--exclude '.*third_party.*' \
		--exclude '.*main\.cpp' \
		--exclude-unreachable-branches \
		--print-summary \
		--fail-under-line 90.0 \
		--fail-under-branch 50.0
	@echo "========================================="
	@echo "📊 Full report: build-debug/coverage/html/index.html"
	@echo "========================================="

test-service: build-image
	@echo "Setting up test virtual environment..."
	@python3 -m venv test/service/.venv 2>/dev/null || true
	@test/service/.venv/bin/pip install -q --upgrade pip
	@test/service/.venv/bin/pip install -q -r test/service/requirements.txt
	@echo "Running service tests..."
	cd test/service && .venv/bin/pytest -v --tb=short

#####################################################################
# Docker build targets
# - build-image: inherited from common.mk, builds runtime stage
# - build-image-debug: builds debug stage with gdbserver
#####################################################################

build-image-debug:
	$(MAKE) build-image TARGET=debug BUILD_TYPE=Debug IMAGE=scenescape-tracker-debug
	@mkdir -p build-debug
	@echo "Extracting debug binary for local symbol loading..."
	@docker create --name tracker-debug-tmp scenescape-tracker-debug:$(VERSION) >/dev/null 2>&1 || true
	@docker cp tracker-debug-tmp:/scenescape/bin/tracker build-debug/tracker 2>/dev/null || true
	@docker rm tracker-debug-tmp >/dev/null 2>&1 || true

build-image-profile:
	$(MAKE) build-image TARGET=runtime BUILD_TYPE=RelWithDebInfo IMAGE=scenescape-tracker-profile

run-image: build-image
	docker run --rm -it $(IMAGE):$(VERSION)

run-image-debug: build-image-debug
	docker run --rm -it --init -p 2345:2345 \
		--cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
		scenescape-tracker-debug:$(VERSION)

stop-image-debug:
	-docker stop $$(docker ps -q --filter ancestor=scenescape-tracker-debug:$(VERSION)) 2>/dev/null

#####################################################################
# Clean targets
#####################################################################

# Override common.mk clean to also remove local build directories
clean:
	rm -rf build-release build-debug build-profile test/service/.venv
	-docker rmi $(IMAGE):$(VERSION) $(IMAGE):latest 2>/dev/null || true
	-rm -f $(BUILD_DIR)/$(IMAGE)-*deps.txt $(LOG_FILE) 2>/dev/null || true
