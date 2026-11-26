# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Test environments (design §5.9):
#   make venv               pinned Python venv for fast local iteration
#   make test-container     build the reference test container (common-base: GCC 12, Python 3.11)
#   make test-in-container  run `make test` inside the container (authoritative)

PYTHON ?= python3
VENV ?= .venv
VERSION ?= $(shell cat ../../version.txt)
BASE_IMAGE ?= intel/scenescape-common-base:$(VERSION)
TEST_IMAGE ?= intel/scenescape-observation-conditioning-test:$(VERSION)
# Import root of the Python package.
OC_PYTHONPATH ?= $(abspath ..)
REPO_ROOT := $(abspath ../..)
BASELINE_DIR := tests/data

.PHONY: venv test-container test-in-container test test-python baseline-original \
	baseline-original-in-container

venv: $(VENV)/.stamp

$(VENV)/.stamp: tests/requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --no-cache-dir -r tests/requirements.txt
	touch $@

test-container:
	docker build -f Dockerfile.test \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE) \
	  --build-arg http_proxy=$(http_proxy) --build-arg https_proxy=$(https_proxy) \
	  --build-arg no_proxy=$(no_proxy) \
	  -t $(TEST_IMAGE) .

# The whole repository is mounted: tests read the terrain dataset and the MVP sources.
test-in-container: test-container
	$(RUN_IN_CONTAINER) make test

define RUN_IN_CONTAINER
docker run --rm --user $(shell id -u):$(shell id -g) \
  -v $(REPO_ROOT):/work -w /work/spatial_performance_primitives/observation_conditioning \
  -e OC_PYTHONPATH=/work/spatial_performance_primitives -e OC_BASELINE_STRICT=1 -e HOME=/tmp $(TEST_IMAGE)
endef

test: test-python

test-python:
	PYTHONPATH="$(OC_PYTHONPATH)$${PYTHONPATH:+:$$PYTHONPATH}" $(PYTHON) -m pytest tests -q

# Regenerate the frozen baseline from the original MVP (run in the container).
baseline-original:
	PYTHONPATH="$(OC_PYTHONPATH)$${PYTHONPATH:+:$$PYTHONPATH}" \
	  $(PYTHON) tests/tools/generate_baseline.py --out $(BASELINE_DIR)/mvp-original.ocb

baseline-original-in-container: test-container
	$(RUN_IN_CONTAINER) make baseline-original
