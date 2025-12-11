# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ================ Makefile for Intel® SceneScape ====================

# =========================== Variables ==============================
SHELL := /bin/bash

# Build folders
COMMON_FOLDER := scene_common
CORE_IMAGE_FOLDERS := autocalibration controller manager model_installer
IMAGE_FOLDERS := $(CORE_IMAGE_FOLDERS) mapping cluster_analytics

# Build flags
EXTRA_BUILD_FLAGS :=
REBUILDFLAGS :=

# Image variables
IMAGE_PREFIX := scenescape
SOURCES_IMAGE := $(IMAGE_PREFIX)-sources
VERSION := $(shell cat ./version.txt)

# User configurable variables
COMPOSE_PROJECT_NAME ?= scenescape
# - User can adjust build output folder (defaults to $PWD/build)
BUILD_DIR ?= $(PWD)/build
# - User can adjust folders being built (defaults to all)
FOLDERS ?= $(CORE_IMAGE_FOLDERS)
# - User can adjust number of parallel jobs (defaults to CPU count)
JOBS ?= $(shell nproc)
# - User can adjust the target branch
TARGET_BRANCH ?= $(if $(CHANGE_TARGET),$(CHANGE_TARGET),$(BRANCH_NAME))
# Ensure BUILD_DIR path is absolute, so that it works correctly in recursive make calls
ifeq ($(filter /%,$(BUILD_DIR)),)
override BUILD_DIR := $(PWD)/$(BUILD_DIR)
endif

# Secrets building variables
SECRETSDIR ?= $(PWD)/manager/secrets
CERTDOMAIN ?= scenescape.intel.com

# Demo variables
DLSTREAMER_SAMPLE_VIDEOS := $(addprefix sample_data/,apriltag-cam1.ts apriltag-cam2.ts apriltag-cam3.ts qcam1.ts qcam2.ts)
DLSTREAMER_DOCKER_COMPOSE_FILE := ./sample_data/docker-compose-dl-streamer-example.yml

# Test variables
TESTS_FOLDER := tests
TEST_DATA_FOLDER := test_data
TEST_IMAGE_FOLDERS := autocalibration controller manager mapping cluster_analytics
TEST_IMAGES := $(addsuffix -test, autocalibration controller manager mapping cluster_analytics)
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

.PHONY: build-experimental
build-experimental: build-experimental-images

# ============================== Help ================================

.PHONY: help
help:
	@echo ""
	@echo "Intel® SceneScape version $(VERSION)"
	@echo ""
	@echo "Available targets:"
	@echo "  build-core        (default) Build secrets, core images (excluding mapping and cluster_analytics), and install models"
	@echo "  build-all                   Build secrets, all images, and install models"
	@echo "  build-experimental          Build experimental images only (mapping and cluster_analytics)"
	@echo "  build-core-images           Build core microservice images (excluding mapping and cluster_analytics) in parallel"
	@echo "  build-all-images            Build all microservice images in parallel"
	@echo "  build-experimental-images   Build experimental microservice images (mapping and cluster_analytics) in parallel"
	@echo "  init-secrets                Generate secrets and certificates"
	@echo "  <image folder>              Build a specific microservice image (autocalibration, controller, etc.)"
	@echo ""
	@echo "  demo                        (default) Start the SceneScape demo with core services using Docker Compose"
	@echo "  demo-all                    Start the SceneScape demo with all services using Docker Compose"
	@echo "                              (the demo targets require the SUPASS environment variable to be set"
	@echo "                              as the super user password for logging into Intel® SceneScape)"
	@echo "  demo-k8s                    Start the SceneScape demo using Kubernetes (DEMO_K8S_MODE=core|all, default: core)"
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
	@echo "  run_performance_tests       Run performance tests"
	@echo "  run_stability_tests         Run stability tests"
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
	@echo "  - Use 'SUPASS=<password> make build-all demo' to build Intel® SceneScape and run demo using Docker Compose."
	@echo "  - Use 'make build-all demo-k8s DEMO_K8S_MODE=all' to build Intel® SceneScape and run demo using Kubernetes with all services."
	@echo ""
	@echo "Tips:"
	@echo "  - Use 'make BUILD_DIR=<path>' to change build output folder (default is './build')."
	@echo "  - Use 'make JOBS=N' to build Intel® SceneScape images using N parallel processes."
	@echo "  - Use 'make FOLDERS=\"<list of image folders>\"' to build specific image folders."
	@echo "  - Image folders can be: $(IMAGE_FOLDERS)"
	@echo ""

# ========================== CI specific =============================

ifneq (,$(filter DAILY TAG,$(BUILD_TYPE)))
  EXTRA_BUILD_FLAGS := rebuild
endif

ifneq (,$(filter rc beta-rc,$(TARGET_BRANCH)))
  EXTRA_BUILD_FLAGS := rebuild
endif

.PHONY: check-tag
check-tag:
ifeq ($(BUILD_TYPE),TAG)
	@echo "Checking if tag matches version.txt..."
	@if grep --quiet "$(BRANCH_NAME)" version.txt; then \
		echo "Perfect - Tag and Version is matching"; \
	else \
		echo "There is some mismatch between Tag and Version"; \
		exit 1; \
	fi
endif

# ========================= Build Images =============================

$(BUILD_DIR):
	mkdir -p $@

# Build common base image
.PHONY: build-common
build-common:
	@echo "==> Building common base image..."
	@$(MAKE) -C $(COMMON_FOLDER) http_proxy=$(http_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE ==> Building common base image"

# Build targets for each service folder
.PHONY: $(IMAGE_FOLDERS)
$(IMAGE_FOLDERS):
	@echo "====> Building folder $@..."
	@$(MAKE) -C $@ BUILD_DIR=$(BUILD_DIR) http_proxy=$(http_proxy) https_proxy=$(https_proxy) no_proxy=$(no_proxy) $(EXTRA_BUILD_FLAGS)
	@echo "DONE ====> Building folder $@"

# Dependency on the common base image
autocalibration controller manager mapping cluster_analytics: build-common

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

# Parallel wrapper for experimental images (mapping and cluster_analytics)
.PHONY: build-experimental-images
build-experimental-images: $(BUILD_DIR)
	@echo "==> Running parallel builds of experimental folders: mapping cluster_analytics"
	@set -e; trap 'grep --color=auto -i -r --include="*.log" "^error" $(BUILD_DIR) || true' EXIT; \
	$(MAKE) -j$(JOBS) mapping cluster_analytics
	@echo "DONE ==> Parallel builds of experimental folders: mapping cluster_analytics"

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
	for dir in $(IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir list-dependencies; \
	done
	@-find . -type f -name '*-apt-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-apt-deps.txt
	@-find . -type f -name '*-pip-deps.txt' -exec cat {} + | sort | uniq > $(BUILD_DIR)/scenescape-all-pip-deps.txt
	@echo "The following dependency lists have been generated:"
	@find $(BUILD_DIR) -name '*-deps.txt' -print
	@echo "DONE ==> Listing dependencies for all microservices"

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
	@$(MAKE) -C model_installer install-models

# =========================== Run Tests ==============================

.PHONY: setup_tests
setup_tests: build-all-images init-secrets .env
	@echo "Setting up test environment..."
	for dir in $(TEST_IMAGE_FOLDERS); do \
		$(MAKE) -C $$dir test-build; \
	done
	mkdir -p $(TEST_DATA_FOLDER)/netvlad_models
	@echo "DONE ==> Setting up test environment"

.PHONY: run_tests
run_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running tests..."
	$(MAKE) --trace -C tests -j 1 SECRETSDIR=$(PWD)/manager/secrets || (echo "Tests failed" && exit 1)
	@echo "DONE ==> Running tests"

.PHONY: run_performance_tests
run_performance_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running performance tests..."
	$(MAKE) -C tests performance_tests -j 1 SUPASS=$(SUPASS) || (echo "Performance tests failed" && exit 1)
	@echo "DONE ==> Running performance tests"

.PHONY: run_stability_tests
run_stability_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running stability tests..."
ifeq ($(BUILD_TYPE),DAILY)
	@$(MAKE) -C tests system-stability SUPASS=$(SUPASS) HOURS=4
else
	@$(MAKE) -C tests system-stability SUPASS=$(SUPASS)
endif
	@echo "DONE ==> Running stability tests"

.PHONY: run_standard_tests
run_standard_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running standard tests..."
	$(MAKE) -C tests standard-tests -j 1 SUPASS=$(SUPASS) || (echo "Standard tests failed" && exit 1)
	@echo "DONE ==> Running standard tests"

.PHONY: run_functional_tests
run_functional_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running functional tests..."
	$(MAKE) -C tests functional-tests SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k || (echo "Functional tests failed" && exit 1)
	@echo "DONE ==> Running functional tests"

.PHONY: run_non_functional_tests
run_non_functional_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running non-functional tests..."
	$(MAKE) -C tests non-functional-tests SUPASS=$(SUPASS) -k || (echo "Non-functional tests failed" && exit 1)
	@echo "DONE ==> Running non-functional tests"

.PHONY: run_metric_tests
run_metric_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running metric tests..."
	$(MAKE) -C tests metric-tests -j $(NPROCS) SUPASS=$(SUPASS) -k || (echo "Metric tests failed" && exit 1)
	@echo "DONE ==> Running metric tests"

.PHONY: run_ui_tests
run_ui_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running UI tests..."
	$(MAKE) -C tests ui-tests SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k || (echo "UI tests failed" && exit 1)
	@echo "DONE ==> Running UI tests"

.PHONY: run_unit_tests
run_unit_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running unit tests..."
	$(MAKE) -C tests unit-tests -j $(NPROCS) SUPASS=$(SUPASS) -k || (echo "Unit tests failed" && exit 1)
	@echo "DONE ==> Running unit tests"

.PHONY: run_basic_acceptance_tests
run_basic_acceptance_tests: setup_tests
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS);
	@echo "Running basic acceptance tests..."
	$(MAKE) --trace -C tests basic-acceptance-tests -j 1 SUPASS=$(SUPASS) || (echo "Basic acceptance tests failed" && exit 1)
	@echo "DONE ==> Running basic acceptance tests"

# Temp K8s BAT target
.PHONY: run_basic_acceptance_tests_k8s
run_basic_acceptance_tests_k8s: setup_tests
	@echo "Running basic acceptance tests..."
	$(MAKE) --trace -C tests basic-acceptance-tests-k8s -j 1 SUPASS=$(SUPASS) || (echo "Basic acceptance tests failed" && exit 1)
	@echo "DONE ==> Running basic acceptance tests"

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
	@$(MAKE) --trace -C tests python-indent-check -j 1 || (echo "Python indentation check failed" && exit 1)
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

# =========================== Coverity ==============================
.PHONY: build-coverity
build-coverity:
	@make -C scene_common/src/fast_geometry/ || (echo "scene_common/fast_geometry build failed" && exit 1)
	@export OpenCV_DIR=$${OpenCV_DIR:-$$(pkg-config --variable=pc_path opencv4 | cut -d':' -f1)} && cd controller/src/robot_vision && python3 setup.py bdist_wheel || (echo "robot vision build failed" && exit 1)
# ===================== Docker Compose Demo ==========================

.PHONY: convert-dls-videos
convert-dls-videos:
	$(MAKE) $(DLSTREAMER_SAMPLE_VIDEOS); \

.PHONY: init-sample-data
init-sample-data: convert-dls-videos
	@echo "Initializing sample data volume..."
	@docker volume create $(COMPOSE_PROJECT_NAME)_vol-sample-data 2>/dev/null || true
	@echo "Setting up volume permissions..."
	@docker run --rm -v $(COMPOSE_PROJECT_NAME)_vol-sample-data:/dest alpine:3.23 chown $(shell id -u):$(shell id -g) /dest
	@echo "Copying files from $(PWD)/sample_data to volume..."
	@if [ -d "$(PWD)/sample_data" ]; then \
		docker run --rm \
			-v $(PWD)/sample_data:/source:ro \
			-v $(COMPOSE_PROJECT_NAME)_vol-sample-data:/dest \
			--user $(shell id -u):$(shell id -g) \
			alpine:3.23 \
			sh -c "echo 'Copying files...'; cp -rv /source/* /dest/ && echo 'Copy completed successfully' || echo 'Copy failed'; echo '';"; \
	else \
		echo "WARNING: Source directory $(PWD)/sample_data does not exist!"; \
		exit 1; \
	fi
	@echo "Sample data volume initialized."

# Helper target to start demo with compose
define start_demo
	@$(MAKE) docker-compose.yml
	@$(MAKE) .env
	@if [ -z "$$SUPASS" ]; then \
		echo "Please set the SUPASS environment variable before starting the demo for the first time."; \
		echo "The SUPASS environment variable is the super user password for logging into Intel® SceneScape."; \
		exit 1; \
	fi
	docker compose $(1) up -d
	@echo ""
	@echo "To stop SceneScape, type:"
	@echo "    docker compose $(1) down"
endef

.PHONY: demo
demo: build-core init-sample-data
	$(call start_demo,)

.PHONY: demo-all
demo-all: build-all init-sample-data
	$(call start_demo,--profile experimental)

.PHONY: demo-k8s
demo-k8s:
	$(MAKE) -C kubernetes DEPLOYMENT_TEST=$(DEPLOYMENT_TEST) DEMO_K8S_MODE=$(DEMO_K8S_MODE)

.PHONY: docker-compose.yml
docker-compose.yml:
	cp $(DLSTREAMER_DOCKER_COMPOSE_FILE) $@;

$(DLSTREAMER_SAMPLE_VIDEOS): ./dlstreamer-pipeline-server/convert_video_to_ts.sh
	@echo "==> Converting sample videos for DLStreamer..."
	@./dlstreamer-pipeline-server/convert_video_to_ts.sh
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
	chmod go-rwx $(SECRETSDIR)

.PHONY: $(SECRETSDIR) certificates
certificates:
	@make -C ./tools/certificates CERTPASS=$$(openssl rand -base64 12) SECRETSDIR=$(SECRETSDIR) CERTDOMAIN=$(CERTDOMAIN)

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
	@backup_dir=${PWD}/scenescape_vol-backup; \
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
	@if [ -d "${PWD}/scenescape_vol-backup" ]; then \
		echo " - Removing directory: ${PWD}/scenescape_vol-backup"; \
		rm -rf "${PWD}/scenescape_vol-backup"; \
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
