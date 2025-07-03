# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

SHELL=/bin/bash
.SHELLFLAGS=-o pipefail -c
IMAGE=scenescape
BASE_IMAGE=$(IMAGE)-manager-test
VERSION:=$(shell cat ../version.txt)

TEST_DATA=test_data
TESTS_DIRECTORY=tests
COVERAGE_CMD=coverage run
SELENIUM_TEST_COVERAGE_ARGS=-m -a --omit */dist-packages/*
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
SECRETSDIR ?= $(PWD)/manager/secrets

ifeq ($(KUBERNETES),1)
    RUNTEST=tests/kubernetes/runtest
else
    RUNTEST=tests/runtest
endif

RANDPASS:=$(shell openssl rand -base64 12)
export SUPASS?=$(RANDPASS)

define common-recipe =
	$(eval YML=$1)
	$(eval TEST_SCRIPT=$2)
	$(eval CONTAINERS=$3)
	$(eval REQUIRE_SUPASS=$4)
	$(eval AUTH_USER=$(if $5, --auth=$(strip $5), ))
	$(eval TEST_IMAGE=$7)
	$(eval DBROOT=$(TEST_DATA)/db_$@)
	$(eval LOGFILE=$(TEST_DATA)/smoke/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; if [ x$(REQUIRE_SUPASS) = xtrue ] ; then \
	      EXTRAS="--password=$(SUPASS)"; \
	  fi \
	  ; if [ ! -z "$(AUTH_USER)" ]; then \
	      EXTRAS="$${EXTRAS} $(AUTH_USER)"; \
	  fi \
	  ; echo RUNNING COMMON TEST $@ \
	  ; cd .. \
	  ; EXAMPLEDB=$(EXAMPLEDB) \
	  ; if [ -n "$6" ] ; then \
	        EXAMPLEDB=$6 \
	  ; fi \
	  ; if [ -z "$(BASE_IMAGE)" ]; then \
	        BASE_IMAGE=$(IMAGE)-manager-test \
	  ; fi \
	  ; if [ -n "$(TEST_IMAGE)" ]; then \
	        BASE_IMAGE=$(TEST_IMAGE) \
	  ; fi \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; env SECRETSDIR=$(SECRETSDIR) IMAGE=$(BASE_IMAGE):$(VERSION) \
	      DBROOT=$(DBROOT) EXAMPLEDB=$${EXAMPLEDB} LOGSFORCONTAINER=$(CONTAINERS) \
	      WAITFORCONTAINERS=$(CONTAINERS) \
	      NO_PROXY=$(NO_PROXY),.scenescape.intel.com,.scenescape \
	      no_proxy=$(no_proxy),.scenescape.intel.com,.scenescape \
	      $(RUNTEST) $(YML) pytest -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
	                                  $${EXTRAS} 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; if [ `grep -c "Traceback" $(LOGFILE)` -ne 0 ] ; then echo "Found error in $@ !"; fi \
	  ; echo END TEST $@
endef

# Not sorted alphabetically on purpose
tests: \
  basic-acceptance-tests \
  standard-tests \

release-tests: \
  3d-ui-calibration-points \
  additional-floor-plans \
  calibrate-all-sensor-types \
  camera-deletion \
  camera-perspective \
  camera-status \
  check-openvino-version \
  different-formats-maps \
  live-view-button \
  manual-camera-calibration \
  reid-unique-count \
  reid-performance-degradation \
  scene-details \
  superuser-crud-operations \
  calibrate-camera-3d-ui-2d-ui \
  randomly-failing-tests \

broken-tests: \
  3d-camera-control-panel \
  april-tag-setup \
  rtsp-stream \
  detector-unit \
  views-unit \
  mqtt-sensor-roi \
  mqtt-slow-sensor-roi \
  orphaned-sensor \
  sensors-send-events \

randomly-failing-tests: \
  3d-scene-control-panel \

# Not sorted alphabetically on purpose
basic-acceptance-tests: \
  deploy \
  infra-tests \
  geometry-conformance \

# FIXME: run functional tests in parallel
standard-tests: \
  _functional-tests \
  non-functional-tests \
  metric-tests \
  ui-tests \
  show-telemetry-button \
  upload-only-3d-glb-files \
  unit-tests \

functional-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k

_functional-tests: \
  auto-calibration \
  add-orphaned-cameras \
  api-large-strings \
  bounding-box \
  delete-roi-mqtt \
  delete-tripwire-mqtt \
  geospatial-ingest-publish \
  mqtt-auth \
  mqtt-cert \
  mqtt-large-messages \
  mqtt-roi \
  mqtt-tripwire \
  out-of-box-no-ntp \
  out-of-box \
  percebro-3d-msgs \
  rest-test \
  child-scenes \
  vdms-similarity-search \

non-functional-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_non-functional-tests: \
  build-time \

metric-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_metric-tests: \
  idc-error-metric \
  velocity-metric \
  distance-msoce \
  msoce-metric \

ui-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_ui-tests: \
  add-delete-3d-object \
  camera-intrinsics \
  delete-sensor-mqtt \
  delete-sensor-scene \
  delete-sensors \
  object-crud \
  persistence \
  restricted-media-access \
  scenes-summary \
  sensor-area \
  sensor-location \
  sensor-scene \
  upload-3d-glb-file \
  view-3d-glb-file \

unit-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_unit-tests: \
  autocamcalib-unit \
  geometry-unit \
  geospatial-unit \
  markerless-unit \
  percebro-unit \
  realsense-unit \
  scene-unit \
  scenescape-unit \
  schema-unit \
  timestamp-unit \
  transform-unit \
  videosource-unit \

include Makefile.sscape Makefile.functional Makefile.percebro Makefile.perf \
        Makefile.external_models Makefile.reports Makefile.infra Makefile.user_interface Makefile.metric

# Recipes below must be in alphabetical order

check-openvino-version: # NEX-T10407
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; tools/scenescape-start tests/check-openvino-version.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

malformed-json:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) WAITFORCONTAINERS="pgserver scene" tests/security/malformed_data/test_malformed_json.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

mqtt-large-messages: # NEX-T10462
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(TEST_DATA) \
	  ; tests/mqtt-large-messages.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

native-tracker:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; tools/scenescape-start controller/tools/tracker/tracker-test controller/tools/tracker/standard-tests.json | tee -i $(LOGFILE) \
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
	  --clean-cmd "make clean-all && docker builder prune -af" \
	  --build-cmd "make FOLDERS=autocalibration broker controller manager model_installer" \
	  --test-name "NEX-T12520" \
	  2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE)

deploy: # NEX-T10422
	$(eval LOGFILE=$(TEST_DATA)/code_build/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; SKIP_BRINGUP=1 REQUIRED_FPS=0 CERTPASS=$$(openssl rand -base64 12) SKIPYML=1 SUPASS=$(SUPASS) ./deploy.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

system-stability: # NEX-T10411
	$(eval HOURS ?= 24)
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/system/stability/tc_sscape_stability.py --hours=$(HOURS),'pgserver web scene',true)

v4l-resolution: # NEX-T10513
	../tools/scenescape-start ./v4l-resolution.py 0
