# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL=/bin/bash
.SHELLFLAGS=-o pipefail -c
IMAGE=scenescape
BASE_IMAGE := $(IMAGE)-manager-test
VERSION := $(shell cat ../version.txt)

TEST_DATA=test_data
TESTS_DIRECTORY=tests
COVERAGE_CMD=coverage run
SELENIUM_TEST_COVERAGE_ARGS=-m -a --omit */site-packages/*,*/dist-packages/*
SELENIUM_TEST_COVERAGE_CMD=$(COVERAGE_CMD) $(SELENIUM_TEST_COVERAGE_ARGS)
COVERAGE_DATA_FILE=$(TESTS_DIRECTORY)/sscape_tests/.coverage_unit_$@
COMBINED_COVERAGE_DATA_FILE=.coverage_combine
SELENIUM_COMBINED_FILE=tests/ui/$(COMBINED_COVERAGE_DATA_FILE)
UNIT_TESTS_COMBINED_FILE=$(TESTS_DIRECTORY)/sscape_tests/$(COMBINED_COVERAGE_DATA_FILE)
COVERAGE_RC_FILE=tests/config.coveragerc
UNIT_TEST_COVERAGE_ARGS=--rcfile=$(COVERAGE_RC_FILE) -a
UNIT_TEST_COVERAGE_CMD=COVERAGE_FILE=$(COVERAGE_DATA_FILE) $(COVERAGE_CMD) $(UNIT_TEST_COVERAGE_ARGS)
GENERATE_JUNITXML=-o junit_logging=all --junitxml tests/reports/test_reports/$@.xml
GENERATE_JUNITXML_UNITTEST=-o junit_logging=all --junitxml tests/reports/test_reports/unit-tests/$@.xml
NPROCS?=$(shell echo $(shell grep -c ^processor /proc/cpuinfo)/3 | bc)
COMPOSE=tests/compose
EXAMPLEDB=tests/testdb.tar.bz2

RANDPASS:=$(shell openssl rand -base64 12)
export SUPASS?=$(RANDPASS)

# ---------------------------------------------------------------------------
# Standalone docker run helpers.
#
# Used by Makefile.perf, Makefile.metric, and Makefile.reports for targets
# that invoke a single container without a compose stack.
#
# DOCKER_RUN_MANAGER  — scenescape-manager-test image (uid-only, userns=host)
# DOCKER_RUN_CONTROLLER — scenescape-controller-test image (uid:gid)
# ---------------------------------------------------------------------------
_UID := $(shell id -u)
_GID := $(shell id -g)

_DOCKER_FLAGS = --rm --privileged --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE --workdir=/workspace
_DOCKER_MOUNTS = --volume="$(CURDIR)/..:/workspace:rw" --volume="scenescape_vol-models:/opt/intel/openvino/deployment_tools/intel_models:rw" --volume="scenescape_vol-sample-data:/home/scenescape/SceneScape/sample_data:rw" --volume="$(CURDIR)/../manager/secrets:/run/secrets:ro"
_DOCKER_ENV = -e PYTHONPATH=/workspace -e SECRETSDIR=/run/secrets

DOCKER_RUN_MANAGER = docker run $(_DOCKER_FLAGS) -u $(_UID) --userns=host $(_DOCKER_MOUNTS) --volume="$(CURDIR)/../manager/secrets:/home/scenescape/SceneScape/manager/secrets:ro" --volume="$(CURDIR)/../manager/secrets/django/secrets.py:/home/scenescape/SceneScape/manager/secrets.py:ro" $(_DOCKER_ENV) $(IMAGE)-manager-test:$(VERSION)
DOCKER_RUN_CONTROLLER = docker run $(_DOCKER_FLAGS) -u $(_UID):$(_GID) $(_DOCKER_MOUNTS) $(_DOCKER_ENV) $(IMAGE)-controller-test:$(VERSION)

# ---------------------------------------------------------------------------
# pytest-recipe: invoke the tests/.venv pytest with -k selection.
#
# Usage:  $(call pytest-recipe, test_id)
# ---------------------------------------------------------------------------
define pytest-recipe =
	$(eval TEST_ID := $1)
	$(eval LOGFILE := $(TEST_DATA)/smoke/$@-$(shell date -u +"%F-%T").log)
	@set -e \
	  ; echo "RUNNING TEST $@" \
	  ; mkdir -p $(shell dirname $(LOGFILE)) reports/test_reports \
	  ; SECRETSDIR=$(SECRETSDIR) SUPASS=$(SUPASS) \
	    .venv/bin/pytest \
	    -k "$(TEST_ID)" -v \
	    --junitxml reports/test_reports/$@.xml \
	    2>&1 | tee -ia $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo "END TEST $@"
endef

# Create the pytest virtualenv if it does not already exist.
# Called automatically by functional-tests, unit-tests, and ui-tests groups.
.PHONY: setup-pytest
setup-pytest:
	@if [ ! -d "$(CURDIR)/.venv" ]; then \
		python3 -m venv $(CURDIR)/.venv; \
		$(CURDIR)/.venv/bin/pip install -q --upgrade pip; \
		$(CURDIR)/.venv/bin/pip install -q -r $(CURDIR)/requirements.txt; \
	fi

# Not sorted alphabetically on purpose
tests: \
  basic-acceptance-tests \
  standard-tests \

release-tests: \
  camera-deletion \
  different-formats-maps \
  live-view-button \
  non-functional-tests \
  scene-details \
  reid-performance-degradation \

broken-features:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k

# tests that are working, but feature is broken
_broken-features: \
  calibrate-camera-3d-ui-2d-ui \
  visibility-regulated \

broken-tests: \
  3d-ui-calibration-points \
  geospatial-ingest-publish \
  delete-sensor-mqtt-api \
  scenes-summary-api \
  reid-performance-degradation \
  auto-calibration-ui \

randomly-failing-tests: \
  distance-msoce \
  reid-data-flow \
  reid-semantic-unique-count \
  reid-unique-count \

# Not sorted alphabetically on purpose
basic-acceptance-tests: \
  pipeline-runner-people \
  pipeline-runner-vehicles \
  out-of-box \
  geometry-conformance \
  metric-tests \
  bounding-box \
  mqtt-roi \
  mqtt-tripwire \
  unit-tests \
  auto-calibration-api \
  openapi-validation \

# Temp K8s BAT target
# Not sorted alphabetically on purpose
basic-acceptance-tests-k8s: \
  idc-error-metric \
  msoce-metric \
  velocity-metric \

# FIXME: run functional tests in parallel
standard-tests: \
  _functional-tests \
  _ui-tests \

functional-tests: setup-pytest
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k

_functional-tests: \
  out-of-box \
  out-of-box-no-ntp \
  geometry-conformance \
  auto-calibration-api \
  add-delete-3d-object-api \
  add-orphaned-cameras \
  api-large-strings \
  calibrate-all-sensor-types-api \
  camera-deletion-api \
  camera-intrinsics-api \
  camera-intrinsics \
  child-scenes \
  delete-sensor-scene-api \
  delete-sensors-api \
  different-formats-maps-api \
  manual-camera-calibration-api \
  mqtt-auth \
  mqtt-cert \
  mqtt-roi \
  mqtt-sensor-roi \
  mqtt-slow-sensor-roi \
  mqtt-tripwire \
  object-crud-api \
  orphaned-sensor \
  persistence-api \
  rest-test \
  scene-details-api \
  scene-import-api \
  scene-import-json \
  sensor-area-api \
  sensor-location-api \
  sensor-scene-api \
  sensors-send-events \
  superuser-crud-operations-api \
  upload-3d-glb-file-api \
  upload-only-3d-glb-files-api \
  vdms-similarity-search \
  visibility-unregulated \
  visibility-none \

non-functional-tests:
	$(MAKE) -Otarget _$@ SUPASS=$(SUPASS) -k

_non-functional-tests: \
  build-time \
  openapi-validation \

metric-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_metric-tests: \
  idc-error-metric \
  velocity-metric \
  msoce-metric \

ui-tests: setup-pytest
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k

_ui-tests: \
  show-telemetry-button \
  upload-only-3d-glb-files \
  add-delete-3d-object \
  bounding-box \
  calibrate-all-sensor-types \
  camera-deletion \
  camera-perspective \
  delete-roi-mqtt \
  delete-sensor-mqtt \
  delete-sensor-scene \
  delete-sensors \
  camera-status \
  delete-tripwire-mqtt \
  different-formats-maps \
  manual-camera-calibration \
  object-crud \
  restricted-media-access \
  persistence \
  live-view-button \
  scene-details \
  scene-import \
  scenes-summary \
  sensor-area \
  sensor-location \
  sensor-scene \
  superuser-crud-operations \
  upload-3d-glb-file \
  view-3d-glb-file \
  3d-scene-control-panel \
  3d-camera-control-panel \
  timestamp-format \

unit-tests: setup-pytest
	$(MAKE) -Otarget -j $(NPROCS) _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k

_unit-tests: \
  account-security-unit \
  autocamcalib-unit \
  cam-unit \
  geometry-unit \
  geospatial-unit \
  mapping-unit \
  markerless-unit \
  robot-vision-unit \
  scene-unit \
  scenescape-unit \
  schema-unit \
  singleton-sensor-unit \
  timestamp-unit \
  transform-unit \
  uuid-manager-unit \
  vdms-adapter-unit \
  views-unit \

include Makefile.sscape Makefile.functional Makefile.perf \
        Makefile.reports Makefile.user_interface Makefile.metric

# Recipes below must be in alphabetical order
malformed-json:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) WAITFORCONTAINERS="pgserver scene" tests/security/malformed_data/test_malformed_json.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

build-time: # NEX-T12520
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
		; echo RUNNING TEST $@ \
		; cd $(CURDIR)/.. \
		; mkdir -p $(shell dirname $(LOGFILE)) \
		; python3 tests/scripts/build-time.py \
			--time-limit 600 \
			--build-cmd "make build-core" \
			--test-name "NEX-T12520" \
			2>&1 | tee -i $(LOGFILE) \
		; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
		; echo END TEST $@

system-stability: setup-pytest # NEX-T10411
	$(eval HOURS ?= 24)
	$(eval LOGFILE := $(TEST_DATA)/smoke/$@-$(shell date -u +"%F-%T").log)
	@set -e \
	  ; echo "RUNNING TEST $@" \
	  ; mkdir -p $(shell dirname $(LOGFILE)) reports/test_reports \
	  ; SECRETSDIR=$(SECRETSDIR) SUPASS=$(SUPASS) STABILITY_HOURS=$(HOURS) \
	    .venv/bin/pytest \
	    -k "system_stability" -v \
	    --junitxml reports/test_reports/$@.xml \
	    2>&1 | tee -ia $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo "END TEST $@"

python-indent-check: # NEX-T10448
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/checkIndent 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE)

openapi-validation: # NEX-T10572
	@cd ../docs/user-guide/api-docs/ \
	; npm install --save-dev swagger-cli@2.0.0 \
	; npx swagger-cli validate api.yaml
