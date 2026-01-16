# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-autocalibration
RUNTIME_OS_IMAGE := python:3.11-slim-bookworm
TARGET = autocalibration-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="scenescape-autocalibration-test" TARGET="autocalibration-test"

# HLOC verification tests
.PHONY: verify-hloc-patches
verify-hloc-patches:
	@echo "Running HLOC patch verification tests..."
	@docker run --rm -it $(IMAGE):latest bash -c "cd /tmp/reloc && python3 /tmp/reloc/tests/run_tests.py"

.PHONY: verify-hloc-api
verify-hloc-api:
	@echo "Running HLOC API tests..."
	@docker run --rm -it $(IMAGE):latest bash -c "cd /tmp/reloc && python3 /tmp/reloc/tests/run_tests.py --api-only"

.PHONY: verify-hloc-functional
verify-hloc-functional:
	@echo "Running HLOC functional tests..."
	@docker run --rm -it $(IMAGE):latest bash -c "cd /tmp/reloc && python3 /tmp/reloc/tests/run_tests.py --functional-only"

.PHONY: verify-hloc-test
verify-hloc-test:
	@if [ -z "$(TEST)" ]; then \
		echo "Usage: make verify-hloc-test TEST=<test_name>"; \
		echo "Available tests: api, extraction, matching, matchers, database, workflows"; \
		exit 1; \
	fi
	@echo "Running HLOC test: $(TEST)..."
	@docker run --rm -it $(IMAGE):latest bash -c "cd /tmp/reloc && python3 /tmp/reloc/tests/run_tests.py --test $(TEST)"

