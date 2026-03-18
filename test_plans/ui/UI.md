# Vision_AI/SceneScape/UI Tests: Test Suite

## Test suite requirements mapping

- FAREQ-134: System must allow user to upload 3D Scene map only in GLTF format
- FAREQ-242: API documentation must be made available with the software package
- FAREQ-387: The system must provide a method of publishing undecorated frames.
- FAREQ-43: The user shall be able to add a new camera that must be assigned to a scene.
- FAREQ-475: The system must support models that output data for 3D object detections.
- FAREQ-48: The user shall be able to view the scene and its corresponding cameras.
- FAREQ-77: The system shall map detected {Object(s)} to a {Scene Graph}.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- FAREQ-80: When the system detects an {Object(s)}, the system shall track the location of the detected {Object(s)} in a {Scene Graph}.
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- ITEP-73577: Unable to save scene pose after update in 3D UI
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-73646: Sensor with circle or poly region fails to load in 3D UI
- ITEP-73725: Object category change does not reflect without web page refresh
- ITEP-79163: [Kubernetes][API][UI] Cannot import a scene when deployed on Kubernetes
- ITEP-80141: [Docker][API][UI] Importing a scene results in Server Error (500) on Docker
- ITEP-81834: [Kubernetes][API] Adding camera with minimal payload crashes kubeclient during pipeline generation
- ITEP-81916: Scene Hierarchy: 3D UI View displays only the parent scene
- ITEP-82254: 3D UI markerless autocalibration button disabled
- ITEP-83215: No Parent-Child scene relation set when importing zip file
- SAIL-1088: Test child scene(s) aggregation
- SAIL-1110: Test glb validator when file is corrupted
- SAIL-1285: User should only upload 3d scene map files in gLTF binary (.glb) format
- SAIL-1309: SCENE CONTROLLER: CHILD SCENES (+)
- SAIL-1317: Parent scene doesn't update after child scene creation
- SAIL-1538: Enable Markerless Auto Camera Calibration
- SAIL-1597: Test user can manage and control the cameras position in 3D UI
- SAIL-1644: Camera in 3D calibration UI goes offline after making updates
- SAIL-1655: UI: Test 3D Tripwire
- SAIL-1656: UI: Test 3D ROI
- SAIL-1663: UI - Test 3D Camera Controls Panel
- SAIL-1665: UI - Test that 3D gltf scene file is uploaded and that tracked objects are present in the 3D UI.
- SAIL-1678: Test and update 3D ROI, Tripwire and Sensor
- SAIL-1682: Test 3D UI Scene Camera
- SAIL-1683: Test 3D UI Camera Translate and Rotate
- SAIL-1685: Test 3D UI Project Frame
- SAIL-1686: Test 3D UI Pause Video
- SAIL-1687: Test 3D UI Opacity
- SAIL-1765: 3D UI Camera Calibration for Queuing scene doesn't work as expected
- SAIL-1804: [Auto Camera Calibration] Validation and Test Plan
- SAIL-1829: Automate manual test cases
- SAIL-1860: Tests for 3D View
- SAIL-1900: 3D UI must have parity with 2D UI
- SAIL-1999: Enable placement of 3D scene object/.glb in 3D UI
- SAIL-2007: 3D Object Detection
- SAIL-2011: Auto calibrate button in 3D UI should indicate when background processing is happening - whether register step or localize step
- SAIL-2133: Modify 3D UI to subscribe to new cameras (topic) created in runtime
- SAIL-2139: GUI support for cuboid with translation, rotation, and size
- SAIL-2177: Refresh 3D UI once the intrinsics information is available for newly created camera
- SAIL-2192: Manual Tests for 3D UI Redesign Q4 2023 Feature updates - WW43 Release
- SAIL-2215: Tests the 3D UI translation and rotation controls implemented in SAIL-1999.
- SAIL-2216: Test that cameras defined in the docker_compose.yml and added in the 3D UI come online without refreshing the brower.
- SAIL-2237: Manual Tests for 3D Object Detection Q4 2023 Feature updates - WW47 Release
- SAIL-2258: Test that changing a camera name in the 3D scene view does not take the camera offline in the "Configure Scene" view
- SAIL-2260: Test that changes in a camera FOV in docker-compose.yaml is reflected in the 3D UI.
- SAIL-2263: Test that uploading polycam data returns a message indicating success or failure.
- SAIL-2264: Successfully uploading polycam data does not return a visible successful upload message.
- SAIL-2266: Check that markerless autocalibration displays an in progress message.
- SAIL-2339: Test that objects translation and rotation is displayed in the 3D UI
- SAIL-2345: Run Manual Tests for 2023.4
- SAIL-2380: Delete camera should show confirmation dialog in 3D UI
- SAIL-2407: Out of the box demo improvements
- SAIL-2454: As a user, I want to read the readme docs via the web server
- SAIL-2501: Parent scene republishes the analytics from child in its coordinate space
- SAIL-2612: Implement 3D bounding box projection to map surface logic in scene controller
- SAIL-2646: Fix child-scenes test
- SAIL-2666: Fix Broken test for 3D Camera Control Panel
- SAIL-2716: User can visualize child scene sensor events and analytics in parent.
- SAIL-2728: When category of an object changes the 3D UI must reflect the change without refresh
- SAIL-2734: broken_tests list: Investigate / root-cause 3d-camera-control-panel failure.
- SAIL-2735: broken_tests list: Investigate / root-cause 3d-ui-calibration-points failure.
- SAIL-2741: randomly_failing_tests list: Investigate / root-cause 3d-scene-control-panel intermittent failures.
- SAIL-2742: randomly_failing_tests list: Investigate / root-cause group intermittent failures
- SAIL-2764: Review AI-model-integration.md for UX Plan
- SAIL-2808: Review integration.md for UX Plan
- SAIL-2949: [DOC] Format and style wrong in documentation page - Creating a Live Scene
- SAIL-2967: Open redirect on sign-in page
- SAIL-3016: When creating a camera in 3D UI, the name and the id dont match
- SAIL-3029: Modifying properties in Object library GUI is broken
- SAIL-3263: Update Architecture Diagram in documentation
- SAIL-3508: Documentation issues in the Web UI
- SAIL-3519: broken_tests list: automated release test cases
- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)
- SAIL-561: 3D UI
- SAIL-799: Web Interface (proxy for requirements traceability)
- SAIL-942: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-964: User can upload 3D scene map files in formats that are not glTF.

## Test suite setup

### Hardware Requirements

### Test suite prerequisites

- A current built version of SceneScape that has been started and is up with a Browser attached and logged in to the WebUI service.
- Existing scene where cameras can be added to
- Firefox installed on the testing machine.
  SceneScape is up and running correctly.
- Intel® SceneScape is installed and running.A parent scene and multiple child scenes are set up.Clients are connected to the Intel® SceneScape system and can subscribe to scene graph updates.
- Intel® SceneScape is installed and running.Two scenes are set up: "scene_1" with no cameras and "scene_2" with cameras.
- Intel® SceneScape is installed on two separate hosts.A parent scene and at least one child scene are set up and linked.The scene hierarchy is correctly configured according to the provided instructions.
- SceneScape should be up and running.
- Scenescape is up and running
- Scenescape is up and running.
- Scenescape must be up and running
- The following zip files are present in /workspace/tests/ui/test_media/:Retail-import.zipEmpty.zipInvalid.zipParent.zipIntersection-Demo.zipCleanly build Scenescape (make &amp;&amp; make setup_tests)

## Vision_AI/SceneScape/UI Tests/01: Test that scenescape only allow GLB 3D files uploads.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- 1. Add test steps with pre-conditions and post-conditions

2. Add test data
3. Add expected results
4. Code test if it can be automated
5. Add test to make file for automation tests suite
   Test PASSES if the above steps are all verified.

### Test requirements mapping

- FAREQ-134: System must allow user to upload 3D Scene map only in GLTF format
- SAIL-964: User can upload 3D scene map files in formats that are not glTF.
- SAIL-1285: User should only upload 3d scene map files in gLTF binary (.glb) format
- SAIL-942: Identify and add JIRA work items for WW48 and WW50 sprints before WW47.3 EOD
- SAIL-1110: Test glb validator when file is corrupted

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests upload-only-3d-glb-files
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/UI Tests/02: Verify Child Scene(s) Aggregation and Dynamic Scene Graph Management

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- This test case verifies that the Intel® SceneScape system can aggregate a parent scene and its child scenes to create a larger, holistic scene graph. The aggregated scene graph should be published to clients, allowing them to access and interact with the combined scene data. Additionally, the test case ensures that the system can manage dynamic changes to the scene graph, such as adding or removing child scenes, and update the aggregated scene graph accordingly.

### Test requirements mapping

- SAIL-1317: Parent scene doesn't update after child scene creation
- SAIL-1309: SCENE CONTROLLER: CHILD SCENES (+)
- SAIL-1088: Test child scene(s) aggregation
- SAIL-2646: Fix child-scenes test
- SAIL-2742: randomly_failing_tests list: Investigate / root-cause group intermittent failures

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests child-scenes
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/UI Tests/03: Test user can manage and control the cameras position in 3D UI

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-1597: Test user can manage and control the cameras position in 3D UI
- SAIL-561: 3D UI
- FAREQ-48: The user shall be able to view the scene and its corresponding cameras.

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Open SceneScape Web Interface in browser
1. Choose Queuing scene using "Configure Queuing Scene" button
1. Press 3D button to view scene in 3D
1. Expand settings for Camera settings and use default camera, atag-qcam2. Expand settings for atag-qcam2 camera to view all settings
1. Press "toggle rotate/translate" button to view differences
1. Click a camera to show transform controls and rotate the camera using the 3D controls
1. Modify Pose(extrinsics) coordinates for atag-qcam2 camera to move this

## Vision_AI/SceneScape/UI Tests/04: UI: Test 3D Tripwire

**Affected Versions:** 2024.2

### Test summary

- Stub for Addo, Derrick to fill in.

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-1678: Test and update 3D ROI, Tripwire and Sensor
- SAIL-1655: UI: Test 3D Tripwire
- SAIL-561: 3D UI

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify 3D tripwire changes color with slider
1. Verify 3D tripwire visibility when show is toggled
1. Verify 3D tripwire label visibility when show is toggled
1. Verify 3D tripwire height changes with slider

## Vision_AI/SceneScape/UI Tests/05: UI: Test 3D ROI

**Affected Versions:** 2024.2

### Test summary

- Stub for Addo, Derrick to fill in.

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-1656: UI: Test 3D ROI
- SAIL-561: 3D UI
- SAIL-1678: Test and update 3D ROI, Tripwire and Sensor

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify 3D roi changes color with slider
1. Verify 3D roi visibility when show is toggled
1. Verify 3D roi opacity with slider
1. Verify 3D roi label visibility when show is toggled
1. Verify 3D roi height changes with slider

## Vision_AI/SceneScape/UI Tests/06: UI: Test four point calibration in 3D UI

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- This is to test the manual calibration feature in the 3D UI via dragging of calibration points/dots.
  Note: Before you can set the camera calibration points you have to toggle "project frame". To set the calibration points double click in the 3D UI. Then the toggle "calibration points visibility" should function as expected.

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-1765: 3D UI Camera Calibration for Queuing scene doesn't work as expected
- SAIL-561: 3D UI
- SAIL-2735: broken_tests list: Investigate / root-cause 3d-ui-calibration-points failure.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests 3d-ui-calibration-points
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/UI Tests/07: UI - Test 3D Scene Control Panel

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- This is to test what is referred to as the Scene Control Panel in the 3D UI.
  In this panel a user should be able to perform the following:
  toggle floor plane,
  navigate to scene details,
  view scene in 2D view or 3D view
  reset the 3D view to it's original state after repositioning.

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-561: 3D UI
- SAIL-2741: randomly_failing_tests list: Investigate / root-cause 3d-scene-control-panel intermittent failures.
- SAIL-3519: broken_tests list: automated release test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/UI Tests/08: UI - Test 3D Camera Controls Panel

**Affected Versions:** 2024.2

### Test summary

- Check that the camera toggle and slider controls for the 3D UI has the expected results. (This ticket will likely need to be broken into multiple tickets.)
  Scene CameraToggle Rotate/TranslateCalibration Points Visible - deprecated featureProject FramePause VideoOpacity

### Test requirements mapping

- SAIL-1687: Test 3D UI Opacity
- SAIL-1682: Test 3D UI Scene Camera
- SAIL-1685: Test 3D UI Project Frame
- SAIL-1683: Test 3D UI Camera Translate and Rotate
- SAIL-1686: Test 3D UI Pause Video
- SAIL-1860: Tests for 3D View
- SAIL-1663: UI - Test 3D Camera Controls Panel
- SAIL-561: 3D UI
- SAIL-2666: Fix Broken test for 3D Camera Control Panel
- SAIL-2734: broken_tests list: Investigate / root-cause 3d-camera-control-panel failure.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/UI Tests/09: UI - Verify that tracked objects are present in the 3D UI

**Affected Versions:** 2024.2

### Test summary

- Test when a user a navigates to the 3D view for the demo scene they are presented with control panels and 3d scene loaded with the tracked objects present and moving on the scene.
  https://github.com/intel-innersource/applications.ai.scene-intelligence.opensail/blob/dev/docs/3D-UI.md

### Test requirements mapping

- SAIL-1860: Tests for 3D View
- SAIL-1665: UI - Test that 3D gltf scene file is uploaded and that tracked objects are present in the 3D UI.

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify that the Camera controls in panel on the right.
1. Verify that the cameras that belong to this scene are present
1. Verify that the tracked objects moving on the scene.
1. Verify that the scene control panel on top left.
1. Verify that the 3D scene uploaded as a glb/gltf file is in the background.

## Vision_AI/SceneScape/UI Tests/10: Test 3D UI Pause Video

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Note: Currently objects are still tracked when video is paused. Until updated by th dev team about this assume it is a feature.

### Test requirements mapping

- SAIL-1686: Test 3D UI Pause Video
- SAIL-1829: Automate manual test cases
- SAIL-561: 3D UI

### Test priority

- P4

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Login into SceneScape via a webbrowser and click on the 3D Queuing Scene
1. Toggle off "show tracked objects"
1. Toggle on "project frame".
1. Take screenshot_1.
1. Toggle on "pause video".
1. Take screenshot_2.
1. Wait a second.
1. Take screenshot_3.
1. Compare screenshot_1 and screenshot_2.
1. Compare screenshot_2 and screenshot_3.

## Vision_AI/SceneScape/UI Tests/11: Tests the 3D UI translation and rotation controls implemented in SAIL-1999.

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Tests the 3D UI translation and rotation controls implemented in SAIL-1999.

 

1. Open the Update Scene page and upload any .glb file. (a raw.glb file for the Queuing scene attached)
2. Open the scene's 3D UI.
3. In the "Controls Panel", open the "Scene Settings" drop down menu.
4. Toggle the rotation/translation switch and check that the corresponding scene controls are displayed.
5. Check that the rotation controls rotate the scene object.
6. Check tat the translation controls move the scene object.
7. Check that the rotation and translation controls change the pose as expected.
8. Check that if the scene object is saved and the page is reloaded, the object is in the same position as it was saved in.

### Test requirements mapping

- SAIL-1999: Enable placement of 3D scene object/.glb in 3D UI
- SAIL-2215: Tests the 3D UI translation and rotation controls implemented in SAIL-1999.
- SAIL-2192: Manual Tests for 3D UI Redesign Q4 2023 Feature updates - WW43 Release
- SAIL-561: 3D UI
- ITEP-73577: Unable to save scene pose after update in 3D UI

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Open the Update Scene page and upload any .glb file (a raw.glb file for the Queuing scene attached)
1. Open the scene's 3D UI
1. In the "Controls Panel", open the "Scene Settings" drop down menu
1. Toggle the rotation/translation switch and check that the corresponding scene controls are displayed
1. Check that the rotation controls rotate the scene object.
1. Check tat the translation controls move the scene object
1. Check that the rotation and translation controls change the pose as expected.
1. Check that if the scene object is saved and the page is reloaded, the object is in the same position as it was saved in.

## Vision_AI/SceneScape/UI Tests/12: Test that cameras defined in the docker_compose.yml and added in the 3D UI come online without refreshing the browser.

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Test that camera's defined in the docker_compose.yml and added in the 3D UI come online without refreshing the brower.

 
Test Steps:

1. Add a 3rd camera to the retail scene in the docker compose file.
2. Bring up Scenescape.
3. In the 3D UI accessed via Firefox, add a 3rd camera, making sure to save the added camera.
4. The 3rd camera should immediately be online (green dot).

### Test requirements mapping

- SAIL-2133: Modify 3D UI to subscribe to new cameras (topic) created in runtime
- SAIL-561: 3D UI
- SAIL-2216: Test that cameras defined in the docker_compose.yml and added in the 3D UI come online without refreshing the brower.
- FAREQ-43: The user shall be able to add a new camera that must be assigned to a scene.

### Test priority

- P4

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/UI Tests/13: Test that changing a camera name in the 3D scene view does not take the camera offline in the "Configure Scene" view

**Affected Versions:** 2024.2

### Test summary

- 1. Go to the 3D view of a scene.

2. Change the name of a camera and save those changes.
3. Click on the wrench icon or "Configure Scene" button.
4. In the "Configure Scene" page check that the camera with the new name is still online.
5. Verify that the settings are still valid and the calibration still persists

### Test requirements mapping

- SAIL-1644: Camera in 3D calibration UI goes offline after making updates
- SAIL-2258: Test that changing a camera name in the 3D scene view does not take the camera offline in the "Configure Scene" view
- SAIL-561: 3D UI
- SAIL-1900: 3D UI must have parity with 2D UI
- SAIL-799: Web Interface (proxy for requirements traceability)

### Test priority

- P4

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Go to the 3D view of a scene.
1. Change the name of a camera and save those changes.
1. Click on the wrench icon or "Configure Scene" button.
1. In the "Configure Scene" page check that the camera with the new name is still online.

## Vision_AI/SceneScape/UI Tests/14: Test that changes in FOV of camera on camera configuration page is reflected in the 3D UI.

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that the FOV/(fx, fy) changes to a camera is reflected in 3D UI

### Test requirements mapping

- SAIL-2260: Test that changes in a camera FOV in docker-compose.yaml is reflected in the 3D UI.
- SAIL-1900: 3D UI must have parity with 2D UI
- SAIL-561: 3D UI
- SAIL-2177: Refresh 3D UI once the intrinsics information is available for newly created camera

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Check default state:enter 3D UI for Queuing scenechoose one of the camerasfor the chosen camera tick 'project frame' and check intrinsic values
1. Go to the Queuing scene configuration page, and enter configuration of the previously chosen camera
1. Modify settings:Unlock fx / fyChange values arbitrarily Save
1. Go back to 3D UI scene and repeat step 1.

## Vision_AI/SceneScape/UI Tests/15: Test that uploading polycam data returns a message indicating success or failure.

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Test how polycam behaves in different scenarios

### Test requirements mapping

- SAIL-2345: Run Manual Tests for 2023.4
- SAIL-2264: Successfully uploading polycam data does not return a visible successful upload message.
- SAIL-2263: Test that uploading polycam data returns a message indicating success or failure.

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Open the scene edit page in the web UI (pencil ICON)
1. Change the calibration type
   - Test data: `Select Calibration Type = Markerless`
1. Upload the files listed below, one by one, in the "Polycam data" field and submit the changes by clicking the button "Save Scene Upload" at the bottom of the page
   - Test data: `Note: Aug1at12-51PM-poly.zip is available in the attachments. Other examples are modifications of this file.`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `Aug1at12-51PM-poly.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_cameras.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_depth_folder.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_depth_image.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_glb.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_image_folder.zip`
1. Check that the message after the upload is complete matches the expected message.
   - Test data: `one_without_meshinfo.zip`

## Vision_AI/SceneScape/UI Tests/16: Check that markerless autocalibration displays an in progress message.

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- The file to be uploaded in this test is found in the attachments
  More details on autocal procedure can be found here on github

### Test requirements mapping

- SAIL-2011: Auto calibrate button in 3D UI should indicate when background processing is happening - whether register step or localize step
- SAIL-2266: Check that markerless autocalibration displays an in progress message.
- SAIL-1804: [Auto Camera Calibration] Validation and Test Plan
- SAIL-2407: Out of the box demo improvements
- SAIL-1538: Enable Markerless Auto Camera Calibration
- FAREQ-387: The system must provide a method of publishing undecorated frames.
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- ITEP-82254: 3D UI markerless autocalibration button disabled
- ITEP-82254: 3D UI markerless autocalibration button disabled

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Open the scene update page in the web UI for the Queuing scene (pencil icon)
1. Select Calibration Type = Markerless
1. Select the files listed in the description using the "Polycam data" field and save the form, starting the file upload.
   - Test data: `Upload the zip file: /share/SceneScape/test-data/markerless_data/Aug1at12-51PM-poly.zip`
1. Go to the 3D scene view and select a camera.
1. One may have to wait 6-7min for the auto calibrate button to "un-grey"
1. In the selected camera's drop down menu select "autocalibrate"
1. In the lower right of the screen a message should appear indicating that markerless autocalibration is processing and finished

## Vision_AI/SceneScape/UI Tests/17: Test that objects translation and rotation are correctly represented in SceneScape coordinate system

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- In the "queuing video" container specfied in docker-compose.yml set --camerachain=retail3dDownload SynthData.zip from attachmentsUnzip SynthData.zip on the server hosting Scenescape.Edit SynthData/publish_as_camera.py replacing the password with the Scenescapes browser container secret.Add cam2 to the Queuing scene in the docker-compose.yml.docker-compose upAdd cam2 in the Queuing scene 3D UI.Edit SynthData/synthData.py so that VISUALIZE=False and R_RATE = np.array([np.pi, np.pi, np.pi])/10Run synthData.py (synthDataLight.py is a simplified version that transforms and rotates a generated wireframe box instead of a GLB 3D object)Check the large box is spinning on 3 axes.Edit SynthData/synthData.py so that T_RATE = np.array([np.pi, np.pi, 4*np.pi])/3Run synthData.pyCheck the large box is being translated on 3 axes.

### Test requirements mapping

- SAIL-2139: GUI support for cuboid with translation, rotation, and size
- SAIL-2339: Test that objects translation and rotation is displayed in the 3D UI
- FAREQ-80: When the system detects an {Object(s)}, the system shall track the location of the detected {Object(s)} in a {Scene Graph}.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- FAREQ-77: The system shall map detected {Object(s)} to a {Scene Graph}.
- SAIL-2237: Manual Tests for 3D Object Detection Q4 2023 Feature updates - WW47 Release
- SAIL-2007: 3D Object Detection

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. In the "queuing video" container specfied in docker-compose.yml set --camerachain=retail3d
1. Download SynthData.zip from attachments
1. Unzip SynthData.zip on the server hosting Scenescape.
1. Edit SynthData/publish_as_camera.py replacing the password with the Scenescapes browser container secret.
1. Add cam2 to the Queuing scene in the docker-compose.yml.
1. docker-compose up
1. Add cam2 in the Queuing scene 3D UI.
1. Edit SynthData/synthData.py so that VISUALIZE=False and R_RATE = np.array([np.pi, np.pi, np.pi])/10
1. Run synthData.py (synthDataLight.py is a simplified version that transforms and rotates a generated wireframe box instead of a GLB 3D object)
1. Check the large box is spinning on 3 axes.
1. Edit SynthData/synthData.py so that T_RATE = np.array([np.pi, np.pi, 4*np.pi])/3
1. Run synthData.py
1. Check the large box is being translated on 3 axes.

## Vision_AI/SceneScape/UI Tests/18: View the documentation via the SceneScape Web UI

**Affected Versions:** 2024.1, 2024.2

### Test summary

- All Readme \*.md docs from the repository are viewable through the web UI of SceneScape.

### Test requirements mapping

- SAIL-2454: As a user, I want to read the readme docs via the web server
- FAREQ-242: API documentation must be made available with the software package
- SAIL-2764: Review AI-model-integration.md for UX Plan
- SAIL-2808: Review integration.md for UX Plan
- SAIL-2949: [DOC] Format and style wrong in documentation page - Creating a Live Scene
- SAIL-3263: Update Architecture Diagram in documentation
- SAIL-3508: Documentation issues in the Web UI

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. After logging in, select the 'Documentation' tab from the top navigation bar.
1. Select each entry from the left navigation panel and check if the documentation is shown correctly.

## Vision_AI/SceneScape/UI Tests/19: Object category change gets reflected without web page refresh

**Affected Versions:** 2024.1, 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-2728: When category of an object changes the 3D UI must reflect the change without refresh
- ITEP-73725: Object category change does not reflect without web page refresh

### Test priority

- P4

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Follow instructions for T647 to setup 3D Object Detection model
   - Test data: `A video file that has atleast two categories of objects`
1. Add assets in Object Library for each category of object. Either a color for the default 3d box or a glb asset to represent that object.
1. Ensure that your the same object changes "object category" over its lifetime in camera view
   - Test data: `The category change can be artificially induced via mqtt. In fact, the whole test can be verified without even running 3D Object detection model. Just mock the input from percebro using percsim and change the category of an object overtime.`

## Vision_AI/SceneScape/UI Tests/20: 3D Object Detection is projected to scene map

**Affected Versions:** 2024.1, 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-2612: Implement 3D bounding box projection to map surface logic in scene controller
- FAREQ-475: The system must support models that output data for 3D object detections.
- SAIL-2007: 3D Object Detection

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Follow instructions in T647 to run a 3D Object Detection and observe where the current objects are displayed. Some are below the map and some are above.
1. Edit the object library to specify an asset for object categories being detected. Set "project_to_map" to yes for one or more categories.

## Vision_AI/SceneScape/UI Tests/21: UI Analytics Hierarchy - Visualize Child Scene Analytics

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the ability of the Intel® SceneScape system to visualize analytics from a child scene in the parent scene's user interface (UI). It ensures that events, regions of interest (ROIs), tripwires, and sensors created in the child scene are correctly propagated and displayed in the parent scene's UI, allowing for a unified view of the analytics hierarchy.

### Test requirements mapping

- SAIL-2716: User can visualize child scene sensor events and analytics in parent.
- SAIL-2501: Parent scene republishes the analytics from child in its coordinate space

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Ensure that the preconditions are met
   - Test data: `Set up two scenes: "scene_1" with no cameras and "scene_2" with cameras.Ensure that Intel® SceneScape is running with both scenes.`
1. Create a local child link
   - Test data: `Link "scene_2" as a local child of "scene_1".Verify that the child link is created with the correct parent and child attributes.`
1. Create ROI, tripwire, and sensor in the child scene
   - Test data: `In the child scene ("scene_2"), create an ROI, a tripwire, and a sensor.Verify that events are observed in the child scene over MQTT.`
1. Visualize analytics in the parent scene UI
   - Test data: `Verify that the ROI, tripwire, and sensor elements are present on the parent scene's web page.`
1. Visualize new ROIs, tripwires, and sensors
   - Test data: `Publish test events on the child scene's event topic:Publish a test event for region type "region" with scene = child.Publish a test event for region type "tripwire" with scene = child.Publish a test event for region type "region" with event type as value for sensor analytics and scene = child.Verify that the same events are republished on the parent scene.Verify that the elements in the UI are created for the published test events.`
1. Verify the propagation of analytics elements
   - Test data: `Verify that an ROI with the same attributes is created in the parent scene.Verify that a tripwire with the same attributes is created in the parent scene.Verify that a sensor with the same attributes is created in the parent scene.`

## Vision_AI/SceneScape/UI Tests/22: Sane login redirect when exploitable link is used

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Make sure that SceneScape will automatically redirect you to the index page when someone will try to exploit the login mechanism to send you to a different page.

### Test requirements mapping

- SAIL-2967: Open redirect on sign-in page

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Open a Firefox browser and replace the next hop to be a different site instead of the root directory.

NOTE: The Chrome is blocking by default the redirect via the Content Security Policy directive.

- Test data: `Replace / with http://malwaresite.biz.ru:

http://scenescape-customer.example.com/sign_in/?next=/
http://scenescape-customer.example.com/sign_in/?next=http://malwaresite.biz.ru

NOTE: The login page used for this example is http://scenescape-customer.example.com.`

1. Login with the correct credentials and see that you are redirected correctly to the SceneScape index page.

## Vision_AI/SceneScape/UI Tests/23: Asset 3D UI CRUD

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify the CRUD of object library via GUI.

Note: Model examples can be found in: https://github.com/KhronosGroup/glTF-Sample-Models/
The Duck.glb file can be used for this test: https://github.com/KhronosGroup/glTF-Sample-Models/blob/main/2.0/Duck/glTF-Binary/Duck.glb

### Test requirements mapping

- SAIL-3029: Modifying properties in Object library GUI is broken

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify OOB scene
   - Test data: `OOB retail scene`
1. Verify tracks in 3D UI
1. Verify the creation of object in object library
   - Test data: `Click object library from nav bar.Click New Object.
Case 1:Class name as "person1" , give a null value for x_size.Click Add New Object.Case 2:Class name as "person1" and default values of all other parameters.Click Add New Object.`
1. Verify the fields in object / asset 3D form toggle on condition
   - Test data: `Go to asset list with Object Library. Locate and select the "person" object.Expected fields in form : ['name', 'model_3d', 'mark_color', 'x_size', 'y_size', 'z_size',
'tracking_radius', 'project_to_map', 'rotation_from_velocity']Change the mark color to "#ffffff" (white).Click Update Object.Verify changes in the OOB scene in the 3D UI.`
1. Verify 3D model upload in objects
   - Test data: `Go to asset list with Object Library.Locate and select the "person" object.Upload a 3D model glb.New form should have fields : ['name', 'model_3d'', 'x_size', 'y_size', 'z_size', 'tracking_radius', 'project_to_map', 'rotation_from_velocity', 'scale', 'rotation_x', 'rotation_y', 'rotation_z', 'translation_x', 'translation_y', 'translation_z' ]Click Update Object.Verify changes in the OOB scene in the 3D UI.`

## Vision_AI/SceneScape/UI Tests/24: 3D UI View with All Items in Scene Using Scene Hierarchy

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the functionality of the 3D UI View in the Intel® SceneScape system, which displays all items in the scene using the scene hierarchy. It ensures that the 3D UI View correctly renders and displays the parent scene and its linked child scenes, allowing users to visualize and interact with the entire scene hierarchy.

### Test requirements mapping

- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-81916: Scene Hierarchy: 3D UI View displays only the parent scene

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Install SceneScape on two separate hosts
   - Test data: `Make sure that both SceneScape instances are up and running. Check the UI and #docker ps`
1. On the parent host, create a new scene or rename the existing "Retail" scene to "Parent_Retail" to serve as the parent scene.
   - Test data: `Go to "Scenes" and hit the "+ New Scene" button`
1. Link a child scene to the parent scene
   - Test data: `Click on the Parent Scene
Under the scene map click the "Children" tab u.
Click "+ Link Child Scene" button
Select the appropriate child scene from the dropdown menu.
Specify the transform type and child transform values.
Click "Add Child Scene" to link the child scene to the parent.`
1. In the parent scene, click the "3D" button to open the 3D UI View.
1. Verify that the 3D UI View displays the parent scene and all linked child scenes correctly.
1. Interact with the 3D UI View by navigating, zooming, and exploring the scene hierarchy.
1. Perform various actions or movements within the parent scene and linked child scenes.
1. Verify that the 3D UI View updates in real-time to reflect the changes in the scene hierarchy.

## Vision_AI/SceneScape/UI Tests/25: Camera creation in 3D scene configuration

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Make sure that the user is able to create a camera in the 3D UI interface.

### Test requirements mapping

- SAIL-3016: When creating a camera in 3D UI, the name and the id dont match

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Select any scene and enter the 3D configuration of it.
   - Test data: ``
1. Create a new camera named. Fill out the name 'A-BC-DE-123' and play around with the settings then click save.

## Vision_AI/SceneScape/UI Tests/26: Camera Deletion in 3D UI

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that camera deletion works as expected in 3D UI

### Test requirements mapping

- SAIL-2380: Delete camera should show confirmation dialog in 3D UI

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Navigate to the scenescape 3D UI and click add camera to add a new camera
1. Set the name of the camera to 'testcam' by entering that name in to the name field and save the camera
1. Click on 'delete camera' and click `cancel` when the confirmation window pops up
1. Click on 'delete camera' and click 'ok' when the confirmation window pops up

## Vision_AI/SceneScape/UI Tests/27: Verify user notification when adding a camera from a different scene during auto calibration

**Affected Versions:**

### Test summary

- This test case verifies that the system informs the user when an auto camera calibration is attempted with a camera from a different scene.
  Specifically, if the retrieval of a subset of matching frames from the raw polycam dataset has weak matches or none, the user should be notified that the camera "might not belong to this scene" and should not silently return poor localization results.
  Create a new scene or select a scene say Queuing.Edit the scene and change calibration type to markerless.Upload the polycam data zip file and save the scene updates.Take the camera from different scene and put it in the Queuing scene.Go to 3d ui of the scene and click auto calibrate button under camera settings.If there are good number of matches between camera and polycam data then auto calibration will work otherwise the user will be informed that camera might not belong to the scene and no auto calibration will work.
  Expected result:
  during the calibration attempt the message "Weak or unsufficient matches. This camera might not belong to this scene." was prompted in the 3D GUI.
  In addition a similar message appeared in a log of the camcalibration container:
  2024-12-09 13:32:01,850 - sscape.log - ERROR - Weak or insufficient matches. This camera might not belong to this scene.

### Test requirements mapping

- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/UI Tests/28: Scene import

**Affected Versions:**

### Test summary

- This test validates the behavior of the Scene Import under various conditions including successful imports, empty zip files, invalid zip files, duplicate scenes, and orphaned components. It ensures that the UI button correctly handles each scenario, returns appropriate responses, and links scene components as expected.

### Test requirements mapping

- ITEP-79163: [Kubernetes][API][UI] Cannot import a scene when deployed on Kubernetes
- ITEP-80141: [Docker][API][UI] Importing a scene results in Server Error (500) on Docker
- ITEP-81834: [Kubernetes][API] Adding camera with minimal payload crashes kubeclient during pipeline generation
- ITEP-83215: No Parent-Child scene relation set when importing zip file

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Connect to the scenescape app.
1. Verify default behavior:Click on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Retail-import.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Verify behavior when handling empty zip files:Click on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Empty.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Verify behavior when adding duplicate scene:Click on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Retail-import.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Verify local scene hierarchy behavior:Click on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Parent.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Verify behavior when adding scene with malformed JSON:Click on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Invalid.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Check Correct behavior of orphaned cameras/sensors:Delete 'Retail-import' sceneClick on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Retail-import.zip' -&gt; ImportAccept alerts concerning orphaned cameras/sensors
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Check correct behavior when adding larger fileClick on the '+ Import Scene' button -&gt; 'Choose File' -&gt; Select 'Intersection-Demo.zip' -&gt; Import
   - Test data: `Zip files present at scenescape\tests\ui\test_media`
1. Test cleanup - Remove scenes, cameras and sensors added during the test.

## Vision_AI/SceneScape/UI Tests/29: All sensor region shapes must be supported in 3D Visualization

**Affected Versions:**

### Test summary

- It should be possible to configure and visualize Sensor region (entire scene, circle, poly)

### Test requirements mapping

- ITEP-73646: Sensor with circle or poly region fails to load in 3D UI

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.
