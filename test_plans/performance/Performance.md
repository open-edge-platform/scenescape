# Vision_AI/SceneScape/Performance Tests: Test Suite

## Test suite requirements mapping

- FAREQ-248: The system shall not allow object ID change error to exceed the defined threshold.
- FAREQ-249: The system shall not allow object jitter to exceed the defined threshold.
- FAREQ-334: The system must support JPEG and PNG image formats from local file system (volume).
- FAREQ-339: The system must loop video playback forever by default.
- FAREQ-469: The system must reidentify objects and persons that were tracked in the past.
- FAREQ-65: The user shall be able to publish {metadata} from a third party inferencing system for mapping data into the scene.
- FAREQ-73: When a new instance of SAIL is brought up, Percebro instances are running with no critical errors.
- FAREQ-75: When a new instance of SAIL is brought up, it runs successfully for 24 hours consecutively without failure.
- FAREQ-89: The system shall enable inference performance profiling.
- FAREQ-91: The system shall enable scene controller performance profiling.
- FAREQ-94: The system shall allow the user to select different OpenVINO supported models for object detection and classification.
- ITEP-25831: Scene performance tests are failing
- ITEP-69604: Validate support for single instance of scene controller handles 50-100 object tracks
- ITEP-73444: Reid performance degradation over time
- ITEP-81806: Metric tests irregular hang-up during execution
- ITEP-81878: RE-ID test failures due to frame skipping and tracker performance issue
- ITEP-81893: Debug and Fix metric tests
- SAIL-101: Test that the system enables inference performance profiling.
- SAIL-1389: Test that specific OpenVINO Model Zoo models are supported
- SAIL-1521: add tracker_metric.py to daily CI
- SAIL-2550: Enrich visual features for better re-id matching
- SAIL-2647: Create testcases for object classes update with new assets
- SAIL-2748: randomly_failing_tests list: Investigate / root-cause idc-error-metric intermittent failures.
- SAIL-2829: Re-ID experiences performance issues with tracked objects after running for a long time
- SAIL-2879: SAIL-T493 Failure - 24 hours consecutive stability test
- SAIL-2936: Automate RE-ID scenarios
- SAIL-3519: broken_tests list: automated release test cases
- SAIL-485: Test fix required for SAIL-101 and SAIL-129 (inference_performance)
- SAIL-615: Automate test cases - WW24 (Chandresh)
- SAIL-776: Test for SAIL-93 is checking FPS instead of just testing if a model works
- SAIL-93: Test that specific OpenVINO Model Zoo models are supported

## Test suite setup

### Hardware Requirements

### Test suite prerequisites

- Required build tools are installedDocker/Kubernetes environments are runningTarget models to be validated are identifiedCamera configuration files for the target models exist under ./sample_camera_configs/Corresponding .ts sample data files exist in the sample_data/ directory
- Scenescape built and deployed.
  Access to docker-compose.yml file.
- There is a scenescape repo cloned on the testing machine

## Vision_AI/SceneScape/Performance Tests/01: Test that specific OpenVINO Model Zoo models are supported

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Verify that a specified model is supported. A model is considered supported if it can be successfully loaded by DLStreamer, and used to run inference without errors, producing valid output metadata.

### Test requirements mapping

- SAIL-1389: Test that specific OpenVINO Model Zoo models are supported
- FAREQ-94: The system shall allow the user to select different OpenVINO supported models for object detection and classification.
- SAIL-615: Automate test cases - WW24 (Chandresh)
- SAIL-776: Test for SAIL-93 is checking FPS instead of just testing if a model works
- SAIL-93: Test that specific OpenVINO Model Zoo models are supported
- FAREQ-89: The system shall enable inference performance profiling.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Install the target model(s) to be validated
   - Test data: `make MODELS=&lt;target_models&gt; PRECISIONS=FP32`
1. Initialize the sample input data required for inference
   - Test data: `make init-sample-data`
1. Start the DLStreamer pipeline using the selected model
   - Test data: `./start-dlsps-pipeline.sh sample_camera_configs/&lt;camera_settings_model&gt;.json`
1. Verify that inference is executed and that output metadata is generated
   - Test data: `output/scenescape_metadata.jsonl`
1. Stop the running pipeline
   Repeat Steps 3 and 4 for each additional model under test
   - Test data: `./stop-dlsps-pipeline.sh`
1. Repeat Steps 3 and 4 for each additional model under test

## Vision_AI/SceneScape/Performance Tests/02: Test that when a new instance of SAIL is brought up, it runs successfully for 24 hours consecutively without failure.

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- This test verifies that the containers are functional for at least 24 hours. It does so by measuring the incoming messages from the sensors, verifying the incoming rate is constant (no drops in rate - to catch re-starting of containers) and fair (no sensor drops) as well as user log-in (to verify the web front end and db are functional).

### Test requirements mapping

- FAREQ-75: When a new instance of SAIL is brought up, it runs successfully for 24 hours consecutively without failure.
- SAIL-2879: SAIL-T493 Failure - 24 hours consecutive stability test
- FAREQ-339: The system must loop video playback forever by default.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. tests/system/smoke/test_017_stability.sh

tests/system/stability/README.md
tests/system/stability/tc_sscape_stability.py

## Vision_AI/SceneScape/Performance Tests/03: Test that the system enables inference performance profiling.

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- This test runs the profiling script and verifies that the system is able to sustain 15 frames per second with two cameras.

### Test requirements mapping

- FAREQ-89: The system shall enable inference performance profiling.
- SAIL-485: Test fix required for SAIL-101 and SAIL-129 (inference_performance)
- FAREQ-65: The user shall be able to publish {metadata} from a third party inferencing system for mapping data into the scene.
- FAREQ-73: When a new instance of SAIL is brought up, Percebro instances are running with no critical errors.
- SAIL-101: Test that the system enables inference performance profiling.
- FAREQ-334: The system must support JPEG and PNG image formats from local file system (volume).

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests inference-performance
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Performance Tests/04: tracker test that runs through all metrics

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- system test that runs through all the metrics (msoce, id change error and max velocity) and compares them to established good values.

tc_tracker_metric.py

### Test requirements mapping

- SAIL-1521: add tracker_metric.py to daily CI
- SAIL-2748: randomly_failing_tests list: Investigate / root-cause idc-error-metric intermittent failures.
- FAREQ-248: The system shall not allow object ID change error to exceed the defined threshold.
- FAREQ-249: The system shall not allow object jitter to exceed the defined threshold.
- ITEP-81806: Metric tests irregular hang-up during execution
- ITEP-81806: Metric tests irregular hang-up during execution
- ITEP-81893: Debug and Fix metric tests

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests idc-error-metric

# make -C tests msoce-metric

# make -C tests velocity-metric

- Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Performance Tests/05: Test Run_scene_performance

**Affected Versions:** 2024.2

### Test summary

-

### Test requirements mapping

- FAREQ-91: The system shall enable scene controller performance profiling.
- SAIL-3519: broken_tests list: automated release test cases
- ITEP-25831: Scene performance tests are failing

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests scene-performance-full
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Performance Tests/06: MSOCE variation based on the object's tracking radius

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that the Mean Squared Object Count Error (MSOCE) varies based on the object's tracking radius.
  In this test, for the same person object, if the tracking radius will increase considerably, the MSOCE will decrease.

### Test requirements mapping

- SAIL-2647: Create testcases for object classes update with new assets

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests distance-msoce
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Performance Tests/07: Test Re-ID performance with visual feature enrichment

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that enriching visual features of stored items improves re-id performance

### Test requirements mapping

- SAIL-2550: Enrich visual features for better re-id matching

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Enable VDMS and Re-ID by modifying docker-compose.yml file:Uncomment the VDMS service segmentUncomment VDMS dependancy from the scene service segmentIn the configs segment change retail-config and queueing-config to
   "file: ./dlstreamer-pipeline-server/retail-config-reid.json" and
   "file: ./dlstreamer-pipeline-server/queuing-config-reid.json" Save changes
1. Restart scenescape:docker compose down --remove-orphansdocker compose up -d
1. Log in and navigate to 2D UI for the scene that has the reid model and toggle "live view"
1. Verify, that a person is assigned the same UUID whenever they enter a scene.

## Vision_AI/SceneScape/Performance Tests/08: Verify that re-ID works without performance degradation over time

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Please identify which performance metrics will be used in this analysis and what is minimum for success.

### Test requirements mapping

- ITEP-73444: Reid performance degradation over time
- SAIL-2829: Re-ID experiences performance issues with tracked objects after running for a long time
- FAREQ-469: The system must reidentify objects and persons that were tracked in the past.
- SAIL-2936: Automate RE-ID scenarios
- FAREQ-339: The system must loop video playback forever by default.
- SAIL-3519: broken_tests list: automated release test cases
- ITEP-81878: RE-ID test failures due to frame skipping and tracker performance issue

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Start scenescape with vdms and re-ID enabled in queueing scene
   - Test data: `Uncomment out vdms container
Add +reid to camerachain`
1. Start scenescape in default state
   - Test data: `No vdms container or reid`

## Vision_AI/SceneScape/Performance Tests/09: Validate support for single instance of scene controller handles 50 object tracks

**Affected Versions:**

### Test summary

- This test verifies that Scene Controller is able to handle tracking for objects when their count is 50 with flawless accuracy.
  Currently (as of 16/07/25) value at which tracker is beginning to have problems with keeping track of objects is roughly 25.

In current state, whenever object count rises above 50, tracker can often accidentally count the same object as a new object because of lost frames.
There are two ways to validate if the tracker is correctly tracking objects:

1. MSOCE (Mean Squared Object Count Error) - this is a value displayed to user via MQTT, it is calculated by service and measures how accurately the tracker predicts the number of objects in a scene over time.
   It can become untruthful if tracker counted the same object multiple times (due to frame loss).
2. When viewing scenescape logs live, whenever a message "tracker work queue not empty" appears, it means that the tracker is overwhelmed by the numbers of messages/updates it is getting.
   Ideally in the scene with 50 objects tracked, no such messages should appear.

Notes:

1. Whenever possible, this TC should have multiple variants of checks for different number of objects (50-100)
2. There is additional way to check for incorrect object tracks and it is a number of fall behinds, which is currently not considered for validation.

### Test requirements mapping

- ITEP-69604: Validate support for single instance of scene controller handles 50-100 object tracks

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, env and deploy demo scenes using command "make demo"
1. Configure Scenescape logs in cmd:
   Open a cmd line, connect to the testing platform (where scenescape project is cloned to) via ssh and type docker compose logs -f
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
Topics to listen to: "#" (all)
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Prepare the environment for the 50 object scene
1. Download the files from this location: NEX-T12747
1. Place retail-cam.ts in scenescape/sample_data/
1. Place dls-indoor-docker-compose.yml on the server, change it's name and replace the original docker-compose.yml with it
   mv dls-indoor-docker-compose.yml scenescape/docker-compose.yml
1. bring up containers
   docker compose up -d
   - Test data: `Contents of NEX-T12747 share file:
5-indoor-cams.json
dls-indoor-docker-compose.yml
retail-cam.ts
NewRetailIndoor.zip`
1. Initialize the scene with 50 trackable objects:
1. Click on "+ Import Scene"
1. Choose file (NewRetailIndoor.zip from the previous step)
1. Click Import
1. Note observations, logs and MQTT messages
