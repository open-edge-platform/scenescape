# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

PYTHON ?= python3
CMAKE ?= cmake
CTEST ?= ctest
CONAN ?= conan
BUILD_DIR ?= build
TEST_BUILD_DIR ?= build-tests
COVERAGE_BUILD_DIR ?= build-coverage
CPP_COVERAGE_DIR ?= $(COVERAGE_BUILD_DIR)/coverage/cpp
GCOVR ?= gcovr
CPP_COVERAGE_LINE_MIN ?= 90
CPP_COVERAGE_BRANCH_MIN ?= 50
BUILD_TYPE ?= Release
JOBS ?= $(shell nproc)

.PHONY: all build build-cpp build-python dependencies-tests configure-tests build-tests \
	dependencies-coverage configure-coverage build-coverage test-cpp-coverage \
	test-cpp test-python test-unit clean

all: build

build: build-python

build-cpp:
	$(CMAKE) -S cpp -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
	  -DFG_BUILD_TESTS=OFF -DFG_NATIVE_ARCH=OFF
	$(CMAKE) --build $(BUILD_DIR) --parallel $(JOBS)

build-python:
	$(PYTHON) -m pip install .

dependencies-tests:
	$(CONAN) install . --output-folder=$(TEST_BUILD_DIR) --build=missing \
	  -s build_type=Debug

configure-tests: dependencies-tests
	$(CMAKE) -S cpp -B $(TEST_BUILD_DIR) \
	  -DCMAKE_TOOLCHAIN_FILE=$(abspath $(TEST_BUILD_DIR)/conan_toolchain.cmake) \
	  -DGTest_DIR=$(abspath $(TEST_BUILD_DIR)) \
	  -DCMAKE_BUILD_TYPE=Debug -DFG_BUILD_TESTS=ON -DFG_NATIVE_ARCH=OFF

build-tests: configure-tests
	$(CMAKE) --build $(TEST_BUILD_DIR) --parallel $(JOBS)

test-cpp: build-tests
	$(CTEST) --test-dir $(TEST_BUILD_DIR) --output-on-failure

dependencies-coverage:
	$(CONAN) install . --output-folder=$(COVERAGE_BUILD_DIR) --build=missing \
	  -s build_type=Debug

configure-coverage: dependencies-coverage
	$(CMAKE) -S cpp -B $(COVERAGE_BUILD_DIR) \
	  -DCMAKE_TOOLCHAIN_FILE=$(abspath $(COVERAGE_BUILD_DIR)/conan_toolchain.cmake) \
	  -DGTest_DIR=$(abspath $(COVERAGE_BUILD_DIR)) \
	  -DCMAKE_BUILD_TYPE=Debug -DFG_BUILD_TESTS=ON -DFG_NATIVE_ARCH=OFF \
	  -DCMAKE_CXX_FLAGS=--coverage \
	  -DCMAKE_EXE_LINKER_FLAGS=--coverage \
	  -DCMAKE_SHARED_LINKER_FLAGS=--coverage

build-coverage: configure-coverage
	$(CMAKE) --build $(COVERAGE_BUILD_DIR) --parallel $(JOBS)

test-cpp-coverage: build-coverage
	@command -v $(GCOVR) >/dev/null || \
	  (echo "gcovr not found; install it with: python3 -m pip install gcovr" && exit 1)
	@mkdir -p $(CPP_COVERAGE_DIR)
	@find $(COVERAGE_BUILD_DIR) -name "*.gcda" -delete
	. $(COVERAGE_BUILD_DIR)/conanrun.sh && \
	  $(CTEST) --test-dir $(COVERAGE_BUILD_DIR) --output-on-failure
	$(GCOVR) $(COVERAGE_BUILD_DIR) --root . --filter 'cpp/src/.*' \
	  --exclude-unreachable-branches --print-summary \
	  --fail-under-line $(CPP_COVERAGE_LINE_MIN) \
	  --fail-under-branch $(CPP_COVERAGE_BRANCH_MIN) \
	  --html-details $(CPP_COVERAGE_DIR)/index.html \
	  --xml-pretty --xml $(CPP_COVERAGE_DIR)/coverage.xml

test-python: build
	$(PYTHON) -m pytest tests/

test-unit: test-cpp test-python

clean:
	rm -rf $(BUILD_DIR) $(TEST_BUILD_DIR) $(COVERAGE_BUILD_DIR)