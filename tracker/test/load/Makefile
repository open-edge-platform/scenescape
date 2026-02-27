# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Load test orchestrator: manages compose lifecycle, k6 generates load,
# pytest asserts SLIs against Prometheus metrics.
#
# Override defaults for boundary testing:
#   NUM_CAMERAS=8 FPS=30 NUM_OBJECTS=500 DURATION=5m make test

.PHONY: test setup clean

# Default test parameters
NUM_CAMERAS ?= 4
FPS ?= 15
NUM_OBJECTS ?= 300
DURATION ?= 1m
METRICS_EXPORT_INTERVAL_S ?= 1

# Version for docker image tags (inherited from parent)
VERSION ?= latest

setup:
	@echo "Setting up load test virtual environment..."
	@python3 -m venv .venv 2>/dev/null || true
	@.venv/bin/pip install -q --upgrade pip
	@.venv/bin/pip install -q -r requirements.txt
	@# Export interval of 1 s ensures wait_for_stable_counter sees fresh data
	@# (with 5 s the counter appears stable before the final export).
	@echo "Pre-building k6 image (Go compilation on first run)..."
	docker compose build k6

test: setup
	@echo "Starting load test infrastructure..."
	VERSION=$(VERSION) NUM_CAMERAS=$(NUM_CAMERAS) FPS=$(FPS) \
		NUM_OBJECTS=$(NUM_OBJECTS) DURATION=$(DURATION) \
		METRICS_EXPORT_INTERVAL_S=$(METRICS_EXPORT_INTERVAL_S) \
		docker compose up -d broker otel-collector tracker
	@echo "Running k6 load generator..."
	VERSION=$(VERSION) NUM_CAMERAS=$(NUM_CAMERAS) FPS=$(FPS) \
		NUM_OBJECTS=$(NUM_OBJECTS) DURATION=$(DURATION) \
		METRICS_EXPORT_INTERVAL_S=$(METRICS_EXPORT_INTERVAL_S) \
		docker compose run --rm k6; \
		K6_EXIT=$$?; \
		FLUSH_WAIT=$$(( $(METRICS_EXPORT_INTERVAL_S) * 3 + 2 )); \
		echo "Waiting $${FLUSH_WAIT}s for metrics pipeline to flush..."; \
		sleep $$FLUSH_WAIT; \
		echo "Asserting SLIs against Prometheus metrics..."; \
		.venv/bin/pytest -v --tb=short; \
		PYTEST_EXIT=$$?; \
		echo "Tearing down load test infrastructure..."; \
		docker compose down -v; \
		if [ $$K6_EXIT -ne 0 ]; then exit $$K6_EXIT; fi; \
		exit $$PYTEST_EXIT

clean:
	-docker compose down -v 2>/dev/null || true
	rm -rf .venv .pytest_cache __pycache__
