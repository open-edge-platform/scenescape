# Vision_AI/SceneScape/ADMIN: Test Suite

## Test suite requirements mapping

- FAREQ-109: System must support 3rd party scene maps in GLTF format
- FAREQ-110: System must generate the uploaded scene on the user interface
- FAREQ-111: System must automatically determine the camera pose
- FAREQ-130: System shall allow user to successfully upload custom scene maps that are in GLTF format
- FAREQ-131: System must allow user to manually estimate the camera pose
- FAREQ-20: The system shall verify that the floorplan image complies with the following file formats: png, jpeg
- FAREQ-26: The user shall be able to view a summary of all scenes.
- FAREQ-27: The user shall be able to view scene details.
- FAREQ-28: The system shall require all sensors to be assigned to one scene (and only one scene).
- FAREQ-31: The system shall maintain a list of sensors that are not assigned to a scene.
- FAREQ-32: A user shall be able to add an existing system sensor from the list that is not assigned to a scene.
- FAREQ-33: The user shall be able to view all sensors (orphaned and assigned to a scene).
- FAREQ-35: The user shall be able to delete any existing sensor (both orphaned and assigned to a scene).
- FAREQ-38: The user shall be able to configure the sensor location in the scene.
- FAREQ-40: The user shall be able to configure measurement areas to the entire scene, a circle, or custom area (polygon).
- FAREQ-45: The system shall maintain a list of cameras that are not assigned to a scene.
- FAREQ-46: A user shall be able to add an existing system camera from the list that is not assigned to a scene.
- FAREQ-47: The user shall be able to list all cameras (orphaned and assigned to a scene).
- FAREQ-49: The user shall be able to delete any existing camera (both orphaned and assigned to a scene).
- FAREQ-57: The system shall allow the user to create one or more directional lines over the scene to define tripwires.
- FAREQ-58: The system shall allow the user to view/read one or more directional lines over the scene to define tripwires.
- FAREQ-59: The system shall allow the user to update one or more directional lines over the scene to redefine tripwires.
- FAREQ-60: The system shall allow the user to delete one or more directional lines over the scene to eliminate tripwires.
- FAREQ-61: The system shall report occupancy changes in regions of interest.
- FAREQ-62: The system shall report +1 or -1 for each directional trip wire activation.
- FAREQ-66: The system shall allow the user to adjust the position and orientation of scenes in respect to other scenes
- FAREQ-67: The user shall be able to configure the camera intrinsics (focal length and resolution).
- FAREQ-69: The system shall identify a camera as offline until data is received.
- FAREQ-71: The system shall provide an out-of-the box scene with cameras, stored videos and associated database, and configuration files to make out-of-box experience as easy as possible.
- FAREQ-73: When a new instance of SAIL is brought up, Percebro instances are running with no critical errors.
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- FAREQ-76: When functionality is changed at the system level (CRUD functions), a superuser shall enable the changes.
- FAREQ-77: The system shall map detected {Object(s)} to a {Scene Graph}.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- FAREQ-81: When an {Object(s)} enters a Region of Interest, the system shall increment the Region of Interest {Object} count by 1.
- FAREQ-82: When an {Object(s)} exits a Region of Interest, the system shall decrement the Region of Interest {Object} count by 1.
- FAREQ-86: The system shall provide a Web User Interface for calibrating sensors and cameras.
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- ITEP-73425: DLStreamer adapter causes pipeline failure without NTP
- ITEP-73442: Cannot create Region of Interest
- ITEP-73443: Cannot create Tripwire
- ITEP-74993: [Kubernetes][Cameras] Cannot manually change and save camera settings
- ITEP-74994: Unable to edit intrinsic/distortion parameters
- ITEP-77684: [API][UI] API allows sensor creation without scene assignment, UI does not
- SAIL-1015: Test that the "Show Telemetry" button in a scene works.
- SAIL-1056: Scene files in .obj format upload successfully to the Scenescape server but are not visible in the 3D scene.
- SAIL-105: Test that the user can manage camera intrinsics
- SAIL-1068: Save camera calibration results in 500 internal server
- SAIL-1071: Implement automated test SAIL-904 verifying that .gltf files an be uploaded and are visible in the 3D scene.
- SAIL-1072: As a tester, I would like to test 3D object update
- SAIL-1074: As a tester, I would like to test delete a sensor MQTT
- SAIL-1075: As a tester, I would like to test delete a Tripwire MQTT
- SAIL-108: Test that the out-of-box Demo scene is operating at first build
- SAIL-1106: Test non-superuser account permissions
- SAIL-1108: As a tester, I would like to test delete a ROI MQTT
- SAIL-1116: Region of interest and tripwire tests fail
- SAIL-1155: Re-enable SAIL-105 test for managing camera intrinsics
- SAIL-1244: Write a test to verify event generated upon object entering a region includes an entered field with the list of newly entered objects
- SAIL-1245: Write a test to verify event generated upon object exiting a region includes an exited field with the list of objects that just left the region
- SAIL-1252: Functional test delete-sensor-mqtt SAIL-997 does not work
- SAIL-1269: Directory not empty error on TC_SAIL-874 causes test failure
- SAIL-1284: Update tc_sail_91_tripwire_mqtt.py
- SAIL-1297: Update test case SAIL-105 to properly test updated camera intrinsics edit page
- SAIL-1310: MANUAL CAMERA CALIBRATION (+)
- SAIL-1538: Enable Markerless Auto Camera Calibration
- SAIL-1900: 3D UI must have parity with 2D UI
- SAIL-2150: tests for upload and view 3d glb are broken
- SAIL-21: As an Engineer I want to implement OpenSAIL using a Github repository so I can create traceability to tests, requirements and code
- SAIL-2343: User without sufficient permissions is able to perform CRUD operations from 3D UI
- SAIL-2350: Run Manual Tests for 2023.4
- SAIL-2362: Remove Tests Failing Due to Code Changes
- SAIL-2384: Fix delete-sensor-mqtt test
- SAIL-2385: Fix delete-tripwire-mqtt test
- SAIL-2541: MQTT Tripwire events are triggered after removing a tripwire
- SAIL-2645: Fix camera-intrinsics test
- SAIL-2733: Sensor with Circle measurement doesn't publish any event
- SAIL-2736: broken_tests list: Investigate / root-cause view-3d-glb-file failure.
- SAIL-2738: broken_tests list: Investigate / root-cause show-telemetry-button failure.
- SAIL-2739: broken_tests list: Investigate / root-cause upload-3d-glb-file failure.
- SAIL-2740: randomly_failing_tests list: Investigate / root-cause camera-status intermittent failures.
- SAIL-2742: randomly_failing_tests list: Investigate / root-cause group intermittent failures
- SAIL-2743: randomly_failing_tests list: Investigate / root-cause object-crud intermittent failures.
- SAIL-2744: randomly_failing_tests list: Investigate / root-cause scene-details intermittent failures.
- SAIL-2745: randomly_failing_tests list: Investigate / root-cause camera-perspective intermittent failures.
- SAIL-2747: randomly_failing_tests list: Investigate / root-cause superuser-crud-operations intermittent failures.
- SAIL-2749: randomly_failing_tests list: Investigate / root-cause live-view-button intermittent failures.
- SAIL-2751: randomly_failing_tests list: Investigate / root-cause different-formats-maps intermittent failures.
- SAIL-2752: randomly_failing_tests list: Investigate / root-cause manual-camera-calibration intermittent failures.
- SAIL-2754: randomly_failing_tests list: Investigate / root-cause camera-deletion intermittent failures.
- SAIL-2757: out-of-box sometimes fails to detect objects
- SAIL-2859: Fix add-orphaned-cameras randomly failing test case
- SAIL-2866: Fix orphaned-sensor randomly failing test case
- SAIL-305: Automate Test Cases - Sprint WW02 (Marian-Virgil)
- SAIL-3104: Documentation for how camera instrinsics and distortion is handled
- SAIL-327: Automate test cases - sprint WW04 (Marian)
- SAIL-3416: The system does not accept gif format as a scene floor plan
- SAIL-3438: Test different formats map didn't validate all provided formats
- SAIL-358: Automate Test Cases - Sprint WW06(Marian)
- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)
- SAIL-372: Automate Test Cases - WW08 Sprint (Marian)
- SAIL-409: Automate Test Cases - WW10 Sprint (Chandresh)
- SAIL-410: Automate Test Cases - WW10 Sprint (Marian)
- SAIL-449: Automate Test Cases -Sprint WW12(Marian)
- SAIL-474: Automate Test Cases - WW16 (Chandresh)
- SAIL-53: Test that various image formats are supported (png, jpeg, gif)
- SAIL-56: Test that the user can view a summary of all scenes
- SAIL-57: Test that the user can view scene details
- SAIL-58: Test that a new sensor must be added to a scene
- SAIL-592: Automate Test Cases - WW20 (Chandresh)
- SAIL-59: Test that sensors are not deleted when the parent scene is deleted
- SAIL-60: Test for adding an orphaned sensor to a scene
- SAIL-615: Automate test cases - WW24 (Chandresh)
- SAIL-616: Automate test cases - WW24 sprint(Marian)
- SAIL-62: Test deleting sensors
- SAIL-64: Test setting a sensor location in the scene
- SAIL-65: Test measurement area configuration for a sensor
- SAIL-68: Test adding orphaned cameras to a scene
- SAIL-69: Test deletion of cameras
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-820: Debug & fix failed test cases in SAIL-493 (HueyLi)
- SAIL-821: Debug & fix failed test cases in SAIL-493 (Shin Wei)
- SAIL-824: Debug & fix failed test cases in SAIL-493 (Marian)
- SAIL-82: Test that regions of interest report occupancy changes
- SAIL-834: Debug & fix failed test cases in SAIL-493 (HueyLi) - WW40
- SAIL-848: Test-Manual Camera Calibration
- SAIL-905: Test that a user can add and delete a 3D object
- SAIL-91: Test that tripwires report +1 and -1 for traversals across the line
- SAIL-935: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-942: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-982: After deleting a sensor from a scene MQTT messages for the sensor continue to be published.
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-996: User unable to delete object if no 3D model file added
- SAIL-997: As a user if I delete a sensor MQTT publishing for that sensor should stop.
- SAIL-998: After deleting a ROI from a scene MQTT messages for the ROI continue to be published.
- SAIL-999: After deleting a Tripwire from a scene MQTT messages for the Tripwire continue to be published.
- SAIL-9: 3D Pathfinding [2022.1 Release]

## Test suite setup

### Hardware Requirements

### Test suite prerequisites

- A current version of Scenescape is built, started and a browser is connected to the Web service.
- Scenescape is up and running
- User already has a 3D object added
- User already has camera(s) added to a scene

## Vision_AI/SceneScape/ADMIN/01: Test that various image formats are supported (glb, png, jpeg, jpg, zip, ply)

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test passes if all image types display correctly.

### Test requirements mapping

- FAREQ-20: The system shall verify that the floorplan image complies with the following file formats: png, jpeg
- SAIL-53: Test that various image formats are supported (png, jpeg, gif)
- SAIL-2751: randomly_failing_tests list: Investigate / root-cause different-formats-maps intermittent failures.
- SAIL-3416: The system does not accept gif format as a scene floor plan
- SAIL-3438: Test different formats map didn't validate all provided formats

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automated execution: make -C tests different-formats-maps
   For manual execution: see below
1. Log In
1. Enter Queuing scene edition by clicking the button with the 'pencil' icon
1. Using the scene map file upload form, select a new floor plan image in glb format and click 'Save Scene Updates' button
1. Verify that the image correctly displays in the UI
1. Repeat steps 3-4 for each of the following file types: png jpeg jpg zip ply

## Vision_AI/SceneScape/ADMIN/02: Test that the user can view a summary of all scenes

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Starting with the Demo scene, create a new sceneVerify that a page exists where both scene are visible in a summary viewTest PASSES if a summary of both scenes can be viewed on a single page.

### Test requirements mapping

- FAREQ-26: The user shall be able to view a summary of all scenes.
- SAIL-372: Automate Test Cases - WW08 Sprint (Marian)
- SAIL-56: Test that the user can view a summary of all scenes

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests scenes-summary
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/03: Test that the user can view scene details

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Using the demo scene, verify that scene details are visible when clicking on the scene summary view. The interface must show the scene name and a large floorplan, along with several cameras (either online or offline).
  Test PASSES if a scene detail is displayed to the user.

### Test requirements mapping

- FAREQ-27: The user shall be able to view scene details.
- SAIL-372: Automate Test Cases - WW08 Sprint (Marian)
- SAIL-57: Test that the user can view scene details
- SAIL-2744: randomly_failing_tests list: Investigate / root-cause scene-details intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests scene-details
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/04: Test that the creation of an orphaned sensor is possible

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Find a "New Sensor" button on the UI (either under a scene or under the "Sensors" menu)Click "New Sensor"Fill out Sensor values, but do not select a sceneVerify that the form successfully submits and the sensor is shown under the "Sensors" tab without a scene assigned.
  Test PASSES if the user is able to create an orphaned sensor when adding a new sensor to the system.

### Test requirements mapping

- FAREQ-28: The system shall require all sensors to be assigned to one scene (and only one scene).
- SAIL-410: Automate Test Cases - WW10 Sprint (Marian)
- SAIL-58: Test that a new sensor must be added to a scene
- ITEP-77684: [API][UI] API allows sensor creation without scene assignment, UI does not
- ITEP-77684: [API][UI] API allows sensor creation without scene assignment, UI does not

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests sensor-scene
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/05: Test orphaned sensors in a deleted scene

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create a new sceneAdd a new sensor to the sceneDelete the new sceneVerify that the new sensor is still shown in the UITest PASSES if the sensor is still visible.

### Test requirements mapping

- FAREQ-31: The system shall maintain a list of sensors that are not assigned to a scene.
- SAIL-358: Automate Test Cases - Sprint WW06(Marian)
- SAIL-59: Test that sensors are not deleted when the parent scene is deleted

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests delete-sensor-scene
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/06: ​Test for adding an orphaned sensor to a scene

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Steps:
  Create an orphaned sensor (e..g delete a sensor's parent scene)View the orphaned sensor in the Sensors listClick on a link to edit the orphaned sensorAssign the orphaned sensor to a new scene using the formVerify that the sensor now appears under the new sceneThis test PASSES if a previously orphaned sensor is assigned to a scene.

### Test requirements mapping

- FAREQ-32: A user shall be able to add an existing system sensor from the list that is not assigned to a scene.
- SAIL-358: Automate Test Cases - Sprint WW06(Marian)
- SAIL-60: Test for adding an orphaned sensor to a scene
- FAREQ-33: The user shall be able to view all sensors (orphaned and assigned to a scene).
- SAIL-2866: Fix orphaned-sensor randomly failing test case

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests orphaned-sensor
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/07: Test deleting sensors

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create sensors in two separate scenesDelete one scene, leaving one or more orphaned sensorsView the sensors, and verify that sensors that are assigned to a scene can be deletedVerify that instructions are available for deleting orphaned sensors (can be instructions to add to a scene first)Perform instructions from step 4View the sensors, and verify that it's possible to delete the sensor from step 4This test PASSES if it is possible to delete any sensor.

### Test requirements mapping

- FAREQ-35: The user shall be able to delete any existing sensor (both orphaned and assigned to a scene).
- SAIL-358: Automate Test Cases - Sprint WW06(Marian)
- SAIL-21: As an Engineer I want to implement OpenSAIL using a Github repository so I can create traceability to tests, requirements and code
- SAIL-62: Test deleting sensors

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automated execution: make -C tests delete-sensors
   For manual steps: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1. Create sensors in two separate scenes
1. Delete one scene, leaving one or more orphaned sensors
1. View the sensors, and verify that sensors that are assigned to a scene can be deleted
1. View the sensors, and verify that orphaned sensors can be deleted

## Vision_AI/SceneScape/ADMIN/08: Test setting a sensor location in the scene

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create a sensorEdit the sensor, then click and drag either the dot or the icon (if configured) of the sensor to a different location in the sceneSave the sensorEdit the sensor again and verify that the new location persistsTest PASSES if the location of the sensor remains where it was last saved.

### Test requirements mapping

- FAREQ-38: The user shall be able to configure the sensor location in the scene.
- FAREQ-86: The system shall provide a Web User Interface for calibrating sensors and cameras.
- SAIL-372: Automate Test Cases - WW08 Sprint (Marian)
- SAIL-64: Test setting a sensor location in the scene

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests sensor-location
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/09: Test measurement area configuration for a sensor

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create a sensorVerify that the UI shows three measurement area types as a radio button selectionVerify that "Entire Scene" is selected by default.Select "Circle" and verify that a circle is shown and that its radius can be modified using the sliderSave the sensor and verify that the "Circle" configuration persistsSelect "Custom area (polygon)" and follow the on-screen directions to create a polygon areaVerify that a polygon can be drawn on the interfaceSave the sensor and verify that the polygon area configuration persistsTest PASSES if each of the above steps is verified.

### Test requirements mapping

- FAREQ-40: The user shall be able to configure measurement areas to the entire scene, a circle, or custom area (polygon).
- SAIL-449: Automate Test Cases -Sprint WW12(Marian)
- SAIL-65: Test measurement area configuration for a sensor

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests sensor-area
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/10: Test adding orphaned cameras to a scene

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create one or more orphaned cameras by adding them to a scene and then deleting the sceneClick on the "Cameras" menu and edit an orphaned cameraVerify that it is possible to add the orphaned camera to a scene by selecting the scene in the appropriate form fieldConfirm that the sensor now appears on the scene detail under "Cameras"Test PASSES if the above steps are verified.

### Test requirements mapping

- FAREQ-46: A user shall be able to add an existing system camera from the list that is not assigned to a scene.
- SAIL-409: Automate Test Cases - WW10 Sprint (Chandresh)
- SAIL-68: Test adding orphaned cameras to a scene
- FAREQ-47: The user shall be able to list all cameras (orphaned and assigned to a scene).
- FAREQ-45: The system shall maintain a list of cameras that are not assigned to a scene.
- SAIL-2859: Fix add-orphaned-cameras randomly failing test case

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests add-orphaned-cameras
   For manual execution: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1. Create one or more orphaned cameras by adding them to a scene and then deleting the scene
1. Click on the "Cameras" menu and edit an orphaned camera
1. Verify that it is possible to add the orphaned camera to a scene by selecting the scene in the appropriate form field
1. Confirm that the sensor now appears on the scene detail under "Cameras"

## Vision_AI/SceneScape/ADMIN/11: Test deletion of cameras

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create an orphaned camera by creating a camera in a scene, then deleting the sceneClick on the "Cameras" menu to view all system camerasClick on the orphaned camera, then add it to an existing sceneOpen up the scene, then click on the icon to delete the cameraGo the camera list and verify that the camera is deletedTest PASSES if the above steps are all verified.

### Test requirements mapping

- FAREQ-49: The user shall be able to delete any existing camera (both orphaned and assigned to a scene).
- SAIL-409: Automate Test Cases - WW10 Sprint (Chandresh)
- SAIL-69: Test deletion of cameras
- SAIL-2754: randomly_failing_tests list: Investigate / root-cause camera-deletion intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/ADMIN/12: Test that regions of interest report occupancy changes

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Create a region of interest with a name and save it in a test sceneSubscribe to the region topic: scenescape/event/region/&lt;scene-name&gt;/&lt;region_name&gt;/countPublish detection bounding boxes that represent locations within the regionVerify that the counts precisely reflect the contents of the region (count should be &gt;0)Publish detection bounding boxes that represent location outside the regionVerify that the counts precisely reflect the contents of the region (count should be 0)Verify event generated upon object entering a region includes an entered field with the list of newly entered objectsVerify event generated upon object exiting a region includes an exited field with the list of objects that just left the regionVerify events published contain the following data:timestampsceneIdsceneNameregionIdregionNamecountsobjectsTest PASSES if above steps succeed.

### Test requirements mapping

- SAIL-1116: Region of interest and tripwire tests fail
- SAIL-1244: Write a test to verify event generated upon object entering a region includes an entered field with the list of newly entered objects
- SAIL-1245: Write a test to verify event generated upon object exiting a region includes an exited field with the list of objects that just left the region
- FAREQ-61: The system shall report occupancy changes in regions of interest.
- FAREQ-81: When an {Object(s)} enters a Region of Interest, the system shall increment the Region of Interest {Object} count by 1.
- FAREQ-82: When an {Object(s)} exits a Region of Interest, the system shall decrement the Region of Interest {Object} count by 1.
- SAIL-615: Automate test cases - WW24 (Chandresh)
- SAIL-821: Debug & fix failed test cases in SAIL-493 (Shin Wei)
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-82: Test that regions of interest report occupancy changes
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/ADMIN/13: Test that tripwires report +1 and -1 for traversals across the line

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that tripwires report appropriate directional values during detections

### Test requirements mapping

- SAIL-1116: Region of interest and tripwire tests fail
- SAIL-1284: Update tc_sail_91_tripwire_mqtt.py
- FAREQ-62: The system shall report +1 or -1 for each directional trip wire activation.
- SAIL-834: Debug & fix failed test cases in SAIL-493 (HueyLi) - WW40
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-592: Automate Test Cases - WW20 (Chandresh)
- SAIL-91: Test that tripwires report +1 and -1 for traversals across the line
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests mqtt-tripwire
   For manual execution: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1. Using the Demo scene, create a tripwire called "Test" in an area where detections are showing
1. Using MQTT Explorer navigate to the tripwire topic
1. Verify that "direction": 1 is published when objects traverse in the direction of the arrow
1. Verify that "direction": -1 is published when objects travers opposite the direction of the arrow
1. Verify events published contain the following data:timestampsceneIdsceneNametripwireIdtripwireNamecountsobjects

## Vision_AI/SceneScape/ADMIN/14: Test that the system provides a manual camera perspective calibration interface

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Open the Demo scene and verify that the camera feeds are showingClick on Camera1Verify that the interface allows for modifying the view of a camera against the scene (and vice versa)Save the changes and verify they persist across a page refreshTest PASSES if steps 1-4 are verified.

### Test requirements mapping

- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- FAREQ-66: The system shall allow the user to adjust the position and orientation of scenes in respect to other scenes
- FAREQ-86: The system shall provide a Web User Interface for calibrating sensors and cameras.
- SAIL-305: Automate Test Cases - Sprint WW02 (Marian-Virgil)
- SAIL-820: Debug & fix failed test cases in SAIL-493 (HueyLi)
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-2745: randomly_failing_tests list: Investigate / root-cause camera-perspective intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests camera-perspective
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/15: Test that the user can manage camera intrinsics

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Launch the Demo sceneClick on camera1Click on the Advanced tabScroll down and verify that the following parameters can be edited: Intrinsics fx, Intrinsics fy, Intrinsics cx, Intrinsics cy, Distortion k1, Distortion k2, Distortion k3, Distortion p1, Distortion p2Verify that parameters entered above persist across a save and refreshTest PASSES if steps 4 and 5 are verified.

### Test requirements mapping

- SAIL-1297: Update test case SAIL-105 to properly test updated camera intrinsics edit page
- SAIL-1155: Re-enable SAIL-105 test for managing camera intrinsics
- FAREQ-111: System must automatically determine the camera pose
- SAIL-2362: Remove Tests Failing Due to Code Changes
- SAIL-105: Test that the user can manage camera intrinsics
- SAIL-2645: Fix camera-intrinsics test
- SAIL-1538: Enable Markerless Auto Camera Calibration
- SAIL-3104: Documentation for how camera instrinsics and distortion is handled
- SAIL-9: 3D Pathfinding [2022.1 Release]
- FAREQ-67: The user shall be able to configure the camera intrinsics (focal length and resolution).
- SAIL-305: Automate Test Cases - Sprint WW02 (Marian-Virgil)
- ITEP-74993: [Kubernetes][Cameras] Cannot manually change and save camera settings
- ITEP-74994: Unable to edit intrinsic/distortion parameters

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests camera-intrinsics
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/16: Test that cameras identify as offline until data is received

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Launch the Demo sceneObserve the cameras and verify that cameras not receiving data identify as offline (by default camera3 is offline, with camera1 and camera2 sending data)Test PASSES if camera3 has a "camera offline" label while camera1 and camera2 show a snapshot.

### Test requirements mapping

- FAREQ-69: The system shall identify a camera as offline until data is received.
- SAIL-327: Automate test cases - sprint WW04 (Marian)
- SAIL-2740: randomly_failing_tests list: Investigate / root-cause camera-status intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. selenium/runtest selenium/run-all-services.yml coverage run -m -a --omit /dist-packages/ pytest selenium/test_sail107_camera_status.py --password=admin123

## Vision_AI/SceneScape/ADMIN/17: Test that the out-of-box Demo scene is operating at first build

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Follow the build instructions for the system and open the UI in a web browserLogin with the "admin" user and the SUPASS you provided at build timeVerify that a scene called Demo is visibleVerify that dots representing people are moving on the sceneClick on the "Live view" toggle and verify that video frames are showing and updatingTest passes if steps 3-5 are verified.

### Test requirements mapping

- SAIL-616: Automate test cases - WW24 sprint(Marian)
- SAIL-824: Debug & fix failed test cases in SAIL-493 (Marian)
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- FAREQ-73: When a new instance of SAIL is brought up, Percebro instances are running with no critical errors.
- FAREQ-77: The system shall map detected {Object(s)} to a {Scene Graph}.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- SAIL-108: Test that the out-of-box Demo scene is operating at first build
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-2757: out-of-box sometimes fails to detect objects
- FAREQ-71: The system shall provide an out-of-the box scene with cameras, stored videos and associated database, and configuration files to make out-of-box experience as easy as possible.
- ITEP-73425: DLStreamer adapter causes pipeline failure without NTP

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests out-of-box

# make -C tests out-of-box-no-ntp

- Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/18: Test that only a superuser can perform CRUD functions on scenes, cameras, and sensors

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Launch the system and log in as adminNavigate to the Demo sceneInspect the UI and verify that the following buttons or links are visible (you may have to click through various tabs): Edit Demo (icon), Delete Demo (icon), Manage camera1 (icon), Delete camera1 (icon), +New Sensor, +New Region, +New TripwireClick on the Admin link in the top menuIn the Admin interface, click Add next to UsersIn the "Username" field enter "testuser"Enter the same strong password in the two password fieldsClick save, then close the browser tabFrom the original interface, click Log OutFrom the login page, enter "testuser" as the username and the strong password you created as the passwordNavigate to the Demo sceneInspect the UI and verify that that the following buttons are NOT visible (you may have to click through various tabs): Edit Demo (icon), Delete Demo (icon), Manage camera1 (icon), Delete camera1 (icon), +New Sensor, +New Region, +New TripwireVerify that the "Admin" link is NOT shown in the menuVerify that no other means to create, update, or delete system elements are available in the UI across the following pages: Home, Cameras, SensorsTest passes if steps 3, 12, 13, and 14 are verified.

### Test requirements mapping

- SAIL-2747: randomly_failing_tests list: Investigate / root-cause superuser-crud-operations intermittent failures.
- FAREQ-76: When functionality is changed at the system level (CRUD functions), a superuser shall enable the changes.
- SAIL-474: Automate Test Cases - WW16 (Chandresh)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests superuser-crud-operations
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/19: As a user I should be able to successfully upload custom scene maps that are in .glb format

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- FAREQ- 130 When a user attempts to upload a custom scene map generated using 3rd party SW, the system shall allow the user to successfully upload custom scene maps that are in gltf format.

### Test requirements mapping

- SAIL-848: Test-Manual Camera Calibration
- SAIL-1310: MANUAL CAMERA CALIBRATION (+)
- FAREQ-109: System must support 3rd party scene maps in GLTF format
- FAREQ-130: System shall allow user to successfully upload custom scene maps that are in GLTF format
- SAIL-1269: Directory not empty error on TC_SAIL-874 causes test failure
- SAIL-2384: Fix delete-sensor-mqtt test
- SAIL-2739: broken_tests list: Investigate / root-cause upload-3d-glb-file failure.
- SAIL-2150: tests for upload and view 3d glb are broken

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests upload-3d-glb-file
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/20: Manual Camera Calibration UI

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Users should be able to successfully set and save camera pose settings via Manage Camera interface for each camera on a scene. The camera pose setting may be set via manually placing colored dots in both video and map perspective or entering parameters

Expected Results: The system must store the camera pose settings, saved by user, in the database and display in the UI the settings last saved for a camera until they are edited and saved again. When calibration is saved, all calibrated pages should reflect these settings.

Note(s):
1 There are currently two ways to calibrate. Via manual placement of colored dots or entering of parameters. Both ways should be tested. If entering parameters, boundary values and equivalence partitioning should be used.
2 E.g., tester should verify parameters are saved via logging out of application and logging back in, navigating to different page, and returning to calibration management page, etc.
3 System should be stressed for maximum number of cameras (Scalability and Stress test)

### Test requirements mapping

- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- FAREQ-131: System must allow user to manually estimate the camera pose
- SAIL-1310: MANUAL CAMERA CALIBRATION (+)
- SAIL-848: Test-Manual Camera Calibration
- SAIL-1068: Save camera calibration results in 500 internal server
- SAIL-935: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-2752: randomly_failing_tests list: Investigate / root-cause manual-camera-calibration intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automated execution: make -C tests manual-camera-calibration
   For manual steps: see below
1. Log into SceneScape web app
1. Enter calibration parameters by placing pairs of dots on both camera and scene views
1. Save Calibration
1. Verify calibration parameters are saved in persistent storage
1. Repeat steps for each camera

## Vision_AI/SceneScape/ADMIN/21: Test that a user is able to upload to view and use a custom scene map that is in .glb format

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- The system shall allow the user to view uploaded 2D/3D objects formatted in .glb format

### Test requirements mapping

- FAREQ-110: System must generate the uploaded scene on the user interface
- SAIL-1056: Scene files in .obj format upload successfully to the Scenescape server but are not visible in the 3D scene.
- SAIL-1071: Implement automated test SAIL-904 verifying that .gltf files an be uploaded and are visible in the 3D scene.
- SAIL-2736: broken_tests list: Investigate / root-cause view-3d-glb-file failure.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests view-3d-glb-file
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/22: Test that a user can add and delete a 3D object

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that a user can add and delete a 3D object

### Test requirements mapping

- SAIL-996: User unable to delete object if no 3D model file added
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-905: Test that a user can add and delete a 3D object

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests add-delete-3d-object
   For manual execution: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1. Check adding 3D object:Log into SceneScape web appClick on Object LibraryUpload a 3D fileSave Object
1. Check deleting 3D object:Navigate to Objects Library and click delete a 3D object

## Vision_AI/SceneScape/ADMIN/23: User should be able to save the update of a 3D object

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- User should be able to save the update of a 3D object

Note(s):
1 Tester should verify parameters are saved via logging out of application and logging back in, navigating to different page, and returning to calibration management page, etc.

### Test requirements mapping

- SAIL-1072: As a tester, I would like to test 3D object update
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-2743: randomly_failing_tests list: Investigate / root-cause object-crud intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests object-crud
   For manual execution: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1.
1. Log into SceneScape web app
1. Navigate to Objects Library and click on wrench to edit a 3D object
1. Edit the settings for the 3D object and save

## Vision_AI/SceneScape/ADMIN/24: As a user if I delete a ROI MQTT publishing for that ROI should stop.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that if a ROI is deleted the MQTT server will stop publishing info on that ROI.
  Procedure:
  (1) Create ROI.
  (2) Delete ROI.
  (3) Start collecting MQTT messages
  (4) Run for long enough for a moving object to enter the ROI.
  (5) Check MQTT messages to verify that the deleted ROI is no longer publishing.

### Test requirements mapping

- SAIL-998: After deleting a ROI from a scene MQTT messages for the ROI continue to be published.
- SAIL-1108: As a tester, I would like to test delete a ROI MQTT
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-2742: randomly_failing_tests list: Investigate / root-cause group intermittent failures
- ITEP-73442: Cannot create Region of Interest

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests delete-roi-mqtt
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/25: As a user if I delete a Tripwire MQTT publishing for that Tripwire should stop.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that if a Tripwire is deleted the MQTT server will stop publishing info on that Tripwire.

### Test requirements mapping

- SAIL-999: After deleting a Tripwire from a scene MQTT messages for the Tripwire continue to be published.
- SAIL-1075: As a tester, I would like to test delete a Tripwire MQTT
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-2385: Fix delete-tripwire-mqtt test
- SAIL-2541: MQTT Tripwire events are triggered after removing a tripwire
- FAREQ-60: The system shall allow the user to delete one or more directional lines over the scene to eliminate tripwires.
- FAREQ-59: The system shall allow the user to update one or more directional lines over the scene to redefine tripwires.
- FAREQ-57: The system shall allow the user to create one or more directional lines over the scene to define tripwires.
- FAREQ-58: The system shall allow the user to view/read one or more directional lines over the scene to define tripwires.
- ITEP-73443: Cannot create Tripwire

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests delete-tripwire-mqtt
   For manual execution: see below
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`
1. Create Tripwire
1. Delete Tripwire
1. Start collecting MQTT messages
1. Run for long enough for a moving object to trip the Tripwire.
1. Check MQTT messages to verify that the deleted Tripwire is no longer publishing.

## Vision_AI/SceneScape/ADMIN/26: As a user if I delete a sensor MQTT publishing for that sensor should stop.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- As a user if I delete a sensor MQTT publishing for that sensor should stop.

### Test requirements mapping

- SAIL-1252: Functional test delete-sensor-mqtt SAIL-997 does not work
- SAIL-982: After deleting a sensor from a scene MQTT messages for the sensor continue to be published.
- SAIL-1074: As a tester, I would like to test delete a sensor MQTT
- SAIL-937: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-997: As a user if I delete a sensor MQTT publishing for that sensor should stop.
- SAIL-2384: Fix delete-sensor-mqtt test
- SAIL-2733: Sensor with Circle measurement doesn't publish any event

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests delete-sensor-mqtt
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/27: Test that the "Live View" button in a scene works.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- This test assumes that  a demo scene is running and that Live View is initially off.
  Procedure:
  (1) Take a screenshot cropped to the Cameras box -&gt; img_1
  (2) Turn on "Live View". This updates the Camera box layout.
  (3) Take a screenshot cropped to the Cameras box -&gt; img_2
  (4) Wait enough time for the video streams to update significantly.
  (5) Take a screenshot cropped to the Cameras box -&gt; img_3
  (6) Check that (img_1 != img_2) and (img_2 != img_3)

### Test requirements mapping

- SAIL-942: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-2749: randomly_failing_tests list: Investigate / root-cause live-view-button intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests live-view-button
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/28: Test that the "Show Telemetry" button in a scene works.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- This test assumes that a demo scene is running and that Show Telemetry is initially off.
  Procedure:
  (1) Take a screenshot cropped to a camera header bar. &gt; img_1  (Should have a " -" in the right corner)
  (2) Store in the memory the initial value for &lt;span class="float-right rate" id="rate-camera1"&gt;--&lt;/span&gt;. -&gt; fps_check1
  (3) Turn on "Show Telemetry".
  (4) Take a screenshot cropped to a camera header bar. -&gt; img_2  (Should have a "#.# FPS" in the right corner)
  (5) Store in the memory the value for "Show telemetry" On: &lt;span class="float-right rate" id="rate-camera1"&gt;13.5 FPS&lt;/span&gt;. -&gt; fps_check2
  (6) Check that (fps_check1 != fps_check2)
  (7) Check that (img_1 != img_2)

### Test requirements mapping

- SAIL-942: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-1015: Test that the "Show Telemetry" button in a scene works.
- SAIL-2738: broken_tests list: Investigate / root-cause show-telemetry-button failure.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests show-telemetry-button
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/ADMIN/29: Test non-superuser account permissions

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that general user can access functionality per the permission configured in the admin module.
  Test that general user can ONLY access functionality per permissions configured in he admin module.

### Test requirements mapping

- SAIL-1106: Test non-superuser account permissions
- SAIL-2343: User without sufficient permissions is able to perform CRUD operations from 3D UI
- SAIL-1900: 3D UI must have parity with 2D UI
- SAIL-2350: Run Manual Tests for 2023.4

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Create a new user with no admin privileges from the scenescape admin panel
   - Test data: `Click on the "Admin" button. Create a new user using the "Add" button the save it.`
1. Logout and log back in as the new user
1. Observe that the options to edit the scene, camera etc. settings is disabled from 2D UI
1. Go to 3D UI and try to perform any CRUD operation and they are limited just like in the 2D one.

## Vision_AI/SceneScape/ADMIN/30: Verify API handling of is_active, is_staff, is_superuser fields for creating a new user

**Affected Versions:**

### Test summary

- This test case verifies that the API parameter names for creating a new user are aligned with the model fields and that the API correctly handles user permissions as individual boolean fields (is_active, is_staff, is_superuser).
  The test ensures that the API documentation and implementation are consistent, with parameter names matching the actual field names expected by the API.

Steps:

1. GET TOKEN: curl --location --insecure -X POST -d "username=admin&amp;password=&lt;password&gt;" https://localhost/api/v1/auth
2. Use token to create a new user: curl --location --insecure -X POST -H "Content-Type: application/json" -H "Authorization: Token &lt;token&gt;" -d '{"username": "usr61", "password": "usr61", "first_name": "Firstname2", "last_name": "Lastname2", "email": "usr61@mycompany.com", "scene": "16fd2706-8baf-433b-82eb-8c7fada847da", "is_active":false, "is_staff": false, "is_superuser": true}' "https://localhost/api/v1/user"
3. Verify (is_active==false, is_staff==false, is_superuser==true) fields values: curl --location --insecure -X GET -H "Content-Type: application/json" -H "Authorization: Token &lt;token&gt;" "https://localhost/api/v1/user/usr61"
4. Change fields, e.g.: curl --location --insecure -X PUT -H "Content-Type: application/json" -H "Authorization: Token &lt;token&gt;" -d '{"is_active": true, "is_staff": true, "is_superuser": true}' "https://localhost/api/v1/user/usr61"
5. Verify (is_active==true, is_staff==true, is_superuser==true) fields values: curl --location --insecure -X GET -H "Content-Type: application/json" -H "Authorization: Token &lt;token&gt;" "https://localhost/api/v1/user/usr61"

### Test requirements mapping

- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.
