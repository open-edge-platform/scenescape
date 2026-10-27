# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Load test orchestrator: manages compose lifecycle, k6 generates load,
# pytest asserts SLIs against Prometheus metrics.
#
# Override defaults for boundary testing:
#   NUM_CAMERAS=8 FPS=30 NUM_OBJECTS=500 DURATION=5m make test

.PHONY: test setup clean

# Default test parameters
SCENARIO ?= camera
NUM_CAMERAS ?= 4
NUM_EXTERNAL_SOURCES ?= $(if $(filter external mixed,$(SCENARIO)),4,0)
FPS ?= 15
EXTERNAL_FPS ?= $(FPS)
CHUNKING_FPS ?= $(FPS)
NUM_OBJECTS ?= 300
DURATION ?= 1m
METRICS_EXPORT_INTERVAL_S ?= 1
LOAD_SCENE_ID := 302cf49a-97ec-402d-a324-c5077b280b7b
EXTERNAL_SOURCE_IDS := $(shell python3 -c 'print(",".join("load-agent-{}".format(i) for i in range(1, int("$(NUM_EXTERNAL_SOURCES)") + 1)))')
EXTERNAL_SOURCE_BINDINGS := $(shell python3 -c 'scene="$(LOAD_SCENE_ID)"; print(",".join("load-agent-{}:{}".format(i, scene) for i in range(1, int("$(NUM_EXTERNAL_SOURCES)") + 1)))')

export SCENARIO NUM_CAMERAS NUM_EXTERNAL_SOURCES FPS EXTERNAL_FPS CHUNKING_FPS
export NUM_OBJECTS DURATION METRICS_EXPORT_INTERVAL_S EXTERNAL_SOURCE_IDS
export EXTERNAL_SOURCE_BINDINGS

# Version for docker image tags (inherited from parent)
VERSION ?= latest

setup:
	@case "$(SCENARIO)" in camera|external|mixed) ;; \
		*) echo "SCENARIO must be camera, external, or mixed"; exit 1 ;; \
	esac
	@test "$(NUM_CAMERAS)" -ge 0 && test "$(NUM_EXTERNAL_SOURCES)" -ge 0
	@test $$(( $(NUM_CAMERAS) + $(NUM_EXTERNAL_SOURCES) )) -gt 0
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
	VERSION=$(VERSION) SCENARIO=$(SCENARIO) NUM_CAMERAS=$(NUM_CAMERAS) \
		NUM_EXTERNAL_SOURCES=$(NUM_EXTERNAL_SOURCES) FPS=$(FPS) \
		EXTERNAL_FPS=$(EXTERNAL_FPS) CHUNKING_FPS=$(CHUNKING_FPS) \
		EXTERNAL_SOURCE_IDS='$(EXTERNAL_SOURCE_IDS)' \
		EXTERNAL_SOURCE_BINDINGS='$(EXTERNAL_SOURCE_BINDINGS)' \
		NUM_OBJECTS=$(NUM_OBJECTS) DURATION=$(DURATION) \
		METRICS_EXPORT_INTERVAL_S=$(METRICS_EXPORT_INTERVAL_S) \
		docker compose up -d broker otel-collector tracker
	@echo "Running k6 load generator..."
	@set +e; \
		 run_load_generator() { K6_SCRIPT=$$1 docker compose run --rm k6; }; \
		 K6_EXIT=0; \
		 if [ "$(SCENARIO)" = camera ]; then \
		   run_load_generator simulate-detections.js; K6_EXIT=$$?; \
		 elif [ "$(SCENARIO)" = external ]; then \
		   run_load_generator simulate-external.js; K6_EXIT=$$?; \
		 else \
		   run_load_generator simulate-detections.js & CAMERA_PID=$$!; \
		   run_load_generator simulate-external.js & EXTERNAL_PID=$$!; \
		   wait $$CAMERA_PID; CAMERA_EXIT=$$?; \
		   wait $$EXTERNAL_PID; EXTERNAL_EXIT=$$?; \
		   if [ $$CAMERA_EXIT -ne 0 ]; then K6_EXIT=$$CAMERA_EXIT; fi; \
		   if [ $$EXTERNAL_EXIT -ne 0 ] && [ $$K6_EXIT -eq 0 ]; then \
		     K6_EXIT=$$EXTERNAL_EXIT; \
		   fi; \
		 fi; \
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
