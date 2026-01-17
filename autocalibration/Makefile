# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := scenescape-autocalibration
TEST_IMAGE := scenescape-autocalibration-test
RUNTIME_OS_IMAGE := python:3.11-slim-bookworm
TARGET = autocalibration-runtime

include ../common.mk

.PHONY: test-build
test-build:
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="autocalibration-test"

# HLOC verification tests
.PHONY: verify-hloc-patches
verify-hloc-patches:
	@echo "Running HLOC patch verification tests..."
	@docker run --rm -it --entrypoint bash -e http_proxy -e https_proxy $(TEST_IMAGE):latest -c "cd /opt/hloc-tests && python3 run_tests.py"

.PHONY: verify-hloc-api
verify-hloc-api:
	@echo "Running HLOC API tests..."
	@docker run --rm -it --entrypoint bash -e http_proxy -e https_proxy $(TEST_IMAGE):latest -c "cd /opt/hloc-tests && python3 run_tests.py --api-only"

.PHONY: verify-hloc-functional
verify-hloc-functional:
	@echo "Running HLOC functional tests..."
	@docker run --rm -it --entrypoint bash -e http_proxy -e https_proxy $(TEST_IMAGE):latest -c "cd /opt/hloc-tests && python3 run_tests.py --functional-only"

.PHONY: verify-hloc-test
verify-hloc-test:
	@if [ -z "$(TEST)" ]; then \
		echo "Usage: make verify-hloc-test TEST=<test_name>"; \
		echo "Available tests: api, extraction, matching, matchers, database, workflows, localize_scenescape"; \
		exit 1; \
	fi
	@echo "Running HLOC test: $(TEST)..."
	@docker run --rm -it --entrypoint bash -e http_proxy -e https_proxy $(TEST_IMAGE):latest -c "cd /opt/hloc-tests && python3 run_tests.py --test $(TEST)"

.PHONY: verify-pose-from-cluster
verify-pose-from-cluster:
	@echo "Running pose_from_cluster tests..."
	@docker run --rm -it --entrypoint bash -e http_proxy -e https_proxy $(TEST_IMAGE):latest -c "cd /opt/hloc-tests && python3 -m pytest test_localize_scenescape.py::TestPoseFromCluster -v"
