# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
SECRETSDIR ?= $(PWD)/../manager/secrets

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

define set-prefix
    $(eval PREFIX = $(if $(DLS),dlstreamer/,))
endef

# For DLStreamer tests, run the target with DLS=1

# Not sorted alphabetically on purpose
tests: \
  basic-acceptance-tests \
  standard-tests \

release-tests: \
  additional-floor-plans \
  camera-deletion \
  different-formats-maps \
  live-view-button \
  non-functional-tests \
  scene-details \
  randomly-failing-tests \
  reid-performance-degradation \

# moved from release-tests to broken-tests:
#  3d-ui-calibration-points

broken-tests: \
  auto-calibration \
  3d-camera-control-panel \
  april-tag-setup \
  rtsp-stream \
  views-unit \
  mqtt-sensor-roi \
  mqtt-slow-sensor-roi \
  orphaned-sensor \
  sensors-send-events \
  delete-roi-mqtt \
  delete-tripwire-mqtt \
  geospatial-ingest-publish \
  delete-sensor-mqtt \
  delete-sensor-scene \
  delete-sensors \
  restricted-media-access \
  sensor-area \
  sensor-location \
  calibrate-all-sensor-types \
  manual-camera-calibration \
  camera-perspective \
  camera-status \
  superuser-crud-operations \
  calibrate-camera-3d-ui-2d-ui \
  vdms-similarity-search \
  mqtt-large-messages \
  out-of-box-no-ntp \
  bounding-box \
  child-scenes \
  3d-ui-calibration-points \

randomly-failing-tests: \
  3d-scene-control-panel \

# Not sorted alphabetically on purpose
basic-acceptance-tests: \
  deploy \
  infra-tests \
  geometry-conformance \
  metric-tests \
  out-of-box \
  mqtt-roi \
  mqtt-tripwire \
  unit-tests \

# FIXME: run functional tests in parallel
standard-tests: \
  _functional-tests \
  _ui-tests \
  show-telemetry-button \
  upload-only-3d-glb-files \

functional-tests:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k

_functional-tests: \
  add-orphaned-cameras \
  api-large-strings \
  mqtt-auth \
  mqtt-cert \
  rest-test \
  reid-unique-count \
  scene-import \

# Moved to broken tests:
#   mqtt-large-messages
#   out-of-box-no-ntp
#   bounding-box
#   child-scenes

non-functional-tests:
	$(MAKE) -Otarget _$@ SUPASS=$(SUPASS) -k

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
	$(MAKE) -Otarget _$@ SUPASS=$(SUPASS) -k

_ui-tests: \
  add-delete-3d-object \
  camera-intrinsics \
  object-crud \
  persistence \
  scenes-summary \
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
  scene-unit \
  scenescape-unit \
  schema-unit \
  timestamp-unit \
  transform-unit \

include Makefile.sscape Makefile.functional Makefile.perf \
        Makefile.external_models Makefile.reports Makefile.infra Makefile.user_interface Makefile.metric

# Recipes below must be in alphabetical order

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
	  ; make init-sample-data \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

system-stability: # NEX-T10411
	$(call set-prefix)
	$(eval HOURS ?= 24)
	$(call common-recipe, $(COMPOSE)/$(PREFIX)broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/$(PREFIX)retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/system/stability/tc_sscape_stability.py --hours=$(HOURS),'pgserver web scene',true)
