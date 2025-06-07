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
IMAGE_INTERFACE=$(IMAGE)-interface
BASE_IMAGE=$(IMAGE)-manager
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
	  ; env IMAGE=$${BASE_IMAGE}:$(VERSION) BROWSER_IMAGE=$(IMAGE_INTERFACE):$(VERSION) \
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
	  ; docker/scenescape-start --image ${IMAGE}-controller pytest -s $(GENERATE_JUNITXML) $(TEST_SCRIPT) \
	                                   $${METRIC} $${THRESHOLD} $${FRAME_RATE} \
	                                   -o junit_suite_name=$(TEST_SUITE) | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@
endef

# Not sorted alphabetically on purpose
tests: \
  basic-acceptance-tests \
  standard-tests \

# These tests must be run during release cycle. FIXME - automate: See SAIL-1874
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
  percebro-pinhole-undistort \
  reid-unique-count \
  reid-performance-degradation \
  scene-details \
  superuser-crud-operations \
  calibrate-camera-3d-ui-2d-ui \
  randomly-failing-tests \

broken-tests: \
  3d-camera-control-panel \
  acl-check \
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
  regenerate-makefiles \
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
  mesh-util-unit \
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

3d-camera-control-panel: # SAIL-T594
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_control_panel.py, 'pgserver')

3d-scene-control-panel: # SAIL-T593
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_scene_control_panel.py, 'pgserver')

3d-ui-calibration-points: # SAIL-T592
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_3d_ui_calibration_points.py, 'pgserver web retail-video scene')

add-delete-3d-object: # SAIL-T521
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_add_delete_3d_object.py, 'pgserver')

additional-floor-plans: # SAIL-T478
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_additional_floor_plans.py, 'pgserver')

april-tag-setup: # SAIL-T596
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/camcalibration.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/queuing_video.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_april_tag_setup.py, 'pgserver broker scene ntpserv retail-video queuing-video camcalibration web',sample_data/exampledb.tar.bz2)

bounding-box: # SAIL-T506
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_bounding_box.py,'pgserver web retail-video scene', true,/run/secrets/browser.auth)

calibrate-all-sensor-types: # SAIL-T574
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_calibrate_all_sensor_types.py, 'pgserver')

calibrate-camera-3d-ui-2d-ui: #SAIL-T684
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/camcalibration.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/queuing_video.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml,  tests/ui/tc_calibrate_camera_3d_ui_2d_ui.py, 'pgserver broker scene ntpserv retail-video queuing-video camcalibration web')

camera-deletion: # SAIL-T469
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_deletion.py, 'pgserver')

camera-intrinsics: # SAIL-T498
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_intrinsics.py, 'pgserver')

camera-perspective: # SAIL-T489
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_perspective.py, 'pgserver')

camera-status: # SAIL-T500
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_camera_status.py, 'pgserver web retail-video scene')

check-openvino-version: # SAIL-T486
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; docker/scenescape-start tests/check-openvino-version.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

delete-roi-mqtt: # SAIL-T526
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_roi_mqtt.py, 'pgserver scene',true, /run/secrets/controller.auth,tests/testdb.tar.bz2,scenescape-interface)

delete-sensor-mqtt: # SAIL-T529
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensor_mqtt.py,'pgserver scene',true, /run/secrets/controller.auth)

delete-sensor-scene: # SAIL-T459
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensor_scene.py, 'pgserver')

delete-sensors: # SAIL-T462
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_sensors.py, 'pgserver')

delete-tripwire-mqtt: # SAIL-T527
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_delete_tripwire_mqtt.py,'pgserver scene',true, /run/secrets/controller.auth)

different-formats-maps: # SAIL-T453
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_different_formats_maps.py, 'pgserver')

distance-msoce: # SAIL-T644
	$(call metric-recipe, tests/system/metric/tc_distance_thresh.py, distance-threshold)

idc-error-metric: # SAIL-T580
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, idc-metric, idc-error, 0.05, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, idc-metric, idc-error, 0.05, 10)

live-view-button: # SAIL-T531
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_live_button_works.py,'pgserver web retail-video scene', true)

malformed-json:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; env IMAGE=$(BASE_IMAGE):$(VERSION) BROWSER_IMAGE=$(IMAGE)-interface:$(VERSION) WAITFORCONTAINERS="pgserver scene" tests/security/malformed_data/test_malformed_json.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

manual-camera-calibration: # SAIL-T519
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_manual_camera_calibration.py, 'pgserver')

mqtt-auth: # SAIL-T511
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/security/system/negative_mqtt_insecure_auth.py)

mqtt-cert: # SAIL-T511
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/security/system/negative_mqtt_insecure_cert.py)

mqtt-large-messages: # SAIL-T579
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(TEST_DATA) \
	  ; tests/mqtt-large-messages.py 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

msoce-metric: # SAIL-T580
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, msoce-metric, msoce, 0.05, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, msoce-metric, msoce, 0.05, 10)

native-tracker:
	$(eval LOGFILE=$(TEST_DATA)/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; docker/scenescape-start controller/tools/tracker/tracker-test controller/tools/tracker/standard-tests.json | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

newlines-check: # SAIL-T631
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/newlinecheck --ignore .github *.md *.txt */Makefile Makefile common.mk 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

object-crud: # SAIL-T522
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_object_crud.py, 'pgserver')

out-of-box: # SAIL-T501
	$(call common-recipe, sample_data/docker-compose-example.yml, tests/ui/tc_out_of_box.py,'pgserver web queuing-video retail-video scene',true,/run/secrets/browser.auth,tests/testdb.tar.bz2,scenescape-interface)

out-of-box-no-ntp: # SAIL-T501
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/retail_video_no_ntp.yml:$(COMPOSE)/queuing_video_no_ntp.yml:$(COMPOSE)/scene_no_ntp.yml:$(COMPOSE)/web.yml, tests/ui/tc_out_of_box.py,'pgserver web queuing-video retail-video scene',true,/run/secrets/browser.auth,tests/testdb.tar.bz2,scenescape-interface)

persistence: # SAIL-T454
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

python-indent-check: # SAIL-T564
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/checkIndent 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

regenerate-makefiles: # SAIL-T613
	$(eval LOGFILE=$(TEST_DATA)/code_check/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; tests/scripts/regenerate_makefiles 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \

reid-unique-count: # SAIL-T661
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver_default.yml:$(COMPOSE)/vdms.yml:$(COMPOSE)/retail_video_reid.yml:$(COMPOSE)/queuing_video_reid.yml:$(COMPOSE)/scene_reid.yml:$(COMPOSE)/web.yml, tests/ui/tc_reid_unique_count.py,'pgserver web queuing-video retail-video scene',true)

deploy: # SAIL-T510
	$(eval LOGFILE=$(TEST_DATA)/code_build/$@-$(shell date -u +"%F-%T").log)
	@set -ex \
	  ; echo RUNNING TEST $@ \
	  ; cd .. \
	  ; mkdir -p $(shell dirname $(LOGFILE)) \
	  ; SKIP_BRINGUP=1 REQUIRED_FPS=0 CERTPASS=$$(openssl rand -base64 12) SKIPYML=1 SUPASS=$(SUPASS) ./deploy.sh 2>&1 | tee -i $(LOGFILE) \
	  ; echo "MAKE_TARGET: $@" | tee -ia $(LOGFILE) \
	  ; echo END TEST $@

restricted-media-access: # SAIL-T614
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_restricted_media_access.py, 'pgserver')

scene-details: # SAIL-T457
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_scene_details.py, 'pgserver web retail-video scene')

scenes-summary: # SAIL-T456
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_scenes_summary.py, 'pgserver')

sensor-area: # SAIL-T465
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_area.py, 'pgserver')

sensor-location: # SAIL-T464
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_location.py, 'pgserver')

sensor-scene: # SAIL-T458
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_sensor_scene.py, 'pgserver')

show-telemetry-button: # SAIL-T532
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_show_telemetry_button.py, 'pgserver web retail-video scene', true, /run/secrets/controller.auth)

superuser-crud-operations: # SAIL-T502
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_superuser_crud_operations.py, 'pgserver')

system-stability: # SAIL-T493
	$(eval HOURS ?= 24)
	$(call common-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/retail_video.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/system/stability/tc_sscape_stability.py --hours=$(HOURS),'pgserver web scene',true)

upload-3d-glb-file: # SAIL-T517
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_upload_3d_glb_file.py, 'pgserver')

upload-only-3d-glb-files: # SAIL-T530
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/web.yml, tests/ui/tc_upload_only_3d_glb_files.py, 'pgserver')

v4l-resolution: # SAIL-T633
	../docker/scenescape-start ./v4l-resolution.py 0

velocity-metric: # SAIL-T580
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, velocity-metric, velocity, 0.15, 30)
	$(call metric-recipe, tests/system/metric/tc_tracker_metric.py, velocity-metric, velocity, 0.15, 10)

view-3d-glb-file: # SAIL-T520
	$(call selenium-recipe, $(COMPOSE)/broker.yml:$(COMPOSE)/ntp.yml:$(COMPOSE)/pgserver.yml:$(COMPOSE)/scene.yml:$(COMPOSE)/web.yml, tests/ui/tc_view_3d_glb_file.py, 'pgserver')
