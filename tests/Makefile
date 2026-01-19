# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
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
				PROJECT=$(PROJECT) CLEANUP_MODE=$(CLEANUP_MODE) SKIP_INIT=$(SKIP_INIT) \
				WAITFORCONTAINERS=$(CONTAINERS) \
				NO_PROXY=$(NO_PROXY),.scenescape.intel.com,.scenescape \
				no_proxy=$(no_proxy),.scenescape.intel.com,.scenescape \
				$(RUNTEST) $(YML) pytest -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
																		$${EXTRAS} 2>&1 | tee -ia $(LOGFILE) \
		; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
		; if [ `grep -c "Traceback" $(LOGFILE)` -ne 0 ] ; then echo "Found error in $@ !"; fi \
		; echo END TEST $@
endef

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
	reid-unique-count \
	reid-performance-degradation \

broken-features:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
# tests that are working, but feature is broken
_broken-features: \
	scene-import \

broken-tests: \
	3d-ui-calibration-points \
	distance-msoce \
	geospatial-ingest-publish \
	delete-sensor-mqtt-api \
	scenes-summary-api \

randomly-failing-tests:

# Not sorted alphabetically on purpose
basic-acceptance-tests: \
	geometry-conformance \
	metric-tests \
	out-of-box \
	out-of-box-no-ntp \
	mqtt-roi \
	mqtt-tripwire \
	unit-tests \
	auto-calibration-api \

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
	show-telemetry-button \
	upload-only-3d-glb-files \

functional-all:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-all: functional-scenes functional-sensors functional-cameras functional-mqtt functional-objects functional-generic

functional-scenes:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-scenes: \
	scene-details-api \
	scene-import-api \
	scene-import-json \
	child-scenes \
	persistence-api \

functional-sensors:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-sensors: \
	calibrate-all-sensor-types-api \
	delete-sensor-scene-api \
	delete-sensors-api \
	sensor-area-api \
	sensor-location-api \
	sensor-scene-api \
	sensors-send-events \
	orphaned-sensor \
	different-formats-maps-api \

functional-cameras:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-cameras: \
	auto-calibration-api \
	add-orphaned-cameras \
	camera-deletion-api \
	camera-intrinsics-api \
	camera-intrinsics \
	manual-camera-calibration-api \

functional-mqtt:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-mqtt: \
	mqtt-sensor-roi \
	mqtt-slow-sensor-roi \
	mqtt-auth \
	mqtt-cert \
	mqtt-roi \
	mqtt-tripwire \

functional-objects:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-objects: \
	add-delete-3d-object-api \
	object-crud-api \
	upload-3d-glb-file-api \
	upload-only-3d-glb-files-api \

functional-generic:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) BASE_IMAGE=$(BASE_IMAGE) -k
_functional-generic: \
	out-of-box \
	out-of-box-no-ntp \
	geometry-conformance \
	api-large-strings \
	rest-test \
	superuser-crud-operations-api \
	vdms-similarity-search \

non-functional-tests:
	$(MAKE) -Otarget _$@ SUPASS=$(SUPASS) -k
_non-functional-tests: \
	build-time \

metric-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k
_metric-tests: \
	idc-error-metric \
	velocity-metric \
	msoce-metric \

ui-all:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-all: ui-scenes ui-sensors ui-cameras ui-mqtt ui-objects ui-generic

ui-scenes:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-scenes: \
	3d-scene-control-panel \
	scenes-summary \
	persistence \

ui-sensors:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-sensors: \
	calibrate-all-sensor-types \
	delete-sensor-scene \
	delete-sensors \
	sensor-area \
	sensor-location \
	sensor-scene \

ui-cameras:
$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-cameras: \
	3d-camera-control-panel \
	camera-perspective \
	camera-status \
	manual-camera-calibration \
	auto-calibration-ui \
	calibrate-camera-3d-ui-2d-ui \

ui-mqtt:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-mqtt: \
	delete-sensor-mqtt \
	delete-roi-mqtt \
	delete-tripwire-mqtt \

ui-objects:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-objects: \
	add-delete-3d-object \
	bounding-box \
	object-crud \
	upload-3d-glb-file \
	view-3d-glb-file \

ui-generic:
	$(MAKE) -Otarget _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_ui-generic: \
	restricted-media-access \
	superuser-crud-operations \

unit-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SECRETSDIR=$(PWD)/manager/secrets SUPASS=$(SUPASS) -k
_unit-tests: \
	account-security-unit \
	autocamcalib-unit \
	cam-unit \
	geometry-unit \
	geospatial-unit \
	markerless-unit \
	robot-vision-unit \
	scene-unit \
	scenescape-unit \
	schema-unit \
	singleton-sensor-unit \
	timestamp-unit \
	transform-unit \
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
			--build-cmd "make" \
			--test-name "NEX-T12520" \
			2>&1 | tee -i $(LOGFILE) \
		; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
		; echo END TEST $@

system-stability: # NEX-T10411
	$(eval HOURS ?= 24)
	$(call common-recipe, $(COMPOSE)/dlstreamer/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/dlstreamer/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/system/stability/tc_sscape_stability.py --hours=$(HOURS),'pgserver web scene',true)

python-indent-check: # NEX-T10448
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
		; cd .. \
		; mkdir -p $(shell dirname $(LOGFILE)) \
		; tests/scripts/checkIndent 2>&1 | tee -i $(LOGFILE) \
		; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE)
