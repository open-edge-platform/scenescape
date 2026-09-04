# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ================ Makefile for Scenescape ====================

# =========================== Variables ==============================
SHELL := /bin/bash

# Build folders
COMMON_FOLDER := scene_common
CORE_IMAGE_FOLDERS := autocalibration controller manager analytics
IMAGE_FOLDERS := $(CORE_IMAGE_FOLDERS) mapping cluster_analytics tracker

# Image variables
IMAGE_PREFIX := scenescape
SOURCES_IMAGE := $(IMAGE_PREFIX)-sources
VERSION := $(shell cat ./version.txt)

# User configurable variables
COMPOSE_PROJECT_NAME ?= scenescape
# - User can adjust build output folder (defaults to $PWD/build)
BUILD_DIR ?= $(CURDIR)/build
# - User can adjust folders being built (defaults to all)
FOLDERS ?= $(CORE_IMAGE_FOLDERS)
# - User can adjust number of parallel jobs (defaults to CPU count)
JOBS ?= $(shell nproc)
# - User can adjust the target branch
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))
# Ensure BUILD_DIR path is absolute, so that it works correctly in recursive make calls
ifeq ($(filter /%,$(BUILD_DIR)),)
override BUILD_DIR := $(CURDIR)/$(BUILD_DIR)
endif

# Secrets building variables
SECRETSDIR ?= $(CURDIR)/manager/secrets
CERTDOMAIN ?= scenescape.intel.com

# Demo variables
SAMPLE_COMPOSE_DIR := sample_data/compose
VIDEO_SOURCE_DIR := sample_data/demo_scenes
VIDEO_SOURCE_COMPOSE_FILE := $(VIDEO_SOURCE_DIR)/docker-compose.yml
DLSTREAMER_SAMPLE_VIDEOS := $(addprefix $(VIDEO_SOURCE_DIR)/Retail/video/,apriltag-cam1.ts apriltag-cam2.ts apriltag-cam3.ts) \
	$(addprefix $(VIDEO_SOURCE_DIR)/Queuing/video/,qcam1.ts qcam2.ts) \
	sample_data/videos/car-detection.ts
DLSTREAMER_DOCKER_COMPOSE_FILE := ./$(SAMPLE_COMPOSE_DIR)/docker-compose-dl-streamer-example.yml
DEMO_WAIT_SECONDS ?= "0"
# Host directory with one subdirectory per demo scene (each holding a <name>.zip)
DEMO_SCENES_DIR ?= sample_data/demo_scenes
DEMO_SCENES_URL ?= https://localhost:$(if $(HTTPS_PORT),$(HTTPS_PORT),443)/api/v1
# The demo certificate is issued for web.scenescape.intel.com, not for localhost.
# Override with --rootcert <ca.pem> when uploading to a properly named host.
DEMO_SCENES_TLS ?= --insecure
# Seconds the scene upload waits for the database to come up
DEMO_SCENES_WAIT ?= 300
UPLOAD_SCENES := tools/upload_scenes/upload-scenes
# ReID vector backend used by the ReID demo targets: vdms (default) or qdrant
REID_BACKEND ?= vdms
REID_OVERRIDE_FILE = $(SAMPLE_COMPOSE_DIR)/docker-compose.$(strip $(REID_BACKEND))-override.yml
REID_PIPELINE_OVERRIDE_FILE = $(SAMPLE_COMPOSE_DIR)/docker-compose.reid-pipeline-override.yml
REID_COMPOSE_ARGS = -f docker-compose.yml -f $(REID_OVERRIDE_FILE) -f $(REID_PIPELINE_OVERRIDE_FILE)
DEMO_REBUILD_IMAGES ?= true
# Skip build-* prereqs when DEMO_REBUILD_IMAGES is falsy
DEMO_BUILD := $(if $(filter-out false 0 no,$(shell echo $(DEMO_REBUILD_IMAGES) | tr '[:upper:]' '[:lower:]')),build,)

# Test variables
TESTS_FOLDER := tests
TEST_DATA_FOLDER := test_data
TEST_IMAGE_FOLDERS := autocalibration controller manager mapping analytics cluster_analytics
TEST_IMAGES := $(addsuffix -test, autocalibration controller manager mapping analytics cluster_analytics)
DEPLOYMENT_TEST ?= 0

# Kubernetes demo variables
DEMO_K8S_MODE ?= core

# Observability variables
CONTROLLER_ENABLE_METRICS ?= false
CONTROLLER_METRICS_ENDPOINT ?= otel-collector.scenescape.intel.com:4317
CONTROLLER_METRICS_EXPORT_INTERVAL_S ?= 60
CONTROLLER_ENABLE_TRACING ?= false
CONTROLLER_TRACING_ENDPOINT ?= otel-collector.scenescape.intel.com:4317
CONTROLLER_TRACING_SAMPLE_RATIO ?= 1.0

# ========================= Default Target ===========================

default: build-core

.PHONY: build-core
build-core: init-secrets build-core-images install-models

.PHONY: build-all
build-all: init-secrets build-all-images install-models

# ============================== Help ================================

.PHONY: help
help:
	@echo ""
	@echo "Scenescape version $(VERSION)"
	@echo ""
	@echo "Available targets:"
	@echo "  build-core        (default) Build secrets, core images (excluding mapping, cluster_analytics, and tracker), and install models"
	@echo "  build-all                   Build secrets, all images, and install models"
	@echo "  build-core-images           Build core microservice images (excluding mapping, cluster_analytics, and tracker) in parallel"
	@echo "  build-all-images            Build all microservice images in parallel"
	@echo "  init-secrets                Generate secrets and certificates"
	@echo "  <image folder>              Build a specific microservice image (autocalibration, controller, etc.)"
	@echo ""
	@echo "  demo                        (default) Start the Scenescape demo with core services (tracking, no ReID)"
	@echo "  demo-reid                   Start the core demo plus the ReID vector database"
	@echo "  demo-all                    Start demo-reid plus cluster analytics and mapping services"
	@echo "  demo-cluster-analytics      Start the Scenescape demo with cluster analytics service using Docker Compose"
	@echo "                              (the demo targets require the SUPASS environment variable to be set"
	@echo "                              as the super user password for logging into Scenescape)"
	@echo "  demo-tracker                Start the Scenescape demo with Tracker + Analytics services (no Scene Controller) using Docker Compose"
	@echo "  demo-scenes                 Upload the demo scenes in DEMO_SCENES_DIR to a running deployment via the REST API"
	@echo "  demo-close                  Stop the running Scenescape demo and remove all volumes"
	@echo "  demo-k8s                    Start the Scenescape demo using Kubernetes (DEMO_K8S_MODE=core|reid|all, default: core)"
	@echo ""
	@echo "  list-dependencies           List all apt/pip dependencies for all microservices"
	@echo "  build-sources-image         Build the image with 3rd party sources"
	@echo "  install-models              Install custom OpenVINO Zoo models to models volume"
	@echo "  check-db-upgrade            Check if the database needs to be upgraded"
	@echo "  upgrade-database            Backup and upgrade database to a newer PostgreSQL version"
	@echo "                              (automatically transfers data to Docker volumes)"
	@echo ""
	@echo "  rebuild-core                Clean and build core images and create secrets and volumes"
	@echo "  rebuild-core-images         Clean and build core images"
	@echo "  rebuild-all                 Clean and build everything including secrets and volumes"
	@echo "  rebuild-all-images          Clean and build all images"
	@echo ""
	@echo "  clean-core                  Clean core images and remove secrets, volumes and models"
	@echo "  clean-core-images           Clean core images"
	@echo "  clean-all                   Clean everything including volumes, secrets and models"
	@echo "  clean-images                Clean all images"
	@echo "  clean-volumes               Remove all project Docker volumes"
	@echo "  clean-secrets               Remove all generated secrets"
	@echo "  clean-models                Remove all installed models"
	@echo "  clean-tests                 Clean test images and test artifacts (logs etc.)"
	@echo ""
	@echo "  run_tests                   Run all tests"
	@echo "  run_basic_acceptance_tests  Run basic acceptance tests"
	@echo "  run_functional_tests        Run functional tests"
	@echo "  run_ui_tests                Run UI tests"
	@echo "  run_unit_tests              Run unit tests"
	@echo "  run_stability_tests         Run stability tests"
	@echo "  run_performance_tests       Run performance tests"
	@echo "  run_metric_tests            Run metric tests"
	@echo "  setup-pytest                Create tests/.venv and install dependencies"
	@echo ""
	@echo "  lint-all                    Lint entire code base"
	@echo "  lint-python                 Lint python files"
	@echo "  lint-python-pylint          Lint python files using pylint"
	@echo "  lint-python-flake8          Lint python files using flake8"
	@echo "  lint-javascript             Lint javascript files"
	@echo "  lint-cpp                    Lint C++ files"
	@echo "  lint-html                   Lint HTML files"
	@echo "  lint-dockerfiles            Lint Dockerfiles"
	@echo "  lint-shell                  Lint shell files"
	@echo "  prettier-check              Run prettier check on all supported files"
	@echo ""
	@echo "  format-python               Format python files using autopep8"
	@echo "  prettier-write              Format code using prettier"
	@echo ""
	@echo "  add-licensing FILE=<file>   Add licensing headers to a file"
	@echo ""
	@echo "Usage:"
	@echo "  - Use 'SUPASS=<password> make build-all demo' to build Scenescape and run demo using Docker Compose."
	@echo "  - Use 'make build-all demo-k8s DEMO_K8S_MODE=all' to build Scenescape and run demo using Kubernetes with all services."
	@echo ""
	@echo "Tips:"
	@echo "  - Use 'make BUILD_DIR=<path>' to change build output folder (default is './build')."
	@echo "  - Use 'make JOBS=N' to build Scenescape images using N parallel processes."
	@echo "  - Use 'make FOLDERS=\"<list of image folders>\"' to build specific image folders."
	@echo "  - Image folders can be: $(IMAGE_FOLDERS)"
	@echo "  - ReID demo targets (demo-reid, demo-all, demo-k8s with DEMO_K8S_MODE=reid|all)"
	@echo "    default to REID_BACKEND=vdms. Set REID_BACKEND=qdrant to use Qdrant instead."
	@echo ""

# ========================= Build Images =============================

$(BUILD_DIR):
	mkdir -p $@

# Build common base image
.PHONY: build-common
build-common:
	@echo "==> Building common base image..."
	@$(MAKE) -C $(COMMON_FOLDER) http_proxy=$(http_proxy)
	@echo "DONE ==> Building common base image"

# Build targets for each service folder
.PHONY: $(IMAGE_FOLDERS)
$(IMAGE_FOLDERS):
	@echo "====> Building folder $@..."
	@$(MAKE) -C $@ BUILD_DIR=$(BUILD_DIR) http_proxy=$(http_proxy) https_proxy=$(https_proxy) no_proxy=$(no_proxy)
	@echo "DONE ====> Building folder $@"

# Dependency on the common base image
autocalibration controller manager analytics mapping cluster_analytics: build-common

# Helper function to build images in parallel
define parallel-build
	@echo "==> Running parallel builds of folders: $(1)"
	@set -e; trap 'grep --color=auto -i -r --include="*.log" "^error" $(BUILD_DIR) || true' EXIT; \
	$(MAKE) -j$(JOBS) $(1)
	@echo "DONE ==> Parallel builds of folders: $(1)"
endef

# Parallel wrapper handles parallel builds of folders specified in FOLDERS variable
.PHONY: build-all-images
build-all-images: $(BUILD_DIR)
	$(call parallel-build, $(IMAGE_FOLDERS))

# Parallel wrapper for core images (excluding mapping and cluster_analytics)
.PHONY: build-core-images
build-core-images: $(BUILD_DIR)
	@echo "==> Running parallel builds of core folders: $(CORE_IMAGE_FOLDERS)"
# Use a trap to catch errors and print logs if any error occurs in parallel build
	@set -e; trap 'grep --color=auto -i -r --include="*.log" "^error" $(BUILD_DIR) || true' EXIT; \
	$(MAKE) -j$(JOBS) $(CORE_IMAGE_FOLDERS)
	@echo "DONE ==> Parallel builds of core folders: $(CORE_IMAGE_FOLDERS)"

# ===================== Cleaning and Rebuilding =======================
.PHONY: rebuild-core-images
rebuild-core-images: clean-core-images build-core-images

.PHONY: rebuild-core
rebuild-core: clean-core build-core

.PHONY: rebuild-all-images
rebuild-all-images: clean-images build-all-images

.PHONY: rebuild-all
rebuild-all: clean-all build-all

define clean-image-folders
	@echo "==> Cleaning up all build artifacts..."
	@for dir in $(1); do \
		$(MAKE) -C $$dir clean 2>/dev/null; \
	done
	@echo "Cleaning common folder..."
	@$(MAKE) -C $(COMMON_FOLDER) clean 2>/dev/null
	@-rm -rf $(BUILD_DIR)
	@echo "DONE ==> Cleaning up all build artifacts"
endef

.PHONY: clean-core-images
clean-core-images:
	$(call clean-image-folders,$(CORE_IMAGE_FOLDERS))

.PHONY: clean-images
clean-images:
	$(call clean-image-folders,$(IMAGE_FOLDERS))

.PHONY: clean-core
clean-core: clean-core-images clean-secrets clean-volumes clean-models clean-tests
	$(call clean-artifacts)

.PHONY: clean-all
clean-all: clean-images clean-secrets clean-volumes clean-models clean-tests
	$(call clean-artifacts)

define clean-artifacts
	@echo "==> Cleaning build artifacts..."
	@-rm -f $(DLSTREAMER_SAMPLE_VIDEOS)
	@-rm -f docker-compose.yml .env
	@echo "DONE ==> Cleaning build artifacts"
endef

.PHONY: clean-models
clean-models:
	@echo "==> Cleaning up all models..."
	@-docker volume rm -f $${COMPOSE_PROJECT_NAME:-scenescape}_vol-models
	@echo "DONE ==> Cleaning up all models"

.PHONY: clean-volumes
clean-volumes: remove-stopped-containers
	@echo "==> Cleaning up all volumes..."
	@if [ -f ./docker-compose.yml ]; then \
		docker compose down -v 2>/dev/null; \
	else \
		VOLS=$$(docker volume ls -q --filter "name=$(COMPOSE_PROJECT_NAME)_"); \
		if [ -n "$$VOLS" ]; then \
			docker volume rm -f $$VOLS 2>/dev/null; \
		fi; \
	fi
	@echo "DONE ==> Cleaning up all volumes"

.PHONY: remove-stopped-containers
remove-stopped-containers:
	@echo "==> Removing stopped containers..."
	@docker container ls -q --filter "status=exited" | xargs -r docker container rm
	@echo "DONE ==> Removing stopped containers"

.PHONY: clean-secrets
clean-secrets:
	@echo "==> Cleaning secrets..."
	@-rm -rf $(SECRETSDIR)
	@echo "DONE ==> Cleaning secrets"

.PHONY: clean-tests
clean-tests:
	@echo "==> Cleaning test artifacts..."
	@-rm -rf test_data/
	@-rm -rf tests/.test_logs tests/.venv
	@echo "Cleaning fast_geometry build artifacts..."
	@-rm -f scene_common/src/fast_geometry/*.oxx scene_common/src/fast_geometry/*.so
	@-rm -rf scene_common/src/scene_common.egg-info
	@echo "Cleaning test images..."
	@for image in $(TEST_IMAGES); do \
		docker rmi $(IMAGE_PREFIX)-$$image:$(VERSION) $(IMAGE_PREFIX)-$$image:latest 2>/dev/null || true; \
	done
	@echo "DONE ==> Cleaning test artifacts"

# ===================== 3rd Party Dependencies =======================
.PHONY: list-dependencies
list-dependencies: $(BUILD_DIR)
	@echo "==> Listing dependencies for all microservices..."
	@set -e; \
	$(MAKE) -C $(COMMON_FOLDER) BUILD_DIR=$(BUILD_DIR) list-dependencies; \
	for dir in $(IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir BUILD_DIR=$(BUILD_DIR) list-dependencies; \
	done
	@echo "The following dependency lists have been generated:"
	@find $(BUILD_DIR) -name '*-deps.txt' -print
	@echo "DONE ==> Listing dependencies for all microservices"

BUILDKIT_BUILDER_NAME := scenescape-buildkit-container

# Generate SPDX SBOMs for all microservices using Docker BuildKit.
# A temporary BuildKit container builder is created automatically and removed on completion.
# Docs: https://www.docker.com/blog/generate-sboms-with-buildkit/
.PHONY: generate-sboms
generate-sboms: $(BUILD_DIR)
	@echo "==> Generating SPDX SBOMs for all microservices..."
	@echo "Creating BuildKit container builder..."
	@docker buildx create --use --name=$(BUILDKIT_BUILDER_NAME) --driver=docker-container \
		--driver-opt=env.http_proxy=$(http_proxy),env.https_proxy=$(https_proxy),env.HTTP_PROXY=$(HTTP_PROXY),env.HTTPS_PROXY=$(HTTPS_PROXY),default-load=true
	@set -e; trap 'docker buildx rm $(BUILDKIT_BUILDER_NAME) 2>/dev/null || true' EXIT; \
	for dir in $(IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir BUILD_DIR=$(BUILD_DIR) generate-sbom; \
	done
	@echo "The following SBOMs have been generated in $(BUILD_DIR)/sboms:"
	@echo "$$(ls $(BUILD_DIR)/sboms)"
	@echo "DONE ==> Generating SPDX SBOMs for all microservices"

.PHONY: build-sources-image
build-sources-image: sources.Dockerfile
	@echo "==> Building the image with 3rd party sources..."
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
		--build-arg http_proxy=$(http_proxy) \
		--build-arg https_proxy=$(https_proxy) \
		--build-arg no_proxy=$(no_proxy) \
		--rm -t $(SOURCES_IMAGE):$(VERSION) . \
	&& docker tag $(SOURCES_IMAGE):$(VERSION) $(SOURCES_IMAGE):latest
	@echo "DONE ==> Building the image with 3rd party sources"

# ======================= Model Installer ============================

.PHONY: install-models
install-models:
	@$(MAKE) -C model_download install-models

# =========================== Run Tests ==============================

NPROCS ?= $(shell echo $$(nproc) / 3 | bc)
PYTEST := $(CURDIR)/tests/.venv/bin/pytest
PYTEST_FLAGS := --rootdir=$(CURDIR)/tests -v --tb=short
TESTS_DIR := $(CURDIR)/tests

.PHONY: setup-tests
setup-tests: init-secrets .env setup-pytest build-common
	@echo "Setting up test environment..."
	for dir in $(TEST_IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir test-build; \
	done
	mkdir -p $(TEST_DATA_FOLDER)/netvlad_models
	@echo "DONE ==> Setting up test environment"

.PHONY: setup-pytest
setup-pytest:
	@if [ ! -d "$(CURDIR)/tests/.venv" ]; then \
		python3 -m venv $(CURDIR)/tests/.venv; \
	fi
	@echo "Installing venv dependencies..."; \
	$(CURDIR)/tests/.venv/bin/pip install --progress-bar on --upgrade pip; \
	cd $(CURDIR)/tests && $(CURDIR)/tests/.venv/bin/pip install --progress-bar on -r requirements.txt; \
	cd $(CURDIR)/tests && $(CURDIR)/tests/.venv/bin/pip install --progress-bar on pycocotools tabulate; \
	cd $(CURDIR)/tests && ( $(CURDIR)/tests/.venv/bin/pip install --no-deps -r requirements-no-deps.txt 2>&1 \
		| sed '/trackeval 1.0.1 requires numpy>=2.3.2; python_version >= "3.11", but you have numpy 2.2.6 which is incompatible\./d' ); \
	test $${PIPESTATUS[0]} -eq 0;
	@if ! $(CURDIR)/tests/.venv/bin/python3 -c "from fast_geometry import Point" 2>/dev/null; then \
		echo "Building fast_geometry C++ extension..."; \
		PATH="$(CURDIR)/tests/.venv/bin:$$PATH" \
			$(MAKE) -C $(CURDIR)/scene_common/src/fast_geometry all install; \
	fi
	@if ! $(CURDIR)/tests/.venv/bin/python3 -c "import robot_vision; assert hasattr(robot_vision, 'tracking')" 2>/dev/null; then \
		echo "Building robot_vision C++ extension..."; \
		for pkg in libopencv-dev libeigen3-dev; do \
			dpkg -s $$pkg > /dev/null 2>&1 || { echo "ERROR: $$pkg is required to build robot_vision. See tests/README.md for installation instructions."; exit 1; }; \
		done; \
		$(CURDIR)/tests/.venv/bin/pip install --no-cache-dir scikit-build-core cmake; \
		OpenCV_DIR="/usr/lib/x86_64-linux-gnu/cmake/opencv4" \
			$(CURDIR)/tests/.venv/bin/pip install --no-cache-dir --no-build-isolation $(CURDIR)/controller/src/robot_vision; \
	fi
	@FF_LOCATIONS="$$(which -a firefox 2>/dev/null || true)"; \
	if [ -z "$$FF_LOCATIONS" ]; then \
			echo "ERROR: Firefox is not installed. UI/Selenium tests will fail. See tests/README.md for installation instructions."; \
			exit 1; \
	fi; \
	FF_NON_SNAP="$$(echo "$$FF_LOCATIONS" | grep -v '/snap/' || true)"; \
	if [ -z "$$FF_NON_SNAP" ]; then \
			echo "ERROR: All firefox binaries are Snap-based:"; \
			echo "$$FF_LOCATIONS" | sed 's/^/  /'; \
			echo "Snap Firefox is incompatible with Selenium. See tests/README.md for installation instructions."; \
			exit 1; \
	fi
	@if [ ! -f "$(CURDIR)/tests/.venv/bin/geckodriver" ]; then \
		echo "geckodriver not found — downloading v0.36.0 into tests/.venv/bin/..."; \
		set -e; \
		BASE_URL=https://github.com/mozilla/geckodriver/releases; \
		GVERSION=v0.36.0; \
		curl -fSL "$${BASE_URL}/download/$${GVERSION}/geckodriver-$${GVERSION}-linux64.tar.gz" \
			| tar xz -C $(CURDIR)/tests/.venv/bin/ geckodriver; \
		echo "geckodriver installed to tests/.venv/bin/geckodriver"; \
	fi
	@if ! command -v Xvfb > /dev/null 2>&1; then \
		echo "WARNING: Xvfb is not installed. UI/Selenium tests will fail. See tests/README.md for installation instructions."; \
	fi

.PHONY: run_tests
run_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR)/functional/ $(TESTS_DIR)/ui/ \
		$(TESTS_DIR)/security/system/ $(TESTS_DIR)/system/stability/ \
		$(TESTS_DIR)/sscape_tests/ $(PYTEST_FLAGS) || (echo "Tests failed" && exit 1)
	@echo "DONE ==> Running tests"

.PHONY: run_standard_tests
run_standard_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running standard tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR)/functional/ $(TESTS_DIR)/ui/ \
		$(TESTS_DIR)/security/system/ $(TESTS_DIR)/system/stability/ $(PYTEST_FLAGS) || (echo "Standard tests failed" && exit 1)
	@echo "DONE ==> Running standard tests"

.PHONY: run_functional_tests
run_functional_tests: setup-tests build-core-images
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running functional tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR)/functional/ $(PYTEST_FLAGS) || (echo "Functional tests failed" && exit 1)
	@echo "DONE ==> Running functional tests"

.PHONY: run_non_functional_tests
run_non_functional_tests: init-secrets .env
	@echo "Running non-functional tests..."
	cd docs/user-guide/api-docs && npm install --save-dev swagger-cli@2.0.0 && npx swagger-cli validate api.yaml
	@echo "DONE ==> Running non-functional tests"

.PHONY: run_ui_tests
run_ui_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running UI tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR)/ui/ $(PYTEST_FLAGS) || (echo "UI tests failed" && exit 1)
	@echo "DONE ==> Running UI tests"

.PHONY: run_unit_tests
run_unit_tests: init-secrets setup-pytest
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running unit tests..."
	$(PYTEST) $(TESTS_DIR)/sscape_tests/ $(PYTEST_FLAGS) || (echo "Unit tests failed" && exit 1)
	@echo "DONE ==> Running unit tests"

.PHONY: run_basic_acceptance_tests
run_basic_acceptance_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running basic acceptance tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR) -m basic_acceptance $(PYTEST_FLAGS) || (echo "Basic acceptance tests failed" && exit 1)
	@echo "DONE ==> Running basic acceptance tests"

.PHONY: run_stability_tests
run_stability_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	$(eval HOURS ?= 24)
	@echo "Running stability tests..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		STABILITY_HOURS=$(HOURS) \
		$(PYTEST) $(TESTS_DIR)/system/stability/ $(PYTEST_FLAGS) || (echo "Stability tests failed" && exit 1)
	@echo "DONE ==> Running stability tests"

# --- Performance and metric tests ---

TEST_DATA ?= test_data
.PHONY: run_performance_tests
run_performance_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running performance tests..."
	$(MAKE) _run_performance_tests SUPASS=$(SUPASS) || (echo "Performance tests failed" && exit 1)
	@echo "DONE ==> Running performance tests"

.PHONY: _run_performance_tests
_run_performance_tests: inference-performance geometry-conformance

.PHONY: inference-performance
inference-performance: # NEX-T10412
	@echo "Running inference performance test..."
	SECRETSDIR=$(CURDIR)/manager/secrets SUPASS=$(SUPASS) \
		$(PYTEST) $(TESTS_DIR)/perf_tests/test_inference_performance.py $(PYTEST_FLAGS) \
		|| (echo "Inference performance test failed" && exit 1)

.PHONY: geometry-conformance
geometry-conformance:
	@echo "Running geometry conformance tests..."
	$(PYTEST) $(TESTS_DIR)/perf_tests/test_geometry_point.py \
		$(TESTS_DIR)/perf_tests/test_geometry_line.py $(PYTEST_FLAGS) \
		|| (echo "Geometry conformance tests failed" && exit 1)

GENERATE_JUNITXML = -o junit_logging=all --junitxml tests/reports/test_reports/$@.xml

.PHONY: run_metric_tests
run_metric_tests: setup-tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running metric tests..."
	$(MAKE) -j $(NPROCS) _run_metric_tests SUPASS=$(SUPASS) || (echo "Metric tests failed" && exit 1)
	@echo "DONE ==> Running metric tests"

.PHONY: _run_metric_tests
_run_metric_tests: idc-error-metric msoce-metric velocity-metric

define metric-recipe =
	$(eval TEST_SCRIPT=$1)
	$(eval TEST_SUITE=$2)
	$(eval LOGFILE=$(TEST_DATA)/smoke/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING METRIC TEST $@ \
	  ; if [ -n "$3" ] && [ -n "$4" ] && [ -n "$5" ]; then \
		METRIC="--metric $3" ; \
		THRESHOLD="--threshold $4" ; \
		FRAME_RATE="--camera_frame_rate $5" \
	  ; fi \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; $(PYTEST) -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
			$${METRIC} $${THRESHOLD} $${FRAME_RATE} \
			-o junit_suite_name=$(TEST_SUITE) | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@
endef

.PHONY: distance-msoce
distance-msoce: # NEX-T10524
	$(call metric-recipe, tests/system/metric/test_distance_thresh.py, distance-threshold)

.PHONY: idc-error-metric
idc-error-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, idc-metric, idc-error, 0.05, 30)
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, idc-metric, idc-error, 0.05, 10)

.PHONY: msoce-metric
msoce-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, msoce-metric, msoce, 0.05, 30)
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, msoce-metric, msoce, 0.05, 10)

.PHONY: velocity-metric
velocity-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, velocity-metric, velocity, 0.15, 30)
	$(call metric-recipe, tests/system/metric/test_tracker_metric.py, velocity-metric, velocity, 0.15, 10)

# ============================= Lint ==================================

.PHONY: lint-all
lint-all: lint-python lint-javascript lint-cpp lint-shell lint-dockerfiles prettier-check
	@echo "==> Linting entire code base..."
	$(MAKE) lint-python
	@echo "DONE ==> Linting entire code base":

.PHONY: lint-python
lint-python: lint-python-pylint lint-python-flake8

.PHONY: lint-python-pylint
lint-python-pylint:
	@echo "==> Linting Python files - pylint..."
	@pylint ./*/src tests/* tools/* || (echo "Python linting failed" && exit 1)
	@echo "DONE ==> Linting Python files - pylint"

.PHONY: lint-python-flake8
lint-python-flake8:
	@echo "==> Linting Python files - flake8..."
	@flake8 || (echo "Python linting failed" && exit 1)
	@echo "DONE ==> Linting Python files - flake8"

.PHONY: lint-javascript
lint-javascript:
	@echo "==> Linting JavaScript files..."
	@find . -name '*.js'  | xargs npx eslint -c .github/resources/eslint.config.js --no-warn-ignored || (echo "Javascript linting failed" && exit 1)
	@echo "DONE ==> Linting JavaScript files"

.PHONY: lint-cpp
lint-cpp:
	@echo "==> Linting C++ files..."
	@find . -name '*.c' -o -name '*.cpp' -o -name '*.h'  | xargs cpplint || (echo "C++ linting failed" && exit 1)
	@echo "DONE ==> Linting C++ files"

.PHONY: lint-shell
SH_FILES := $(shell find . -type f \( -name '*.sh' \) -print )
lint-shell:
	@echo "==> Linting Shell files..."
	@shellcheck -x -S style $(SH_FILES) || (echo "Shell linting failed" && exit 1)
	@echo "DONE ==> Linting Shell files"

.PHONY: lint-dockerfiles
lint-dockerfiles:
	@echo "==> Linting Dockerfiles..."
	@find . -name '*Dockerfile*' | xargs hadolint || (echo "Dockerfile linting failed" && exit 1)
	@echo "DONE ==> Linting Dockerfiles"

.PHONY: prettier-check
prettier-check:
	@echo "==> Checking style with prettier..."
	@npx prettier --check . --ignore-path .gitignore --ignore-path .github/resources/.prettierignore --config .github/resources/.prettierrc.json  || (echo "Prettier check failed - run 'make prettier-write' to fix" && exit 1)
	@echo "DONE ==> Checking style with prettier"

.PHONY: indent-check
indent-check:
	@echo "==> Checking Python indentation..."
	@tests/scripts/checkIndent
	@echo "DONE ==> Checking Python indentation"

# ===================== Format Code ================================

.PHONY: format-python
format-python:
	@echo "==> Formatting Python files..."
	@find . -name "*.py" -not -path "./venv/*" | xargs autopep8 --in-place --aggressive --aggressive || (echo "Python formatting failed" && exit 1)
	@echo "DONE ==> Formatting Python files"

.PHONY: prettier-write
prettier-write:
	@echo "==> Formatting code with prettier..."
	@npx prettier --write . --ignore-path .gitignore --ignore-path .github/resources/.prettierignore --config .github/resources/.prettierrc.json || (echo "Prettier formatting failed" && exit 1)
	@echo "DONE ==> Formatting code with prettier"

# ===================== Licensing Management ========================

.PHONY: add-licensing
add-licensing:
	@reuse annotate --template template $(ADDITIONAL_LICENSING_ARGS) --merge-copyrights --copyright-prefix="spdx-c" --copyright="Intel Corporation" --license="Apache-2.0" $(FILE) || (echo "Adding license failed" && exit 1)

# ===================== Docker Compose Demo ==========================

.PHONY: convert-dls-videos
convert-dls-videos:
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);

# tools/pipeline_runner mounts a "vol-videos" named volume (unlike the
# standalone video-source compose stack, which bind-mounts the files
# directly); populate it from the two source directories it needs.
.PHONY: init-pipeline-runner-videos
init-pipeline-runner-videos: convert-dls-videos
	@docker volume create $(COMPOSE_PROJECT_NAME)_vol-videos 2>/dev/null || true
	@docker run --rm -v $(CURDIR)/$(VIDEO_SOURCE_DIR)/Queuing/video:/source:ro -v $(COMPOSE_PROJECT_NAME)_vol-videos:/dest alpine:3.23 sh -c "cp -n /source/*.ts /dest/ 2>/dev/null || true"
	@docker run --rm -v $(CURDIR)/sample_data/videos:/source:ro -v $(COMPOSE_PROJECT_NAME)_vol-videos:/dest alpine:3.23 sh -c "cp -n /source/*.ts /dest/ 2>/dev/null || true"

# Video-source stack (mediamtx + per-scene ffmpeg loopers) lives outside the
# Scenescape stack; it joins the same "scenescape" Docker network so the
# dlsps pipelines keep resolving rtsp://mediaserver:8554/<camera-id>.
.PHONY: video-source-up
video-source-up: convert-dls-videos
	SCENESCAPE_NETWORK=$(COMPOSE_PROJECT_NAME)_scenescape docker compose -f $(VIDEO_SOURCE_COMPOSE_FILE) up -d

.PHONY: video-source-down
video-source-down:
	-SCENESCAPE_NETWORK=$(COMPOSE_PROJECT_NAME)_scenescape docker compose -f $(VIDEO_SOURCE_COMPOSE_FILE) down

# Helper target to start demo with compose
define start_demo
	@$(MAKE) docker-compose.yml
	@$(MAKE) .env
	@if [ -z "$$SUPASS" ]; then \
		echo "Please set the SUPASS environment variable before starting the demo for the first time."; \
		echo "The SUPASS environment variable is the super user password for logging into Scenescape."; \
		exit 1; \
	fi
	@if [ "$$BROKER_PORT" != "" ] && [ "$$BROKER_PORT" != "1883" ]; then \
		echo "Updating docker-compose.yml with custom MQTT broker port: $$BROKER_PORT"; \
		sed -i -E "s/[0-9]+:1883/$$BROKER_PORT:1883/g" docker-compose.yml; \
	fi
	@if [ "$$HTTPS_PORT" != "" ] && [ "$$HTTPS_PORT" != "443" ]; then \
		echo "Updating docker-compose.yml with custom HTTPS port: $$HTTPS_PORT"; \
		sed -i -E "s/[0-9]+:443/$$HTTPS_PORT:443/g" docker-compose.yml; \
	fi
	@echo "$(1)" > .scenescape-profile
	@if [ "$(DEMO_WAIT_SECONDS)" != "0" ]; then \
		echo "Waiting for Scenescape services to be ready..."; \
		docker compose $(1) up -d --wait --wait-timeout $(DEMO_WAIT_SECONDS); \
	else \
		echo "Starting Scenescape services in detached mode..."; \
		docker compose $(1) up -d; \
	fi
	@$(MAKE) video-source-up
	@$(MAKE) demo-scenes
	@echo ""
	@echo "To stop Scenescape, type:"
	@echo "    docker compose $(1) down"
	@echo "Or use: make demo-close"
endef

.PHONY: check-reid-backend
check-reid-backend:
	@case "$(strip $(REID_BACKEND))" in \
		vdms|qdrant) ;; \
		*) echo "REID_BACKEND must be 'vdms' (default) or 'qdrant'"; exit 1 ;; \
	esac

.PHONY: demo-scenes
demo-scenes:
	@VENV="tools/upload_scenes/.venv"; \
	if [ ! -d "$$VENV" ]; then \
		python3 -m venv "$$VENV"; \
		"$$VENV/bin/pip" install -q -r tools/upload_scenes/requirements.txt; \
	fi
	@echo "Uploading demo scenes from $(DEMO_SCENES_DIR) to $(DEMO_SCENES_URL)..."
	@VENV="tools/upload_scenes/.venv"; \
	"$$VENV/bin/python3" $(UPLOAD_SCENES) --restauth $(SECRETSDIR)/controller.auth \
		$(DEMO_SCENES_TLS) --wait $(DEMO_SCENES_WAIT) \
		$(DEMO_SCENES_URL) $(DEMO_SCENES_DIR)

.PHONY: demo
demo: $(DEMO_BUILD:build=build-core)
	$(call start_demo,--profile controller)

.PHONY: demo-reid
demo-reid: check-reid-backend $(DEMO_BUILD:build=build-core)
	$(call start_demo,$(strip $(REID_COMPOSE_ARGS) --profile controller))

.PHONY: demo-all
demo-all: check-reid-backend $(DEMO_BUILD:build=build-all)
	$(call start_demo,$(strip $(REID_COMPOSE_ARGS) --profile controller --profile cluster-analytics --profile mapping))

.PHONY: demo-cluster-analytics
demo-cluster-analytics: $(DEMO_BUILD:build=build-all)
	$(call start_demo,--profile controller --profile cluster-analytics)

.PHONY: demo-tracker
demo-tracker: $(DEMO_BUILD:build=build-all)
	$(call start_demo,--profile tracker)

.PHONY: demo-close
demo-close:
	@if [ ! -f .scenescape-profile ]; then \
		echo "Error: .scenescape-profile not found. Was the demo started with 'make demo'?"; \
		exit 1; \
	fi
	docker compose $(shell cat .scenescape-profile 2>/dev/null) down -v
	@$(MAKE) video-source-down
	@rm -f .scenescape-profile

.PHONY: demo-k8s
demo-k8s: check-reid-backend
	$(MAKE) -C kubernetes DEPLOYMENT_TEST=$(DEPLOYMENT_TEST) DEMO_K8S_MODE=$(DEMO_K8S_MODE) REID_BACKEND=$(strip $(REID_BACKEND))

.PHONY: docker-compose.yml
docker-compose.yml:
	cp $(DLSTREAMER_DOCKER_COMPOSE_FILE) $@;

$(DLSTREAMER_SAMPLE_VIDEOS): $(VIDEO_SOURCE_DIR)/convert_videos.sh
	@echo "==> Converting sample videos for DLStreamer..."
	@$(VIDEO_SOURCE_DIR)/convert_videos.sh
	@echo "DONE ==> Converting sample videos for DLStreamer..."

.PHONY: .env
.env:
	@echo "SECRETSDIR=$(SECRETSDIR)" > $@
	@echo "VERSION=$(VERSION)" >> $@
	@echo "GID=$$(id -g)" >> $@
	@echo "UID=$$(id -u)" >> $@
	@echo "DOCKER_CONTENT_TRUST=1" >> $@
	@echo "CONTROLLER_AUTH=$$(cat $(SECRETSDIR)/controller.auth)" >> $@
	@echo DATABASE_PASSWORD=$$(sed -nr "/DATABASE_PASSWORD=/s/.*'([^']+)'/\\1/p" ${SECRETSDIR}/django/secrets.py) >> $@
	@echo "CONTROLLER_ENABLE_METRICS=$(CONTROLLER_ENABLE_METRICS)" >> $@
	@echo "CONTROLLER_METRICS_ENDPOINT=$(CONTROLLER_METRICS_ENDPOINT)" >> $@
	@echo "CONTROLLER_METRICS_EXPORT_INTERVAL_S=$(CONTROLLER_METRICS_EXPORT_INTERVAL_S)" >> $@
	@echo "CONTROLLER_ENABLE_TRACING=$(CONTROLLER_ENABLE_TRACING)" >> $@
	@echo "CONTROLLER_TRACING_ENDPOINT=$(CONTROLLER_TRACING_ENDPOINT)" >> $@
	@echo "CONTROLLER_TRACING_SAMPLE_RATIO=$(CONTROLLER_TRACING_SAMPLE_RATIO)" >> $@
# ======================= Secrets Management =========================

.PHONY: init-secrets
init-secrets: $(SECRETSDIR) certificates auth-secrets

$(SECRETSDIR):
	mkdir -p $@
	@if ! chmod go-rwx $(SECRETSDIR); then \
		if [ "$${CI}" = "true" ] || [ "$${CI}" = "1" ]; then \
			echo "Warning: could not set restrictive permissions on $(SECRETSDIR) in CI; secrets may be more exposed on this filesystem. Ensure runner isolation controls are in place."; \
		else \
			exit 1; \
		fi; \
	fi

.PHONY: $(SECRETSDIR) certificates
# Hierarchy functional tests need SANs for parent-/child*-web/broker and reid-*.
# Override with empty values for minimal production-like certs, e.g.
#   make certificates BROKER_EXTRA_HOSTS= WEB_EXTRA_HOSTS= REID_S_EXTRA_HOSTS=
BROKER_EXTRA_HOSTS ?= parent-broker child1-broker child2-broker
WEB_EXTRA_HOSTS ?= parent-web child1-web child2-web
REID_S_EXTRA_HOSTS ?= reid-shared reid-a reid-b
certificates:
	@make -C ./tools/certificates CERTPASS=$$(openssl rand -base64 12) \
		SECRETSDIR=$(SECRETSDIR) CERTDOMAIN=$(CERTDOMAIN) \
		BROKER_EXTRA_HOSTS="$(BROKER_EXTRA_HOSTS)" \
		WEB_EXTRA_HOSTS="$(WEB_EXTRA_HOSTS)" \
		REID_S_EXTRA_HOSTS="$(REID_S_EXTRA_HOSTS)"

.PHONY: auth-secrets
auth-secrets:
	$(MAKE) -C ./tools/authsecrets SECRETSDIR=$(SECRETSDIR)

# Database upgrade target
.PHONY: check-db-upgrade upgrade-database

check-db-upgrade:
	@if manager/tools/upgrade-database --check >/dev/null 2>&1; then \
		echo "Database upgrade is required."; \
		exit 0; \
	else \
		echo "No database upgrade needed."; \
		exit 1; \
	fi

upgrade-database:
	@echo "Starting database upgrade process..."
	@if ! manager/tools/upgrade-database --check >/dev/null 2>&1; then \
		echo "No database upgrade needed."; \
		exit 0; \
	fi
	@UPGRADE_LOG=/tmp/upgrade.$(shell date +%s).log; \
	echo "Upgrading database (log at $$UPGRADE_LOG)..."; \
	manager/tools/upgrade-database 2>&1 | tee $$UPGRADE_LOG; \
	NEW_DB=$$(grep -E 'Upgraded database .* has been created in Docker volumes' $$UPGRADE_LOG | sed -e 's/.*created in Docker volumes.*//'); \
	if [ $$? -ne 0 ]; then \
		echo ""; \
		echo "ABORTING"; \
		echo "Automatic upgrade of database failed"; \
		exit 1; \
	fi; \
	echo ""; \
	echo "Database upgrade completed successfully."; \
	echo "Database is now stored in Docker volumes:"; \
	echo "  - Database: scenescape_vol-db"; \
	echo "  - Migrations: scenescape_vol-migrations"

.PHONY: backupdb
backupdb:
	@echo "==> Starting backup of database and migrations volumes..."
	@backup_dir=$(CURDIR)/scenescape_vol-backup; \
	mkdir -p "$$backup_dir"; \
	echo "Creating tar backup of database volume 'scenescape_vol-db'..."; \
	docker run --rm \
		-v scenescape_vol-db:/volume \
		-v $$backup_dir:/backup \
		alpine sh -c "tar czf /backup/db-backup.tar.gz -C /volume ."; \
	echo "Database volume backup created at: $$backup_dir/db-backup.tar.gz"; \
	echo "Creating tar backup of migrations volume 'scenescape_vol-migrations'..."; \
	docker run --rm \
		-v scenescape_vol-migrations:/volume \
		-v $$backup_dir:/backup \
		alpine sh -c "tar czf /backup/migrations-backup.tar.gz -C /volume ."; \
	echo "Migrations volume backup created at: $$backup_dir/migrations-backup.tar.gz"; \
	echo "Creating tar backup of media volume 'scenescape_vol-media'..."; \
	docker run --rm \
		-v scenescape_vol-media:/volume \
		-v $$backup_dir:/backup \
		alpine sh -c "tar czf /backup/media-backup.tar.gz -C /volume ."; \
	echo "Media volume backup created at: $$backup_dir/media-backup.tar.gz"; \
	echo "==> Backup completed successfully."

.PHONY: clean-backup
clean-backup:
	@echo "==> Cleaning backup directory and backup volumes..."
	@if [ -d "$(CURDIR)/scenescape_vol-backup" ]; then \
		echo " - Removing directory: $(CURDIR)/scenescape_vol-backup"; \
		rm -rf "$(CURDIR)/scenescape_vol-backup"; \
	else \
		echo " - Backup directory not found"; \
	fi
	@for vol in scenescape_vol-migrations-backup scenescape_vol-media-backup scenescape_vol-db-backup; do \
		if docker volume ls -q | grep -q "^$$vol$$"; then \
			echo " - Removing volume: $$vol"; \
			docker volume rm $$vol >/dev/null; \
		else \
			echo " - Volume '$$vol' not found"; \
		fi; \
	done
	@echo "==> Cleanup complete."
