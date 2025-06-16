```text
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.
```
- [FUNC/SYS/SSCAPE: SceneScape](#funcsyssscape-scenescape)
  - [Test suite requirements mapping](#test-suite-requirements-mapping)
  - [Test suite prerequisites](#test-suite-prerequisites)
  - [FUNC/SYS/SSCAPE/01: Verify ID Counter Metric For Re-ID](#funcsyssscape01-verify-id-counter-metric-for-re-id)
    - [Test summary](#test-summary)
    - [Test requirements mapping](#test-requirements-mapping)
    - [Test Prerequisites](#test-prerequisites)
    - [Test steps](#test-steps)
  - [FUNC/SYS/SSCAPE/02: Verify Out Of Box Scene](#funcsyssscape02-verify-out-of-box-scene)
    - [Test summary](#test-summary-1)
    - [Test requirements mapping](#test-requirements-mapping-1)
    - [Test Prerequisites](#test-prerequisites-1)
    - [Test steps](#test-steps-1)
  - [FUNC/SYS/SSCAPE/03: Verify Out Of Box Scene Without NTP](#funcsyssscape03-verify-out-of-box-scene-without-ntp)
    - [Test summary](#test-summary-2)
    - [Test requirements mapping](#test-requirements-mapping-2)
    - [Test Prerequisites](#test-prerequisites-2)
    - [Test steps](#test-steps-2)
  - [FUNC/SYS/SSCAPE/04: Verify Cameras Not Receiving Data Identify As Offline](#funcsyssscape04-verify-cameras-not-receiving-data-identify-as-offline)
    - [Test summary](#test-summary-3)
    - [Test requirements mapping](#test-requirements-mapping-3)
    - [Test Prerequisites](#test-prerequisites-3)
    - [Test steps](#test-steps-3)
  - [FUNC/SYS/SSCAPE/05: Display Of Bounding Boxes On The User Interface](#funcsyssscape05-display-of-bounding-boxes-on-the-user-interface)
    - [Test summary](#test-summary-4)
    - [Test requirements mapping](#test-requirements-mapping-4)
    - [Test Prerequisites](#test-prerequisites-4)
    - [Test steps](#test-steps-4)
  - [FUNC/SYS/SSCAPE/06: Verify DLStreamer Can Handle Rotation And Size](#funcsyssscape06-verify-dlstreamer-can-handle-rotation-and-size)
    - [Test summary](#test-summary-5)
    - [Test requirements mapping](#test-requirements-mapping-5)
    - [Test Prerequisites](#test-prerequisites-5)
    - [Test steps](#test-steps-5)

# FUNC/SYS/SSCAPE: SceneScape

```SceneScape```

Intel® SceneScape makes writing applications based on sensor data faster, easier and better by reaching beyond vision-based AI to realize spatial awareness through contextualization of multimodal sensor data in a common reference frame. It provides a collection of microservices, tools and supporting containers to quickly move from single sensor analytics to a multimodal aggregated scene view.

## Test suite requirements mapping

- [FAREQ-469](https://jira.devtools.intel.com/browse/FAREQ-469)
- [SAIL-2491](https://jira.devtools.intel.com/browse/SAIL-2491)
- [FAREQ-71](https://jira.devtools.intel.com/browse/FAREQ-71)
- [FAREQ-69](https://jira.devtools.intel.com/browse/FAREQ-69)
- [FAREQ-87](https://jira.devtools.intel.com/browse/FAREQ-87)
- [SAIL-2007](https://jira.devtools.intel.com/browse/SAIL-2007)

## Test suite prerequisites

- Successful Deployment of Scenescape
- Check all services are up and running

## FUNC/SYS/SSCAPE/01: Verify ID Counter Metric For Re-ID

### Test summary

- Verify that the ID counter metric correctly counts unique ids.
- Feature is functionally successful if unique counts for objects is reduced by at least 50% when Re-ID is enabled compared to Re-ID disabled.

### Test requirements mapping

- [FAREQ-469](https://jira.devtools.intel.com/browse/FAREQ-469)
- [SAIL-2491](https://jira.devtools.intel.com/browse/SAIL-2491)

### Test Prerequisites

1. All services are up and running.
1. [Enable Reidentification](https://github.com/open-edge-platform/scenescape/blob/main/dlstreamer-pipeline-server/README.md#enable-reidentification)

### Test steps

1. Start Scene Scape with the default sample configuration.
1. Subscribe to the MQTT topics and verify that you receive messages from SceneScape.
1. Check the `unique_detection_count` field published through MQTT in the Queuing and Retail scene and verify that these are incrementing continuously.
1. Stop SceneScape and restart it using Re-ID and the VDMS container enabled.
1. Uncomment out the vdms container and add +retail to modelchain for both scenes
1. Check the `unique_detection_count` field published through MQTT in the Queuing and Retail scene and verify that these stop incrementing after the first video loop.
1. Refer to [NEX-T10539](https://jira.devtools.intel.com/secure/Tests.jspa#/testCase/NEX-T10539)

## FUNC/SYS/SSCAPE/02: Verify Out Of Box Scene

### Test summary

- Verify that the out-of-box scene is operating at first build.

### Test requirements mapping

- [FAREQ-71](https://jira.devtools.intel.com/browse/FAREQ-71)

### Test Prerequisites

1. All services are up and running.

### Test steps

1. Login with the "admin" user and the SUPASS you provided at build time
1. Verify that a scenes are visible
1. Verify that dots representing people are moving on the scene
1. Click on the "Live view" toggle and verify that video frames are showing and updating

> Expected output:

```
$ make -C tests out-of-box
# Output will be added later
```

## FUNC/SYS/SSCAPE/03: Verify Out Of Box Scene Without NTP

### Test summary

- Verify that the out-of-box scene is operating at first build without NTP.

### Test requirements mapping

- [FAREQ-71](https://jira.devtools.intel.com/browse/FAREQ-71)

### Test Prerequisites

1. Remove NTP service and update other containers to no longer depend on it. 
1. Deploy Scenescape and check that all services are up and running. 

### Test steps

1. Login with the "admin" user and the SUPASS you provided at build time
1. Verify that a scenes are visible
1. Verify that dots representing people are moving on the scene
1. Click on the "Live view" toggle and verify that video frames are showing and updating
1. Verify that no error or crash occur due to missing NTP

> Expected output:

```
$ make -C tests out-of-box-no-ntp
# Output will be added later
```

## FUNC/SYS/SSCAPE/04: Verify Cameras Not Receiving Data Identify As Offline 

### Test summary

- Verify that the system identifies a camera as offline until data is received.

### Test requirements mapping

- [FAREQ-69](https://jira.devtools.intel.com/browse/FAREQ-69)

### Test Prerequisites

1. Deploy Scenescape and check that all services are up and running. 

### Test steps

1. Launch the Demo scene
1. Observe the cameras and verify that cameras not receiving data identify as offline (by default camera3 is offline, with camera1 and camera2 sending data)
1. Test passes if camera3 has a "camera offline" label while camera1 and camera2 show a snapshot

> Expected output:

```
$ make -C tests camera-status
# Output will be added later
```

## FUNC/SYS/SSCAPE/05: Display Of Bounding Boxes On The User Interface 

### Test summary

- Verify that the system displays bounding boxes around detected Object(s) in the Web User Interface.

### Test requirements mapping

- [FAREQ-87](https://jira.devtools.intel.com/browse/FAREQ-87)

### Test Prerequisites

1. Deploy Scenescape and check that all services are up and running. 

### Test steps

1. Launch the Demo scene
1. Click the "Live View" toggle to the on position
1. Inspect the displayed video frames in for camera1 and camera2 and verify that bounding boxes are decorated around detected people or objects
1. Test passes if bounding boxes are displayed in step 3

> Expected output:

```
$ make -C tests bounding-box
# Output will be added later
```

## FUNC/SYS/SSCAPE/06: Verify DLStreamer Can Handle Rotation And Size

### Test summary

- Verify that DLStreamer can handle rotation and size if provided by a 3D object detection model.

### Test requirements mapping

- [SAIL-2007](https://jira.devtools.intel.com/browse/SAIL-2007)

### Test Prerequisites

1. Deploy Scenescape and check that all services are up and running. 

### Test steps

1. In the "queuing video" container specfied in docker-compose.yml set --camerachain=retail3d
1. Run docker-compose up
1. Use MQTTexplore to connect to Scenescape using the browser container credentials
1. Look at topic: scenescape/data/camera/person/camera2/atag-qcam1
1. Check that detected objects contain data in the following format:

> Expected data:

```
{
"id": 1, 
"category": "person", 
"confidence": 0.8990641236305237, 
"translation": [529, 36, 529], 
"rotation": [1, 5, 3, 2], 
"size": [111.0, 202.0, 111.0], 
"bounding_box": {"x": 529, "y": 36, "z": 529, "width": 111.0, "height": 202.0, "depth": 111.0},
"center_of_mass": {"x": 566, "y": 86, "z": 566, "width": 37.0, "height": 50.5, "depth": 37.0}
} 
```