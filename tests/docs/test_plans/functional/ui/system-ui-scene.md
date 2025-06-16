```text
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.
```
- [UI/SYS/SSCAPE: UI System Tests](#uisyssscape-ui-system-tests)
  - [Test suite requirements mapping](#test-suite-requirements-mapping)
  - [Test suite prerequisites](#test-suite-prerequisites)
  - [UI/SYS/SSCAPE/01: Verify Scene Details](#uisyssscape01-verify-scene-details)
    - [Test summary](#test-summary)
    - [Test requirements mapping](#test-requirements-mapping)
    - [Test Prerequisites](#test-prerequisites)
    - [Test steps](#test-steps)
  - [UI/SYS/SSCAPE/02: Verify Show Telemetry Button Behavior](#uisyssscape02-verify-show-telemetry-button-behavior)
    - [Test summary](#test-summary-1)
    - [Test requirements mapping](#test-requirements-mapping-1)
    - [Test Prerequisites](#test-prerequisites-1)
    - [Test steps](#test-steps-1)
  - [UI/SYS/SSCAPE/03: Verify Live View Button Behavior](#uisyssscape03-verify-live-view-button-behavior)
    - [Test summary](#test-summary-2)
    - [Test requirements mapping](#test-requirements-mapping-2)
    - [Test Prerequisites](#test-prerequisites-2)
    - [Test steps](#test-steps-2)
  - [UI/SYS/SSCAPE/04: Verify User Can Set yp a New Scene With April Tags](#uisyssscape04-verify-user-can-set-yp-a-new-scene-with-april-tags)
    - [Test summary](#test-summary-3)
    - [Test requirements mapping](#test-requirements-mapping-3)
    - [Test Prerequisites](#test-prerequisites-3)
    - [Test steps](#test-steps-3)
  - [UI/SYS/SSCAPE/05: Manual Calibration In 3D](#uisyssscape05-manual-calibration-in-3d)
    - [Test summary](#test-summary-4)
    - [Test requirements mapping](#test-requirements-mapping-4)
    - [Test Prerequisites](#test-prerequisites-4)
    - [Test steps](#test-steps-4)
  - [UI/SYS/SSCAPE/06: Auto Calibration In 3D](#uisyssscape06-auto-calibration-in-3d)
    - [Test summary](#test-summary-5)
    - [Test requirements mapping](#test-requirements-mapping-5)
    - [Test Prerequisites](#test-prerequisites-5)
    - [Test steps](#test-steps-5)
  - [UI/SYS/SSCAPE/07: Calibrate camera in 3D first and calibrate again camera in 2D using April Tag](#uisyssscape07-calibrate-camera-in-3d-first-and-calibrate-again-camera-in-2d-using-april-tag)
    - [Test summary](#test-summary-6)
    - [Test requirements mapping](#test-requirements-mapping-6)
    - [Test Prerequisites](#test-prerequisites-6)
    - [Test steps](#test-steps-6)

# UI/SYS/SSCAPE: UI System Tests

```UI```
UI tests validate that user interface elements behave as expected when interacted with. These include verifying visibility, state changes, content display, toggle behavior, and user-driven actions such as clicking buttons or opening panels.

## Test suite requirements mapping

- [FAREQ-27](https://jira.devtools.intel.com/browse/FAREQ-27)
- [SAIL-942](https://jira.devtools.intel.com/browse/SAIL-942)
- [SAIL-101](https://jira.devtools.intel.com/browse/SAIL-1015)
- [SAIL-942](https://jira.devtools.intel.com/browse/SAIL-942)
- [SAIL-683](https://jira.devtools.intel.com/browse/SAIL-683)
- [SAIL-561](https://jira.devtools.intel.com/browse/SAIL-561)

## Test suite prerequisites

- Successful Deployment of Scenescape
- Check all services are up and running

## UI/SYS/SSCAPE/01: Verify Scene Details

### Test summary

- Test validate that scene details are visible.

### Test requirements mapping

- [FAREQ-27](https://jira.devtools.intel.com/browse/FAREQ-27)

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Launch web page and navigate to the demo scene view
1. Click on the scene view to check scene detail display
1. Verify that scene name is visible, large floorplan is displayed and several cameras are shown (either online or offline)


> Expected output:

```
$ make -C tests scene-details
# Output will be added later
```

## UI/SYS/SSCAPE/02: Verify Show Telemetry Button Behavior

### Test summary

- Test validate that the `Show Telemetry` button in a scene functions as expected.

### Test requirements mapping

- [SAIL-942](https://jira.devtools.intel.com/browse/SAIL-942)
- [SAIL-101](https://jira.devtools.intel.com/browse/SAIL-1015)  

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Take a screenshot cropped to a camera header bar. (Verify that have a "--" in the right corner)
1. Store in the memory the initial value for <span class="float-right rate" id="rate-camera1">--</span>. -> fps_check1
1. Turn on "Show Telemetry"
1. Take a screenshot cropped to a camera header bar. (Verify that have a "#.# FPS" in the right corner)
1. Store in the memory the value for "Show telemetry" On: <span class="float-right rate" id="rate-camera1">13.5 FPS</span>. -> fps_check2
1. Check that (fps_check1 != fps_check2)
1. Check that (img_1 != img_2)


> Expected output:

```
$ make -C tests show-telemetry-button
# Output will be added later
```

## UI/SYS/SSCAPE/03: Verify Live View Button Behavior

### Test summary

- Verify that the `Live View` button in a scene functions as expected.

### Test requirements mapping

- [SAIL-942](https://jira.devtools.intel.com/browse/SAIL-942)

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Take a screenshot cropped to the Cameras box -> img_1
1. Turn on "Live View". This updates the Camera box layout
1. Take a screenshot cropped to the Cameras box -> img_2
1. Wait enough time for the video streams to update significantly
1. Take a screenshot cropped to the Cameras box -> img_3
1. Check that (img_1 != img_2) and (img_2 != img_3)


> Expected output:

```
$ make -C tests live-view-button
# Output will be added later
```

## UI/SYS/SSCAPE/04: Verify User Can Set yp a New Scene With April Tags

### Test summary

- Verify that user can set up a new scene with April tags

### Test requirements mapping

- [SAIL-683](https://jira.devtools.intel.com/browse/SAIL-683)

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Create a scene with april tags
1. Create at least one camera feed with april tags
1. Test passes if clicking the autocalibration button has an effect on the calibration points
1. Test fails if clicking autocalibration generates a calibration failure message

## UI/SYS/SSCAPE/05: Manual Calibration In 3D

### Test summary

- Verify that user can calibrate camera on a scene by dragging the colored dots.

### Test requirements mapping

- [SAIL-561](https://jira.devtools.intel.com/browse/SAIL-561)

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Open the 3D UI in the application
1. Toggle the "Project Frame" option to enable calibration mode
1. Double-click on the 3D UI to place calibration points
1. Observe that calibration dots appear in the 3D space
1. Click and drag one of the calibration points to adjust its position
1. Toggle the "Calibration Points Visibility" setting
1. Turn it off and confirm the points are hidden
1. Turn it on and confirm the points are visible again


> Expected output:

```
$ make -C tests 3d-ui-calibration-points
# Output will be added later
```

## UI/SYS/SSCAPE/06: Auto Calibration In 3D

### Test summary

- TODO

### Test requirements mapping

- [SAIL-561](https://jira.devtools.intel.com/browse/SAIL-561)

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. Initialize MQTT client and connect to the broker
1. Register two MQTT callbacks:
- One for receiving auto-calibration pose results (DATA_AUTOCALIB_CAM_POSE)
- One for monitoring the status of auto-calibration (SYS_AUTOCALIB_STATUS)
1. Publish a series of "isAlive" messages to trigger auto-calibration system response.
1. On receiving a "running" status:
- Send a "localize" command to the camera’s MQTT command topic
- Wait for a response containing updated calibration points (2D and 3D)
1. Compare updated points to the predefined initial points
1. Test passes, if both sets of updated points are received and differ from the initial ones


> Expected output:

```
$ make -C tests auto-calibration
# Output will be added later
```

## UI/SYS/SSCAPE/07: Calibrate camera in 3D first and calibrate again camera in 2D using April Tag

### Test summary

- Verify that camera is calibrated in 2D UI and new information is saved from 2D in UI interface.

### Test requirements mapping

### Test Prerequisites

1. All services are up and running.
1. Successful login to scenescape-web

### Test steps

1. SceneScape is started - web interface have one scene or more
1. Enter in Queuing scene, Press on Queuing scene
1. Enter in 3D UI View, Press button 3D
1. Enter in Camera 1(atag-qcam1) menu, Press button to calibrate and Save
1. Exit in 2D UI using Configure Queuing Scene button to recalibrate Camera 1(atag-qcam1)
1. Enter in camera configuration menu using Manage atag-qcam1 button
1. Press button Reset points to view 2D April Tags
1. Press button Auto calibrate to calibrate camera
1. Press button Save Camera
1. Verify that no errors and Camera is calibrated in 2D UI and new information is saved from 2D in UI interface.
