# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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

ifeq ($(KUBERNETES),1)
    RUNTEST=tests/kubernetes/runtest
else
    RUNTEST=tests/runtest
endif

RANDPASS:=$(shell openssl rand -base64 12)
export SUPASS?=$(RANDPASS)

define selenium-recipe =
	$(eval YML=$1)
	$(eval TEST_SCRIPT=$2)
	$(eval CONTAINERS=$3)
	$(eval DBROOT=$(TEST_DATA)/db_$@)
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	$(eval SELENIUM_COVERAGE_DATA_FILE=$(TESTS_DIRECTORY)/ui/.coverage_$@)
	@set -ex \
	  ; echo RUNNING SELENIUM TEST $@ \
	  ; cd .. \
	  ; EXAMPLEDB=$(EXAMPLEDB) \
	  ; if [ -n "$4" ] ; then \
	        EXAMPLEDB=$4 \
	  ; fi \
	  ; echo $(EXAMPLEDB) \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE_INTERFACE):$(VERSION) \
	      DBROOT=$(DBROOT) EXAMPLEDB=$${EXAMPLEDB} LOG=$(LOGFILE) LOGSFORCONTAINER="scene" \
	      TEST_SCRIPT=$(TEST_SCRIPT) \
	      WAITFORCONTAINERS=$(CONTAINERS) \
	      $(RUNTEST) $(YML) $(SELENIUM_TEST_COVERAGE_CMD) \
	      --data-file=$(SELENIUM_COVERAGE_DATA_FILE) pytest -s $(GENERATE_JUNITXML) \
	      $(TEST_SCRIPT) --password=$(SUPASS) 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; if [ `grep -c "Traceback" $(LOGFILE)` -ne 0 ] ; then echo "Found error in $@ !"; exit 1; fi \
	  ; echo END TEST $@
endef

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
	  ; BASE_IMAGE=$(BASE_IMAGE) \
	  ; if [ -n "$(TEST_IMAGE)" ]; then \
	        BASE_IMAGE=$(TEST_IMAGE) \
	  ; fi \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE_INTERFACE):$(VERSION) \
	      DBROOT=$(DBROOT) EXAMPLEDB=$${EXAMPLEDB} LOGSFORCONTAINER=$(CONTAINERS) \
	      WAITFORCONTAINERS=$(CONTAINERS) \
	      NO_PROXY=$(NO_PROXY),.scenescape.intel.com,.scenescape \
	      no_proxy=$(no_proxy),.scenescape.intel.com,.scenescape \
	      $(RUNTEST) $(YML) pytest -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
	                                  $${EXTRAS} 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; if [ `grep -c "Traceback" $(LOGFILE)` -ne 0 ] ; then echo "Found error in $@ !"; exit 1; fi \
	  ; echo END TEST $@
endef

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
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tools/scenescape-start --image ${IMAGE}-controller pytest -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
	                                   $${METRIC} $${THRESHOLD} $${FRAME_RATE} \
	                                   -o junit_suite_name=$(TEST_SUITE) | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
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
  auto-calibration \
  metric-tests \
  mqtt-large-messages \
  rtsp-stream \
  scene-performance-full \
  sscape-unit \
  vdms-similarity-search \
  videosource-unit \

randomly-failing-tests: \
  3d-scene-control-panel \

# Not sorted alphabetically on purpose
basic-acceptance-tests: \
  newlines-check \
  python-indent-check \
  deploy \
  infra-tests \
  geometry-conformance \

standard-tests: \
  functional-tests \
  ui-tests \
  unit-tests \

functional-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_functional-tests: \
  add-orphaned-cameras \
  api-large-strings \
  bounding-box \
  child-scenes \
  delete-roi-mqtt \
  delete-tripwire-mqtt \
  geospatial-ingest-publish \
  mqtt-auth \
  mqtt-cert \
  mqtt-roi \
  mqtt-sensor-roi \
  mqtt-slow-sensor-roi \
  mqtt-tripwire \
  orphaned-sensor \
  out-of-box \
  out-of-box-no-ntp \
  percebro-3d-msgs \
  rest-test \
  sensors-send-events \

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
  show-telemetry-button \
  upload-3d-glb-file \
  upload-only-3d-glb-files \
  view-3d-glb-file \

unit-tests:
	$(MAKE) -Otarget -j $(NPROCS) _$@ SUPASS=$(SUPASS) -k

_unit-tests: \
  autocamcalib-unit \
  detector-unit \
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
  views-unit \

include Makefile.sscape Makefile.functional Makefile.percebro Makefile.perf \
        Makefile.external_models Makefile.reports Makefile.infra

# Recipes below must be in alphabetical order

3d-camera-control-panel: # NEX-T10475
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_control_panel.py, 'pgserver')

3d-scene-control-panel: # NEX-T10474
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_scene_control_panel.py, 'pgserver')

3d-ui-calibration-points: # NEX-T10473
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_3d_ui_calibration_points.py, 'pgserver web retail-video scene')

add-delete-3d-object: # NEX-T10428
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_add_delete_3d_object.py, 'pgserver')

additional-floor-plans: # NEX-T10405
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_additional_floor_plans.py, 'pgserver')

april-tag-setup: # NEX-T10477
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/camcalibration.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/queuing_video.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_april_tag_setup.py, 'pgserver broker scene ntpserv retail-video queuing-video camcalibration web',sample_data/exampledb.tar.bz2)

bounding-box: # NEX-T10419
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_bounding_box.py,'pgserver web retail-video scene', true,/run/secrets/browser.auth)

calibrate-all-sensor-types: # NEX-T10457
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_calibrate_all_sensor_types.py, 'pgserver')

calibrate-camera-3d-ui-2d-ui: #NEX-T10562
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/camcalibration.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/queuing_video.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml,  tests/ui/tc_calibrate_camera_3d_ui_2d_ui.py, 'pgserver broker scene ntpserv retail-video queuing-video camcalibration web')

camera-deletion: # NEX-T10403
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_deletion.py, 'pgserver')

camera-intrinsics: # NEX-T10415
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_intrinsics.py, 'pgserver')

camera-perspective: # NEX-T10410
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_perspective.py, 'pgserver')

camera-status: # NEX-T10416
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_status.py, 'pgserver web retail-video scene')

check-openvino-version: # NEX-T10407
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; tools/scenescape-start tests/check-openvino-version.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

delete-roi-mqtt: # NEX-T10430
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_roi_mqtt.py, 'pgserver scene',true, /run/secrets/controller.auth)

delete-sensor-mqtt: # NEX-T10432
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensor_mqtt.py,'pgserver scene',true, /run/secrets/controller.auth)

delete-sensor-scene: # NEX-T10397
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensor_scene.py, 'pgserver')

delete-sensors: # NEX-T10399
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensors.py, 'pgserver')

delete-tripwire-mqtt: # NEX-T10431
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_tripwire_mqtt.py,'pgserver scene',true, /run/secrets/controller.auth)

different-formats-maps: # NEX-T10392
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_different_formats_maps.py, 'pgserver')

distance-msoce: # NEX-T10524
	$(call metric-recipe, tests/system/metric/tc_distance_thresh.py, distance-threshold)

idc-error-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, idc-metric, idc-error, 0.05, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, idc-metric, idc-error, 0.05, 10)

live-view-button: # NEX-T10434
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_live_button_works.py,'pgserver web retail-video scene', true)

malformed-json:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE)-interface:$(VERSION) WAITFORCONTAINERS="pgserver scene" tests/security/malformed_data/test_malformed_json.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

manual-camera-calibration: # NEX-T10426
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_manual_camera_calibration.py, 'pgserver')

mqtt-auth: # NEX-T10423
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/security/system/negative_mqtt_insecure_auth.py,'',true,/run/secrets/browser.auth)

mqtt-cert: # NEX-T10423
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/security/system/negative_mqtt_insecure_cert.py,'',true,/run/secrets/browser.auth)

mqtt-large-messages: # NEX-T10462
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(TEST_DATA) \
	  ; tests/mqtt-large-messages.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

msoce-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, msoce-metric, msoce, 0.05, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, msoce-metric, msoce, 0.05, 10)

native-tracker:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; tools/scenescape-start controller/tools/tracker/tracker-test controller/tools/tracker/standard-tests.json | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

newlines-check: # NEX-T10511
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/newlinecheck --ignore .github *.md *.txt */Makefile Makefile common.mk 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

object-crud: # NEX-T10429
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_object_crud.py, 'pgserver')

out-of-box: # NEX-T10417
	$(call common-recipe, sample_data/docker-compose-example.yml, tests/ui/tc_out_of_box.py,'pgserver web queuing-video retail-video scene',true,/run/secrets/browser.auth)

out-of-box-no-ntp: # NEX-T10417
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/retail_video_no_ntp.yml:$(COMPOSE)/queuing_video_no_ntp.yml:$(COMPOSE)/scene_no_ntp.yml:$(COMPOSE)/web.yml, tests/ui/tc_out_of_box.py,'pgserver web queuing-video retail-video scene',true,/run/secrets/browser.auth)

persistence: # NEX-T10393
	$(eval DBROOT=$(TEST_DATA)/db_$@)
	$(eval LOGFILE_NAVIGATE=$(TEST_DATA)/$@-on-page-navigate-$(shell date -u +"%F-%T").log)
	$(eval LOGFILE_RESTART=$(TEST_DATA)/$@-on-restart-$(shell date -u +"%F-%T").log)
	$(eval SELENIUM_COVERAGE_DATA_FILE=$(TESTS_DIRECTORY)/ui/.coverage_$@)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; EXAMPLEDB=$(EXAMPLEDB) \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE)-interface:$(VERSION) DBROOT=$(DBROOT) EXAMPLEDB=$${EXAMPLEDB} $(RUNTEST) $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml $(SELENIUM_TEST_COVERAGE_CMD) --data-file=$(SELENIUM_COVERAGE_DATA_FILE) pytest -s $(GENERATE_JUNITXML) tests/ui/tc_persistence_on_page_navigate.py --password=$(SUPASS) 2>&1 | tee -i $(LOGFILE_NAVIGATE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE_NAVIGATE) \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE)-interface:$(VERSION) DBROOT=$(DBROOT) KEEP_DB=1 EXAMPLEDB=$${EXAMPLEDB} $(RUNTEST) $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml $(SELENIUM_TEST_COVERAGE_CMD) --data-file=$(SELENIUM_COVERAGE_DATA_FILE) pytest -s $(GENERATE_JUNITXML) tests/ui/tc_persistence_on_restart.py --password=$(SUPASS) 2>&1 | tee -i $(LOGFILE_RESTART) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE_RESTART) \
	  ; echo END TEST $@

python-indent-check: # NEX-T10448
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/checkIndent 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

regenerate-makefiles: # NEX-T10493
#	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
#	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/regenerate_makefiles 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

reid-unique-count: # NEX-T10539
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/vdms.yml:$(COMPOSE)/retail_video_reid.yml:$(COMPOSE)/queuing_video_reid.yml:$(COMPOSE)/scene_reid.yml:$(COMPOSE)/web.yml, tests/ui/tc_reid_unique_count.py,'pgserver web queuing-video retail-video scene',true)

deploy: # NEX-T10422
	$(eval LOGFILE=$(TEST_DATA)/code_build/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; SKIP_BRINGUP=1 REQUIRED_FPS=0 CERTPASS=$$(openssl rand -base64 12) SKIPYML=1 SUPASS=$(SUPASS) ./deploy.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

restricted-media-access: # NEX-T10494
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_restricted_media_access.py, 'pgserver')

scene-details: # NEX-T10395
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_scene_details.py, 'pgserver web retail-video scene')

scenes-summary: # NEX-T10394
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_scenes_summary.py, 'pgserver')

sensor-area: # NEX-T10401
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_area.py, 'pgserver')

sensor-location: # NEX-T10400
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_location.py, 'pgserver')

sensor-scene: # NEX-T10396
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_scene.py, 'pgserver')

show-telemetry-button: # NEX-T10435
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_show_telemetry_button.py, 'pgserver web retail-video scene', true, /run/secrets/controller.auth)

superuser-crud-operations: # NEX-T10418
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_superuser_crud_operations.py, 'pgserver')

system-stability: # NEX-T10411
	$(eval HOURS ?= 24)
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/system/stability/tc_sscape_stability.py --hours=$(HOURS),'pgserver web scene',true)

upload-3d-glb-file: # NEX-T10425
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_upload_3d_glb_file.py, 'pgserver')

upload-only-3d-glb-files: # NEX-T10433
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_upload_only_3d_glb_files.py, 'pgserver')

v4l-resolution: # NEX-T10513
	../tools/scenescape-start ./v4l-resolution.py 0

velocity-metric: # NEX-T10463
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, velocity-metric, velocity, 0.15, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, velocity-metric, velocity, 0.15, 10)

view-3d-glb-file: # NEX-T10427
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_view_3d_glb_file.py, 'pgserver')
