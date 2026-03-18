# Vision_AI/SceneScape/Functional Tests: Test Suite

## Test suite requirements mapping

- FAREQ-16: Once built, the system shall not require an internet connection to operate.
- FAREQ-21: The system shall store the scene floorplan and its {metadata}.
- FAREQ-23: The user shall be able to edit the scene properties for an existing scene.
- FAREQ-241: The system must provide a standards-based REST API
- FAREQ-243: API must provide a list of objects by scene object type
- FAREQ-244: API must provide CRUD functions for all object types
- FAREQ-245: API must support token-based authentication
- FAREQ-24: The user shall be able to delete an existing scene.
- FAREQ-25: The system shall ask the user to confirm that the scene can be deleted.
- FAREQ-29: The user shall be able to add a new sensor that must be assigned to a scene.
- FAREQ-308: The system must support a scene to be a child of another scene on the same scene controller.
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- FAREQ-30: The system shall require sensor ID, sensor name, and parent scene data fields be populated for sensor creation.
- FAREQ-313: The system must provide a method for generating REST API tokens
- FAREQ-328: When ingesting data with longitude, latitude, altitude (LLA) and no cartesian location, the system must convert LLA into earth-centered earth-fixed (ECEF).
- FAREQ-330: The system shall provide the option to configure a scene to output latitude, longitude, altitude (LLA).
- FAREQ-346: The system must synchronize the processing of multiple video files.
- FAREQ-34: The user shall be able to view the scene and its corresponding sensors.
- FAREQ-352: The system must support model chaining where the output of one model is used as the input to the next model.
- FAREQ-363: The system must operate as a standalone, containerized microservice.
- FAREQ-366: The system must utilize ISO 8604 UTC format timestamps.
- FAREQ-36: The system shall ask the user to confirm that the sensor can be deleted.
- FAREQ-381: The system must publish results using JSON over MQTT.
- FAREQ-386: The system must decorate frames with detections and the current frame rate.
- FAREQ-41: The user shall be able to edit the configuration properties for an existing sensor.
- FAREQ-43: The user shall be able to add a new camera that must be assigned to a scene.
- FAREQ-44: When a camera is created, the user shall input the properties for camera ID, camera name and parent scene.
- FAREQ-469: The system must reidentify objects and persons that were tracked in the past.
- FAREQ-475: The system must support models that output data for 3D object detections.
- FAREQ-50: The system shall ask the user to confirm that the sensor can be deleted.
- FAREQ-51: The system shall perform analytics to map 2D camera detections into the scene.
- FAREQ-53: The system shall allow the user to create one or more polygons over the scene to define regions of interest.
- FAREQ-54: The system shall allow the user to view/read one or more polygons over the scene to define regions of interest.
- FAREQ-55: The system shall allow the user to update one or more polygons over the scene to redefine regions of interest.
- FAREQ-56: The system shall allow the user to delete one or more polygons over the scene to eliminate regions of interest.
- FAREQ-57: The system shall allow the user to create one or more directional lines over the scene to define tripwires.
- FAREQ-58: The system shall allow the user to view/read one or more directional lines over the scene to define tripwires.
- FAREQ-59: The system shall allow the user to update one or more directional lines over the scene to redefine tripwires.
- FAREQ-60: The system shall allow the user to delete one or more directional lines over the scene to eliminate tripwires.
- FAREQ-68: The user shall be able to edit the configuration properties for an existing camera.
- FAREQ-72: When a new instance of SAIL is brought up, the containers configured in the example Docker Compose start successfully.
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- FAREQ-81: When an {Object(s)} enters a Region of Interest, the system shall increment the Region of Interest {Object} count by 1.
- FAREQ-82: When an {Object(s)} exits a Region of Interest, the system shall decrement the Region of Interest {Object} count by 1.
- FAREQ-85: The system shall only allow {Admin Authorized Applications} to access data produced by {Analytics Applications}.
- FAREQ-87: The system shall display bounding boxes around detected {Object(s) in the Web User Interface.
- ITEP-18989: Investigate and fix: test case api-large-strings
- ITEP-66618: SceneScape Refactoring (Other)
- ITEP-69623: Validate if Scene Controller provides volumetric analytics
- ITEP-69628: Validate if each service can be build independently
- ITEP-72041: [MQTT][API] Service does not respond to request status message being published to endpoint
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- ITEP-73442: Cannot create Region of Interest
- ITEP-73538: Scene controller fails to emit LLA output for valid detection
- ITEP-73587: Permissions granted to user, but functionalities unavailable
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-78992: Add / update dynamic Camera Configuration test cases
- ITEP-79163: [Kubernetes][API][UI] Cannot import a scene when deployed on Kubernetes
- ITEP-80141: [Docker][API][UI] Importing a scene results in Server Error (500) on Docker
- ITEP-81834: [Kubernetes][API] Adding camera with minimal payload crashes kubeclient during pipeline generation
- ITEP-81878: RE-ID test failures due to frame skipping and tracker performance issue
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely
- ITEP-81919: Cannot link child scene with new user
- ITEP-82000: DeepScenario container exited due to image warping issue
- ITEP-82050: Fuzzing: 3 out of 5 requests failed to execute successfully
- ITEP-82375: [Kubernetes] Kind fail on host restart
- ITEP-82623: Objects from the parent scene are not retracked in the child scene
- SAIL-1129: Implement test SAIL-986 MQTT message generation for sensors.
- SAIL-113: Test for display of bounding boxes on the user interface
- SAIL-1291: Update ROI test to have an option for singleton/sensor creation
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape
- SAIL-1451: Test REST API with both positive and negative testing, verify returned data and HTTP status codes
- SAIL-1551: Test that API returns requested objects with info for addt'l requests
- SAIL-1560: Test system supports token authorization
- SAIL-1611: A malicious user could abuse the /media/ directory and upload any arbitrary web content
- SAIL-1766: Test system provides a method for generating/revoking REST API tokens
- SAIL-1793: API Tests
- SAIL-1808: Test ACC given the scene and map contain updates to an april tag.
- SAIL-1839: Write and Run functional tests for Auto Camera Calibration AprilTags
- SAIL-1840: User can launch SceneScape using Kubernetes
- SAIL-1848: User can call "User API: Post"
- SAIL-1850: User can call "User API: Get"
- SAIL-1867: Test ACC with no April tags identified produces error
- SAIL-1868: Test ACC with 4 aprilTags with 1 or more occluded will error after MAX attempts
- SAIL-1869: Test ACC with 4 unoccluded apriltags can map the scene successfully
- SAIL-1980: Helm Charts for SceneScape
- SAIL-2007: 3D Object Detection
- SAIL-2037: CT631 - Create fuzzing tools for RESTler
- SAIL-2111: SAIL-113 bounding-box test passes even when it fails
- SAIL-2121: Creating a scene hierarchy with circular dependency causes a server 500 error.
- SAIL-2212: Manual Tests for Kubernetes Q4 2023 Feature updates - WW44 Release
- SAIL-2224: Successful deployment into a kind cluster
- SAIL-2349: Run Manual Tests for 2023.4
- SAIL-2350: Run Manual Tests for 2023.4
- SAIL-2357: UI autocalibration error messaging
- SAIL-2359: Kubernetes: camcalibration pod is failing
- SAIL-2397: Handle register step termination for multiple updates to the same scene
- SAIL-2404: Distributed Scene Hierarchy - Crawl
- SAIL-2480: Singleton sensor data not getting tagged on the scene objects
- SAIL-2490: Scene Controller handles both the spatial data and re-id data
- SAIL-2491: Add counter for number of unique IDs detected in scene
- SAIL-2500: Parent scene can connect to remote child scene
- SAIL-2501: Parent scene republishes the analytics from child in its coordinate space
- SAIL-2509: Verify the similarity search and the threshold settings
- SAIL-2524: If a camera from a different scene is added, inform the user when attempting auto calibration
- SAIL-2560: README document is provided on how to setup a remote child connection
- SAIL-2610: Percebro detector support for DeepScenario 3D model
- SAIL-2623: Remote child tracking fails in absence of scene object in parent db
- SAIL-2716: User can visualize child scene sensor events and analytics in parent.
- SAIL-2718: Associate all LPR detections to 3D object detections
- SAIL-2724: Generate test cases for Dynamic Camera Configuration
- SAIL-2737: broken_tests list: Investigate / root-cause restricted-media-access failure.
- SAIL-2746: randomly_failing_tests list: Investigate / root-cause calibrate-all-sensor-types intermittent failures.
- SAIL-2753: randomly_failing_tests list: Investigate / root-cause mqtt-slow-sensor-roi intermittent failures.
- SAIL-2763: Setup a toggle for child tracks in parent scene
- SAIL-2778: Number of objects never drops to zero even when nothing is detected
- SAIL-2828: Wipro enabling - LPR association with 3D object detection
- SAIL-2936: Automate RE-ID scenarios
- SAIL-2944: Scene hierarchy child is disconnected from parent on several minutes
- SAIL-2948: Update RE-ID test case SAIL-T661 to allow for acceptable variation and baselining for regression tracking
- SAIL-2981: Video playback from multiple video sources does not stay in sync
- SAIL-303: Automate Test Cases - Sprint WW02 (Richa)
- SAIL-3101: Singleton sensor won't work unless the Name matches the Sensor ID
- SAIL-3102: Camera calibration with AprilTags is not available when transition from Markerless to AprilTag is used
- SAIL-3172: Retrack option should be to bypass tracker or not
- SAIL-3183: Distributed Scene Hierarchy - Walk
- SAIL-3225: Control the temporal fidelity/resolution of a scene
- SAIL-3284: Attribute sensors are still tagging old data on new objects
- SAIL-3352: Implement 3d bounding box rotation before cropping for model-chaining.
- SAIL-3406: License plate association with 3D object inside of percebro
- SAIL-3446: Move heavy compute related to visibility and camera bounds to regulated topic only.
- SAIL-3451: Cameras created via REST API are not visible in the Web Scene UI
- SAIL-346: Security malformed data test to check if system rejects malformed data correctly
- SAIL-3509: Auto Calibrate button for camera not working in 3D using markerless calibration type
- SAIL-3519: broken_tests list: automated release test cases
- SAIL-3562: Parallel model inference (annotations) are broken
- SAIL-3577: Problem with granting permissions to new user
- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)
- SAIL-481: Persist singleton data on a given object track in the scene graph
- SAIL-52: Test that the system operates with no Internet connection
- SAIL-54: Test that the system saves scene floorplan, name, and scale
- SAIL-591: Automate Test cases - WW22 (Marian)
- SAIL-683: Camera Calibration April Tag Method
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-824: Debug & fix failed test cases in SAIL-493 (Marian)
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.

## Test suite setup

### Hardware Requirements

### Test suite prerequisites

- - Kind cluster is running properly
- All pods are up and running
- 1. SceneScape must be up and running.

2. You also have to be authenticated into the postgres database:

# docker exec -it &lt;pgserver-container-name&gt; bash

he password is located in: run/secrets/django/secrets.py

# psql -h localhost -d scenescape -U scenescape -W

- 3D model must be available. Text-detection model and Text-recognition model.
  Static image available with known text (and detectable by the text-detection + text-recognition model).
  SAIL-T647
- All SceneScape containers are up and running
- Availability of a 3D DS model.
- Available 3D vehicle detection model
  Available LP detection model (Geti trained)
  Available video/image input with annotated data
- Current version of SceneScape is installed and configured for out of box demo scene.
- Intel® SceneScape is installed and running.A parent scene and a child scene are set up.The child scene is already linked to the parent scene.
- Intel® SceneScape is installed and running.A parent scene and multiple child scenes are set up.The User API is accessible, and a second user can be created.Clients are connected to the Intel® SceneScape system and can subscribe to scene graph updates.
- Intel® SceneScape is installed and running.Two scenes are set up: "scene_1" with no cameras and "scene_2" with cameras.
- Intel® SceneScape is installed and running.Two scenes are set up: a parent scene and a child scene.The child scene is linked to the parent scene.
- Intel® SceneScape is installed on both Host 1 and Host 2.Host 1 and Host 2 are on the same network.MQTT is configured and enabled on both hosts.
- Intel® SceneScape is installed on both Host 1 and Host 2.Host 1 and Host 2 are on the same network.The parent scene and remote child scene have different names.The remote child scene is initially linked to the parent scene.
- Intel® SceneScape is installed on both Host A and Host B.Host A and Host B are on the same network.The parent scene and child scene have different names.
- Intel® SceneScape is installed on both the parent and child systems.The parent and child systems are on the same network.The parent and child systems have different scene names (no conflicting scene names).
- Kubernetes Scenescape demo deployed
- Kubernetes scenescape demo deployed
- Kubernetes scenescape demo deployed
  Scenescape deployed on a platform with iGPU and dGPU
- Local access to a physical machine capable of running Scenescape
- Make sure that SceneScape is up and running
- Run the deploy SceneScape script to have all containers build.Make sure that the containers are not started, using docker-compose down
- Running the VDMS container with the VDMS client installed and able to connect to it

One way to get the initial setup is start scenescape with docker-compose and connect to one of the containers using
"docker exec -it scenescape_web_1 /bin/bash"
Then can run python and execute the test from there

- SceneScape is up and running
- SceneScape is up and running
  A sensor data publisher for sensor1 is running as follows:docker/scenescape-start --shellutils/singleton.py -a /run/secrets/percebro.auth -i sensor1
- SceneScape is up and running.
- SceneScape is up with camcalibration container running
- Scenescape is deployed with Queuing scene present.
  Access to console of the host machine.
- Scenescape is deployed with Retail scene present.
  Access to console of the host machine.
- Scenescape is up and running
- Scenescape repo present on the machine
  Scenescape not deployed
- Scenescape set up with the default configuration using ./deploy.sh
- The camera frame contains 4 unoccluded AprilTags.Camera intrinsics are available.The scene exists in the system.
- The following zip files are present in /workspace/tests/ui/test_media/:Retail-import.zipEmpty.zipInvalid.zipParent.zipIntersection-Demo.zipCleanly build Scenescape (make &amp;&amp; make setup_tests)
- There is a scenescape repo cloned on the testing machine
- There is a scenescape repo cloned on the testing machine
  User already has camera(s) added to a scene
- Verify an error occured when no AprilTags are visible
- kubernetes scenescape demo deployed

## Vision_AI/SceneScape/Functional Tests/01: Test that the system operates with no Internet connection

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Verify that, even with no internet connection, Scene Scape is able to operate properly.

### Test requirements mapping

- FAREQ-16: Once built, the system shall not require an internet connection to operate.
- SAIL-52: Test that the system operates with no Internet connection

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build the system, in a normal fashion, with internet connection ON. Check that containers are up and running and Scene Scape behaves properly
   - Test data: `# ./deploy

# docker ps`

1. Stop the Scene Scape. Make sure there are no more containers up and running
   - Test data: `# docker compose down --remove-orphans
#docker ps`
1. Disconnect from the Internet. Either unplug the ethernet cable or disable your WIFI.
   - Test data: `start any web-browser and verify that indeed there is no internet anymore`
1. Start the system again and login into the web interface. Verify that Scene Scape behaves properly
   - Test data: `# docker compose up -d`

## Vision_AI/SceneScape/Functional Tests/02: Persistence

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that the system saves scene floorplan, name, and scale
  Edit a scene, and note the changes madeNavigate to the Home page, then back into the scene. Verify the changes made are persistent.From the command line, take down the Docker containers using `docker-compose down`From the command line, start the Docker containers using `docker-compose up`Navigate to the original scene, and verify that all changes made persist across the system restart.Test PASSES if changes are persistent.

### Test requirements mapping

- FAREQ-21: The system shall store the scene floorplan and its {metadata}.
- SAIL-303: Automate Test Cases - Sprint WW02 (Richa)
- SAIL-54: Test that the system saves scene floorplan, name, and scale

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. make -C tests persistence

## Vision_AI/SceneScape/Functional Tests/03: Test for display of bounding boxes on the user interface

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2021.4, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Launch system with the Demo sceneLog in to the web interface and navigate to the Demo sceneClick the "Live View" toggle to the on positionInspect the displayed video frames in for camera1 and camera2 and verify that bounding boxes are decorated around detected people or objectsTest PASSES if bounding boxes are displayed in step 4.

### Test requirements mapping

- FAREQ-87: The system shall display bounding boxes around detected {Object(s) in the Web User Interface.
- SAIL-591: Automate Test cases - WW22 (Marian)
- SAIL-824: Debug & fix failed test cases in SAIL-493 (Marian)
- SAIL-817: Resolve issues with disabled and failing tests related to child scene implementation
- SAIL-113: Test for display of bounding boxes on the user interface
- FAREQ-74: When a new instance of SAIL is brought up, the MQTT broker is running.
- SAIL-98: Test that when a new instance of SAIL is brought up, the MQTT broker is running.
- FAREQ-386: The system must decorate frames with detections and the current frame rate.
- SAIL-2111: SAIL-113 bounding-box test passes even when it fails

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests bounding-box
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Functional Tests/04: Security malformed data test to check if system rejects malformed data correctly

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- This sends invalid sensor (camera) data thru MQTT, the tester must visually verify on the scene page whether the scene and camera feed get updated.
  The test will cycle thru 13 tests. It will publish 500 frames for each of the steps.
  Step 1: Invalid timestamp Step 2: Invalid sensor ID. Step 3: Invalid confidence (0 and negative) Step 4: Invalid (negative) bounding box width Step 5: Invalid (negative) bounding box height Step 6: Invalid (negative) Center of Mass width Step 7: Invalid (negative) Center of Mass height Step 8: Invalid (negative and non-sequential) inference id Step 9: Invalid (negative) framerate. Back to step 0.

### Test requirements mapping

- SAIL-346: Security malformed data test to check if system rejects malformed data correctly
- FAREQ-85: The system shall only allow {Admin Authorized Applications} to access data produced by {Analytics Applications}.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. tests/security/malformed_data/test_malformed_json.sh

## Vision_AI/SceneScape/Functional Tests/05: Implement test SAIL-986 MQTT message generation for sensors.

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Test that MQTT messages are generated for objects by sensors covering the entire scene, a circular area, or an polygonal area.

### Test requirements mapping

- SAIL-1129: Implement test SAIL-986 MQTT message generation for sensors.
- FAREQ-381: The system must publish results using JSON over MQTT.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests sensors-send-events
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Functional Tests/06: Test that a user can calibrate a sensor

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Implement an automated way to test that a user can calibrate a sensor. This can be broken down into three cases.
  Sensor covers the entire scene:
  Check that the sensor name is in the demo scene.Check that the sensor id is in the demo scene.Check that class="area-group" has no elements in the demo scene.Sensor covers a circular area:
  Check that the sensor name is in the demo scene.Check that the sensor id is in the demo scene.Check that the class="area-group" contains a circle tag of class="area" in the demo scene.Check the radius of the circle in the demo scene is the same as saved in the sensor's calibration.Sensor covers a polygonal area:
  Check that the sensor name is in the demo scene.Check that the sensor id is in the demo scene.Check that the class="area-group" contains a polygon tag of class="area" in the demo scene.Check the polygon points in the demo scene are where they were placed in calibration.

### Test requirements mapping

- SAIL-2746: randomly_failing_tests list: Investigate / root-cause calibrate-all-sensor-types intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests calibrate-all-sensor-types
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Functional Tests/07: Verify event generated upon an object entering a sensor/singleton region, contains the current singleton value added to it, and any new singleton values received while the object stays in the region

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- You can use the utils/singleton.py file to generate singleton values at specific intervals.

See mqtt-sensor-roi -&gt; tests\functional\tc_mqtt_sensor_roi.py

### Test requirements mapping

- SAIL-1291: Update ROI test to have an option for singleton/sensor creation
- FAREQ-81: When an {Object(s)} enters a Region of Interest, the system shall increment the Region of Interest {Object} count by 1.
- FAREQ-82: When an {Object(s)} exits a Region of Interest, the system shall decrement the Region of Interest {Object} count by 1.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/08: Write a test to verify event generated upon an object entering/exiting a sensor/singleton region, That if a sensor/singleton does not update often, still contains the most recent value added to them

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- You can use the utils/singleton.py file to generate singleton values at specific intervals.

### Test requirements mapping

- SAIL-1291: Update ROI test to have an option for singleton/sensor creation
- SAIL-2753: randomly_failing_tests list: Investigate / root-cause mqtt-slow-sensor-roi intermittent failures.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/09: Test REST API with both positive and negative testing, verify returned data and HTTP status codes

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2024.2

### Test summary

- Test that uses rest_client.py and does both positive and negative testing to make sure that every call works and that the correct status codes are returned from the REST server on errors.
  Documentation of current REST calls is in sscape/rest_client.py
  Swagger/OpenAPI spec is located at docs/api
  Test should be designed in a modular way to make it easy to add new REST API calls.

### Test requirements mapping

- FAREQ-244: API must provide CRUD functions for all object types
- FAREQ-245: API must support token-based authentication
- FAREQ-313: The system must provide a method for generating REST API tokens
- FAREQ-79: The system shall publish the location of detected {Object(s)} to {Clients}.
- FAREQ-78: When an {Object(s)} is detected, the system shall publish the {Scene Metadata} of the {Object} to {Client(s)}.
- FAREQ-72: When a new instance of SAIL is brought up, the containers configured in the example Docker Compose start successfully.
- FAREQ-68: The user shall be able to edit the configuration properties for an existing camera.
- FAREQ-60: The system shall allow the user to delete one or more directional lines over the scene to eliminate tripwires.
- FAREQ-59: The system shall allow the user to update one or more directional lines over the scene to redefine tripwires.
- FAREQ-58: The system shall allow the user to view/read one or more directional lines over the scene to define tripwires.
- FAREQ-57: The system shall allow the user to create one or more directional lines over the scene to define tripwires.
- FAREQ-56: The system shall allow the user to delete one or more polygons over the scene to eliminate regions of interest.
- FAREQ-55: The system shall allow the user to update one or more polygons over the scene to redefine regions of interest.
- FAREQ-54: The system shall allow the user to view/read one or more polygons over the scene to define regions of interest.
- FAREQ-53: The system shall allow the user to create one or more polygons over the scene to define regions of interest.
- FAREQ-51: The system shall perform analytics to map 2D camera detections into the scene.
- FAREQ-50: The system shall ask the user to confirm that the sensor can be deleted.
- FAREQ-43: The user shall be able to add a new camera that must be assigned to a scene.
- FAREQ-36: The system shall ask the user to confirm that the sensor can be deleted.
- FAREQ-30: The system shall require sensor ID, sensor name, and parent scene data fields be populated for sensor creation.
- FAREQ-29: The user shall be able to add a new sensor that must be assigned to a scene.
- FAREQ-25: The system shall ask the user to confirm that the scene can be deleted.
- FAREQ-24: The user shall be able to delete an existing scene.
- FAREQ-23: The user shall be able to edit the scene properties for an existing scene.
- SAIL-1793: API Tests
- SAIL-1451: Test REST API with both positive and negative testing, verify returned data and HTTP status codes
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape
- FAREQ-241: The system must provide a standards-based REST API
- FAREQ-44: When a camera is created, the user shall input the properties for camera ID, camera name and parent scene.
- FAREQ-41: The user shall be able to edit the configuration properties for an existing sensor.
- FAREQ-34: The user shall be able to view the scene and its corresponding sensors.
- ITEP-66618: SceneScape Refactoring (Other)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests rest-test
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Functional Tests/10: Test that API returns requested objects with info for additional requests

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This should test that whenever a request for a given object type is made the system returns a list of the object(s) along with information provided for making subsequent requests included such as UIDs and parent scene(s).
  Systems objects include: scenes, cameras, sensors, 3Dassets, tripwires and regions

### Test requirements mapping

- FAREQ-243: API must provide a list of objects by scene object type
- SAIL-1793: API Tests
- SAIL-1551: Test that API returns requested objects with info for addt'l requests
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape
- ITEP-66618: SceneScape Refactoring (Other)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Get token
   - Test data: `URL=https://localhost/api/v1
TOKEN=$(curl -s --location --insecure -X POST -d "username=admin&amp;password=pass" ${URL}/auth | jq -r .token)`
1. Call REST API and verify if the returned json contains correct response
   - Test data: `curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/scenes" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/cameras" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/sensors" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/assets" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/tripwires" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/reqions" | jq
curl --location --insecure -H "Authorization: Token ${TOKEN}" -G "${URL}/users" | jq`
1. Call getScenes REST API and verify if the returned json contains all objects contained by the scene.

## Vision_AI/SceneScape/Functional Tests/11: Test system supports token authorization

**Affected Versions:** 2024.2

### Test summary

- The system must support token authorization and provide a method for generating and revoking the tokens that are used to secure API transactions.

### Test requirements mapping

- FAREQ-245: API must support token-based authentication
- SAIL-1793: API Tests
- SAIL-1560: Test system supports token authorization
- SAIL-3451: Cameras created via REST API are not visible in the Web Scene UI
- ITEP-66618: SceneScape Refactoring (Other)
- ITEP-81834: [Kubernetes][API] Adding camera with minimal payload crashes kubeclient during pipeline generation

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. From the SceneScape Admin Web interface, delete the existing token for the admin user then create one for it.
1. Start a scenescape shell.
   - Test data: `# docker/scenescape-start --shell`
1. Get the authentication token.
   - Test data: `# curl --location --insecure -X POST -d "username=admin&amp;password=pgpass" https://localhost/api/v1/auth`
1. Get the scene for which new camera will be added
   - Test data: `curl --location --insecure -H "Authorization: Token 449331ce6b807b3dddf667ec4b8a8edce4cb3934" -G "https://localhost/api/v1/scenes"`
1. Generate a new test camera with uuid of scene from previous step
   - Test data: `curl --location --insecure -X POST -H "Content-Type: application/json" -d '{
"name": "cameratest",
"scene": "3bc091c7-e449-46a0-9540-29c499bca18c"
}' -H "Authorization: Token 449331ce6b807b3dddf667ec4b8a8edce4cb3934" "https://localhost/api/v1/camera"`
1. Go to the SceneScape web interface and verify that in the 'Cameras' tab, a new camera named 'cameratest' was created.

## Vision_AI/SceneScape/Functional Tests/12: Test system provides a method for generating REST API tokens

**Affected Versions:** 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-2349: Run Manual Tests for 2023.4
- FAREQ-313: The system must provide a method for generating REST API tokens
- SAIL-1766: Test system provides a method for generating/revoking REST API tokens
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. URL=https://localhost/api/v1
   TOKEN=$(curl -s --location --insecure -X POST -d "username=admin&amp;password=pass" ${URL}/auth | jq -r .token)
1. echo $TOKEN

## Vision_AI/SceneScape/Functional Tests/13: Test ACC given the scene and map contain updates to an april tag.

**Affected Versions:** 2024.2

### Test summary

- Test ACC given the scene and map contain updates to an april tag (Ex. a point was moved to a different location on the map), verifying the register step.

### Test requirements mapping

- SAIL-1839: Write and Run functional tests for Auto Camera Calibration AprilTags
- SAIL-1808: Test ACC given the scene and map contain updates to an april tag.
- SAIL-683: Camera Calibration April Tag Method
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/14: Test ACC with no April tags identified produces error

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that the ACC displays an appropriate error message and disables the calibration button when no April tags are present in the scene.

### Test requirements mapping

- SAIL-2357: UI autocalibration error messaging
- SAIL-2350: Run Manual Tests for 2023.4
- SAIL-1839: Write and Run functional tests for Auto Camera Calibration AprilTags
- SAIL-1867: Test ACC with no April tags identified produces error
- SAIL-683: Camera Calibration April Tag Method
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Log into SceneScape web app
1. Check UI:Enter page for one of the Retail scene's cameras.Mouse over the "Auto Calibrate" button
1. Check REST in the host machine console:Acquire scenescape-camcalibration container ID with "docker ps"Check container logs with "docker logs {ID_FROM_PREVIOUS_STEP}"

## Vision_AI/SceneScape/Functional Tests/15: Test ACC with 4 aprilTags with 1 or more occluded will error after MAX attempts

**Affected Versions:** 2024.2

### Test summary

- Verify ACC fails correctly and pub_data contains proper messages.

### Test requirements mapping

- SAIL-2357: UI autocalibration error messaging
- SAIL-2350: Run Manual Tests for 2023.4
- SAIL-1868: Test ACC with 4 aprilTags with 1 or more occluded will error after MAX attempts
- SAIL-683: Camera Calibration April Tag Method
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Simulating the scenario where one or more AprilTags are occluded in the camera frame
1. Get camera calibration response from DATA_AUTOCALIB_CAM_POSE and verify errors raised and pose data

## Vision_AI/SceneScape/Functional Tests/16: Test ACC with 4 unoccluded apriltags can map the scene successfully

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that if the camera frame contains 4 visible AprilTags, the scene can be successfully mapped, and calibration can proceed.

### Test requirements mapping

- SAIL-2350: Run Manual Tests for 2023.4
- SAIL-1869: Test ACC with 4 unoccluded apriltags can map the scene successfully
- SAIL-683: Camera Calibration April Tag Method
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Check service status
   - Test data: `GET {{baseUrl}}/status`
1. Register the scene
   - Test data: `POST {{baseUrl}}/scenes/{sceneId}/registration`
1. poll scene registration status until complete
   - Test data: `GET {{baseUrl}}/scenes/{sceneId}/registration`
1. Start camera calibration
   - Test data: `POST{{baseUrl}}/cameras/{cameraId}/calibration`
1. Poll calibration status until success
   - Test data: `GET {{baseUrl}}/cameras/{cameraId}/calibration`
1. Publishing the pub_data to the topic DATA_AUTOCALIB_CAM_POSE

## Vision_AI/SceneScape/Functional Tests/17: CLONE - Test Child Scene(s) Aggregation and Linking with a Second User

**Affected Versions:** 2024.2

### Test summary

- This test case verifies the behavior of child scene aggregation and linking using a second user created with the User API. It ensures that the Intel® SceneScape system can aggregate a parent scene and its child scenes to create a larger, holistic scene graph, which is published to clients. Additionally, it tests the rules and error handling related to linking child scenes to parent scenes, including the restriction of linking a child scene to only one parent scene, the ability to link multiple child scenes to a parent, and the behavior when a parent scene is deleted.

### Test requirements mapping

- ITEP-73587: Permissions granted to user, but functionalities unavailable
- SAIL-1850: User can call "User API: Get"
- SAIL-1848: User can call "User API: Post"
- SAIL-3577: Problem with granting permissions to new user
- ITEP-81919: Cannot link child scene with new user

### Test priority

- P4

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up a parent scene and multiple child scenes in the Intel® SceneScape system.
1. Create a second user using the User API calls (POST and GET).

URL=https://localhost/api/v1

TOKEN=$(curl -s --location --insecure -X POST -d "username=admin&amp;password=pass" ${URL}/auth | jq -r .token)

curl --location --insecure -H "Authorization: Token ${TOKEN}" -H "Content-Type: application/json" -X POST "${URL}/user" -d '{
"username": "newuser",
"password": "newpass"
}'

1. Add scene linking permissions (super user status - SAIL-3577) for a second user in the admin panel.
1. With the second user, link a child scene to the parent scene.
1. Verify that the aggregated scene graph is being published to clients, containing the combined data from the parent scene and the linked child scene.
1. Attempt to link the same child scene to another parent scene.
1. Verify that the system prevents the linking operation and doesn't show the option to add the same already used scene to another parent
1. Link additional child scenes to the parent scene using the second user.
1. Verify that the aggregated scene graph is updated to include the data from all linked child scenes.
1. Delete the parent scene.
1. Verify that the linked child scenes are not deleted along with the parent scene.

## Vision_AI/SceneScape/Functional Tests/18: Integrate Geospatial tests into Scenescape

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

-

### Test requirements mapping

- ITEP-73538: Scene controller fails to emit LLA output for valid detection
- FAREQ-330: The system shall provide the option to configure a scene to output latitude, longitude, altitude (LLA).
- FAREQ-328: When ingesting data with longitude, latitude, altitude (LLA) and no cartesian location, the system must convert LLA into earth-centered earth-fixed (ECEF).

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. make -C tests geospatial-ingest-publish

## Vision_AI/SceneScape/Functional Tests/19: Restricted media access

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- A malicious user could abuse the /media/ directory and upload any arbitrary web content
  A malicious user could upload a fake version of the login page which performs actions controlled by the adversary. This is possible because the web server is accepting and rendering any html files placed in the root of the media directory. For example: https://scenescape-hat.fm.intel.com/media/index2.glb is HTML but has a glb extension. The web server will render it as HTML. It is a copy of the actual login page but under control of the adversary.

 
Repro Steps:
Create an index.glb file which contains HTML and upload it. Visit the URL with the full ink to the file (https://scenescape-hat.fm.intel.com/media/index2.glb) and observe the web content being rendered. The file can be called anything you wish however.

### Test requirements mapping

- SAIL-1611: A malicious user could abuse the /media/ directory and upload any arbitrary web content
- SAIL-2737: broken_tests list: Investigate / root-cause restricted-media-access failure.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. # make -C tests restricted-media-access
   - Test data: `For the Kubernetes environment add the following environment variables, where change_me is the password used for the Kubernetes deployment:
SUPASS=change_me KUBERNETES=1`

## Vision_AI/SceneScape/Functional Tests/20: Successful deployment into a kind cluster

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

- Make sure that all SceneScape pods are correctly deployed into a kind cluster

### Test requirements mapping

- SAIL-2359: Kubernetes: camcalibration pod is failing
- SAIL-2224: Successful deployment into a kind cluster
- SAIL-1840: User can launch SceneScape using Kubernetes
- SAIL-1980: Helm Charts for SceneScape
- SAIL-2212: Manual Tests for Kubernetes Q4 2023 Feature updates - WW44 Release

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Bring the kind Kubernetes cluster up.
   - Test data: `# make -C kubernetes/`
1. Make sure that the SceneScape pods are running. This can either be done using kubectl or k9s by checking each pod.
   - Test data: `# kubectl get pods -n scenescape -w

Or using the alternative TUI

# k9s`

1. Tear down the Kubernetes cluster
   - Test data: `# make -C kubernetes uninstall

# k9s

# make -C kubernetes clean-all

# k9s`

## Vision_AI/SceneScape/Functional Tests/21: Verify scene controller attaches re-id data to detected objects when using the reid model

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Ensure that the scene controller correctly handles re-id data when using the reid model by associating

### Test requirements mapping

- SAIL-2490: Scene Controller handles both the spatial data and re-id data

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Enable VDMS and Re-ID by modifying docker-compose.yml file:Uncomment the VDMS service segmentUncomment VDMS dependancy from the scene service segmentUncomment ports section in the broker service (this allows connecting to MQTT Explorer)In the configs segment change retail-config and queueing-config to
   "file: ./dlstreamer-pipeline-server/retail-config-reid.json" and
   "file: ./dlstreamer-pipeline-server/queuing-config-reid.json"Save changes
1. Restart scenescape:docker compose down --remove-orphansdocker compose up -d
1. Run MQTT explorer and connect to the scenescape broker using the same login as in web
1. Read the UID of the Retail scene by entering scene's page and checking the address.
1. Check the value of MQTT messages
   - Test data: `Subscribe to the topic: scenescape/data/scene/{SCENE_UID}/person`

## Vision_AI/SceneScape/Functional Tests/22: Verify similarity search with re-id vectors using VDMS

**Affected Versions:** 2024.1, 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-2509: Verify the similarity search and the threshold settings
- SAIL-2936: Automate RE-ID scenarios

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Connect to the VDMS database
   - Test data: `import vdms
db = vdms.vdms()
db.connect("&lt;HOSTNAME&gt;")`
1. Add the descriptor set for re-id data
   - Test data: `descriptor_set = { "AddDescriptorSet": {
     "name": "reid_vectors",
     "metric": "L2",
     "dimensions": 256
     }}

all_queries = []
all_queries.append(descriptor_set)

response, res_arr = db.query(all_queries)

print(f"RESPONSE: {response}\nRES_ARR: {res_arr}")`

1. Add descriptors for two distinct objects
   - Test data: `thing_1 = [0.07054176027309234,0.24336714076111404,-0.6711210960921561,-0.3412324983461833,0.16770637931712745,-0.5226452598950639,0.13748149223724676,-0.28059626891562206,0.7000075188650375,-0.25970002587838437,0.32714957113788395,0.2214066914136978,0.4797087168546342,0.24994270301746485,-0.6667949778174636,-0.7978168023330425,-0.2877644980012378,-0.1580214175107424,0.28539008657024295,0.6543530189127004,0.03985851512938442,0.05053288891803044,-0.1037729720107627,0.636873442476503,-0.48953999507284685,-0.43540964242740776,0.48395640386084143,0.173387591628705,-0.3569388780464783,-0.5375287358216829,-0.15265296532457473,0.23514945473101748,0.19938767539764085,0.43417690896383776,0.14596762908142305,0.05544167396307102,-0.25196407523863285,-0.019847908261453277,-0.04558917242377758,-0.1407847762961196,-0.5184992703393172,-0.2073301950745477,-0.5651638930908344,-0.06854011846888719,0.6121197305342652,-0.7004375599861651,-0.14879958469289284,-0.1270313916107073,-0.07676957258327938,0.06966887904850846,0.10934469243177755,0.4848538611478833,0.09560037693102882,-0.31999739290899304,-0.7363485457517462,-0.5360086513903328,-0.09237591878103865,0.2723703633344253,0.46122769457847196,0.362816679839171,-0.174347206457009,0.3076260709057838,-0.02140477184436066,-0.2529188243257755,0.037297629287814445,0.1639497074897778,-0.08837199040605058,0.2765649217146948,0.14163675677436022,-0.19972769482502667,-0.08127871460034135,-0.8091078052066493,-0.046274791139516144,-0.17038674434063805,-0.19458334654299447,0.11997587762321642,0.5384773547338018,-0.17472735522966248,-0.3420918102228279,0.48906062820704543,0.06243440324250045,0.16995230464142602,0.3474646900432123,0.3580041250672275,-0.5395622311035395,0.9364083705121844,0.33375383807652975,0.02572500182986635,-0.517302127755117,0.2011972351537855,0.09573550377881752,-0.25142815459396645,-0.10749808666401532,0.1578031896930246,-0.14344305543491598,0.40360201849623295,0.004381619044668261,-0.3878182395353522,-0.36554644016768245,-0.44547691773648934,0.6031581524048973,-0.34320698488072593,0.7509367865832312,-0.02002020410608438,-0.4699302864378613,-0.10851879627273604,-0.14027447039859506,-0.6961058943752776,0.17460619235547564,-0.271285191254803,0.18409646744346486,0.32695689457856003,0.233634701728921,-0.5605574552067958,-0.6258410114002958,-0.7825641958085121,0.17305510465491353,-0.1738553054436685,0.036443698507889075,-0.02547139608857139,-0.7460478731442545,-0.11198434302207332,0.04176430305477931,-0.19327203569530352,-0.21907687854580646,0.19678609833359711,0.9117475523233921,0.36656462319789446,-0.15512735162531788,0.4618725112063551,-0.4350818271457815,-0.11115377443325539,-0.26901202929680146,0.059580447897957654,-0.23635716424331324,0.3398468253702906,0.5829698113378484,0.3479290198844582,0.4886181459771503,-0.1843304467725112,0.028945137772629276,0.18866305851822465,0.40725850363288857,-1.05513175204137,-0.06952575631096054,0.5012122323556863,-0.057318908449703485,0.2367680888413089,0.23935659753360244,-0.022588826059225343,0.49007197329089636,0.38935365644063,-0.3351013076898939,0.14658626124990454,-0.13377195550428558,-0.23466052978869695,0.30524984021726664,-0.31003504577279817,0.13580786453710963,-0.020745260895117534,-0.22990800242171056,0.4103779023989723,-0.015165931439389463,0.026600901199241044,0.5164163373478283,0.4626104156143406,0.9573853450750873,-0.44981748288278584,0.011534445091167422,0.2698170240071865,0.07247186344343579,0.05396100489621743,0.11593053771211555,-0.012447713900718804,0.7591103960993213,0.3333501130343032,0.23258076934686867,0.021125833577845442,-0.11428325165693627,0.04986703861020639,0.3078175979577002,0.17799800419104983,-0.49963874268407726,-0.1489948692467905,0.1864694858221523,0.2565494369190377,-0.3502449606318528,-0.5920172935885674,0.3384775622879294,-0.056586919482954426,-0.6154463713871624,-0.07316352129133005,0.5193498205774587,-0.5683804892683437,-0.5520728013427657,0.35874907963439057,-0.24996289148974285,-0.3227318439003214,0.07747497927623681,-0.549373262696002,-0.5679254399665985,0.09548122996231183,0.9629311909812113,-0.1954147544058702,0.1950379187393229,-0.2210935954731222,0.5779745678388879,-0.7809403538634302,-0.1262036474229274,0.026956516936214064,-0.09148028160331681,0.3262336580589193,0.8689848952591511,0.07350051917701916,0.3909974859899282,0.014112430099517653,-0.7628870502840268,0.3154250577507552,-0.2004871623556203,0.006909667292703381,0.9913800968196792,0.6072590533392123,-0.4070937314300062,0.024615458894007226,-0.3808321936417098,-0.7598388425199918,-0.5044541067272809,0.06603225174751264,0.5519831337437666,-0.3829781554477794,0.02756605625980225,0.30741530110741366,0.5303263778395386,-0.466259518860742,0.22516823421448545,0.08797765261301398,-0.18943719985952706,-0.07337676414657393,-0.2280372000937317,-0.27544403956459335,0.2010470521760916,0.21935749227546916,0.03415158318295179,-0.7077581999609786,-0.14908961151791986,0.21564123850991218,0.27837584323770526,-0.2829625052611809,-0.160919994403398,0.5473930473135593,0.10081514762310913,-0.08584535771654753,0.11731988875768276,-0.394693899872976,0.8341085017812221,-0.03605961273888473 ]
     thing_2 = [0.24425808962217835,-0.1922936061464417,-0.541027300825389,-0.6632455409905005,-0.09810870609557025,-0.05178101785959351,0.7044971371673339,0.03716278567359284,-0.25969121735357525,0.23300649396830533,-0.16595808197458273,0.22075250864659007,-0.3378708864433752,0.3615377460513521,0.013536327367299667,-0.20315440011751967,-0.14216546339269912,-0.3310928452238864,-0.9730999621933325,-0.18300800878607837,-0.06455437677476053,0.04093030200727273,-0.10034845331441353,-0.04172615717769204,-0.0006329358951717767,0.1048476610004474,0.6291929335500976,-0.4209525182298224,0.24638913640235044,0.10456406510484428,0.9067918918280062,0.27903366625919024,-0.6290473082326398,0.0728163769067354,-0.08048150102793893,-0.021856528251911995,-0.31307508853717575,-0.2453065785725023,0.7746082922355001,-0.004893293578479233,-0.3916597062642071,-0.1555706893983683,0.10716539321753657,-0.36699100374274796,0.17873332779407067,-0.4543906340082386,-0.17918475738014522,-0.7119015645160743,0.3315791118822977,0.1907384704278549,0.2883591103456643,0.30003799889664823,-0.4097398454150648,0.10665091092967494,0.23817187483078506,-0.3712731158025689,0.16993919971437818,-0.4953788781719508,0.25144313790376904,-0.35400386991517313,0.22214792363611596,0.16810713340577813,0.1658027480225321,0.1964926160193768,-0.10811645731659077,-0.13887598195549364,0.7909169219059489,-0.4418175994323807,-0.06799672346278207,0.12274908356339567,0.501165353144321,-0.24091234674219097,-0.7592194594020019,0.0072951618111684186,0.1060469120528166,-0.23543869546509785,0.28867751397108066,0.25157676185752714,-0.25218392835173187,0.3586510515997744,0.02026127330935652,-0.19771090308574862,-0.3103912796204302,-0.21692407441599296,0.1334646688853936,0.8575179383455105,-0.2017810769629098,-0.37527364937435537,0.31010647718475653,0.41369281149581594,0.14944855188703182,-0.4906725286949604,0.0653437894096542,0.06045533671959839,0.8547142751116737,-0.3526075359045261,-0.4268369522087637,-0.7683506852603414,-0.29448790951420656,0.13592855024952222,0.474212065886794,0.2389071922430191,0.5738324859119865,-0.1326864834064756,-0.09237839349054924,-0.05558069040145639,0.26712472624638545,-0.5535164713429018,0.3423034453884821,0.2664605656630262,0.052535379123913664,0.2735058921294173,0.008740038283464466,-0.43288078511962136,-0.702998368018297,-0.7153331422285315,1.08858319654037,-0.33557904153250095,-0.07743415119604272,-0.8509392113639886,0.7905740382004744,-0.384862435153847,0.20524317726267158,0.18183251817907573,-0.459902146392663,-0.1156666358809677,-0.030564129983633226,0.6130376899960425,0.14298854930156785,0.036228108515247284,0.7313178091317662,-0.49039019318252003,0.3472156484163937,0.09504353385801556,-0.755077543672113,0.29225441109995676,0.19647418505543376,-0.10763787896118124,-0.2184447051333132,-0.03930245684547835,0.2550315833132037,-0.6187738098880273,0.3522492987319416,-0.4500496031354982,0.03527597375580269,-0.6138123791157131,-0.5449441951161575,0.061976662856457886,-0.36548147122176206,-0.06317547446610136,1.4941953629616598,0.045690248829318776,0.07889450655939054,0.31054775174170435,0.09308128211718088,-0.3066292454731412,-0.3923839143727005,-0.028265439052605208,-0.24593160737811318,-0.11293717818779343,-0.13532962668918513,-0.13285742147786403,-0.17175122104835022,-0.4550357497199755,-0.44708638692351854,0.9880594703741112,0.536936843172581,0.014351498927674285,-0.332016542966841,0.00674496576072336,0.1122716638943769,-0.6193496987283176,-0.30140647168351936,-0.2689713716354172,0.22997081449082324,-0.2659485591631326,-0.22074872865535816,0.2569547609430268,-0.5689442182033234,-0.3090964381480569,0.36913800639718763,0.05965615089437322,-0.2696011841373075,-0.0859222339630145,-0.042503887803402064,0.0961075283611574,-0.19047064671377784,-0.3125792039039644,0.45267189771193256,-0.6427831045769111,-0.6680339785910231,0.29155051548256217,0.15610364606240923,-0.33293991073888346,-0.4129837363821249,0.0836377927522092,-0.860784406045697,0.2542831635922872,0.2286983769957695,0.5329611793933205,-0.07435129772771595,-0.1636262060713777,0.3789055911264648,-0.04641058206426495,0.6732890658149131,0.010121192592410266,-0.08129696682621848,-0.011305882607163992,0.09106547441086296,0.04590512924995103,0.09664477085633216,0.3255176341892516,0.19169078709120102,-0.10651493082499908,0.7350267675535664,0.12931834286827798,-0.03834385832448879,-0.5412506503114072,0.4948915382789312,0.046487996886264135,0.053662910304410505,0.7827391559719838,0.14286213999001562,0.38583391243762655,-0.025406509748748453,-0.5556381797209481,0.43048555797607674,0.3298939931202715,-0.29312044196183634,-0.1933132924505832,-0.37247883333308573,0.6867830725966388,-0.22109640965055816,-0.2598891652193812,0.3472794647155749,0.8235302400992831,0.36848370432675615,0.16512693539063422,0.3119513651529144,0.24944191467871218,-0.31995369817320285,-0.44365656877015647,-0.07673598097645942,-0.30034996424755706,0.34055372396744266,-0.3138011782046856,0.0015118953156826056,0.2542577790321751,0.08461818753327413,0.09957226843566741,0.3002628780350643,-0.2442956280661417,0.668404329278897,0.20623461557837092,-0.19989525910707798,-0.4601903439336586]
     blob_1 = np.array(thing_1, dtype="float32")
     blob_2 = np.array(thing_2, dtype="float32")
     descriptor_blob = []
     descriptor_blob.append(blob_1.tobytes())
     descriptor_blob.append(blob_2.tobytes())

descriptor_1 = { "AddDescriptor": {
"set": "reid_vector",
"label": "Person 1"
}}

descriptor_2 = { "AddDescriptor": {
"set": "reid_vector",
"label": "Person 2"
}}

all_queries = []
all_queries.append(descriptor_1)
all_queries.append(descriptor_2)

response, res_arr = db.query(all_queries, [descriptor_blob])

print(f"RESPONSE: {response}\nRES_ARR: {res_arr}")`

1. Pass a third re-id vector from one of the two initial objects and get a similarity search comparison. It should have low distance from one of the entries.
   - Test data: `thing_2_match = [0.258094405421856,-0.18940506317468353,-0.5487877420481396,-0.6528600654492432,-0.11811041359410676,-0.029357388372570813,0.7122041875546501,0.044029338568950534,-0.2573769818970813,0.22074038642704194,-0.2021299327898874,0.20978933374787098,-0.32023621876848923,0.3738334051540614,0.0491707383319999,-0.1975324055964452,-0.13798361599971226,-0.3245762639824357,-0.9534645779470188,-0.18727376349329516,-0.030506234890589505,0.027792315861996562,-0.08533204770895055,-0.03413668204149205,0.006084304983254919,0.11298106027638133,0.6544011666936103,-0.4485022855524002,0.263246614004221,0.0932041261661076,0.9137589955493539,0.27815110419209443,-0.612833563780624,0.07353652409061534,-0.06335874741275797,0.033116486635974385,-0.31027145416255275,-0.2356143199690079,0.7728593835715524,-0.006471585039798356,-0.3712595893602342,-0.17179753765416375,0.08783362307386572,-0.3577866050832067,0.1627839304870981,-0.44091990359181593,-0.2067253434641024,-0.7308389490593881,0.39344049534118675,0.21756118819963496,0.25933629140834313,0.29052448707797984,-0.3880110641542508,0.10279442828654695,0.22086975568937223,-0.35125136102654614,0.1536323004613493,-0.5052797390969928,0.2709227518127574,-0.3702957160209789,0.20654985631801176,0.15464644222057894,0.15901673283627255,0.19486433011704976,-0.11480407756601596,-0.14839306988513598,0.824186850711454,-0.42874300468488064,-0.03730702180513824,0.09805274928577334,0.5040797578903404,-0.229843568693309,-0.7698825572457986,-0.027606576319474396,0.1605737407765857,-0.18979585492453094,0.26223837046065845,0.2454322658819817,-0.2768535572744429,0.3706491100335493,0.0581356988182405,-0.1936800712760734,-0.27896372097785976,-0.22159013993721458,0.12601647133686328,0.8696711908113501,-0.17052948229308673,-0.3450413991783609,0.3316791836240379,0.4439589070686094,0.17181737875911532,-0.4982369607807232,0.07402871707226044,0.051151132749016656,0.8813695915428781,-0.3619918719330092,-0.4370445472656426,-0.7981835709916727,-0.2810121090748773,0.10021207717412632,0.4595234631954944,0.23104304527008904,0.6172243829543296,-0.1629427848518462,-0.10970300014310005,-0.11913439620166093,0.2946201506953423,-0.5649786988415767,0.3197693255760119,0.26418019106724355,0.06158519557474655,0.2735586980666011,0.003868996940053343,-0.41267603200021535,-0.7246359300540858,-0.7111931336672302,1.081866292312956,-0.33164389364346797,-0.049982053067463436,-0.8444564045749303,0.8160939549659101,-0.35934867493722733,0.1907096516729812,0.20452886709334323,-0.4481777514943367,-0.1284280425162925,-0.0425729998672996,0.6048348771999044,0.12858337012655557,0.04582802756506489,0.720649305214512,-0.5159269170830558,0.3219363180837297,0.12452967444653248,-0.7736367084540574,0.28175857212654565,0.23289398790061372,-0.11329786943817095,-0.21968984452074797,-0.044712373366936634,0.2722516902663717,-0.5881511346256978,0.31632025842364037,-0.44949760387463905,0.03161453663053996,-0.6188112542296917,-0.5561270660433452,0.08624793156663385,-0.3711824507637346,-0.03447841147715962,1.4935964180764996,0.03515484258222767,0.07635428774756273,0.2966738117592169,0.11680926221191094,-0.30585453465381673,-0.374374474840449,-0.029402513351400223,-0.2434158092213868,-0.1229238738872673,-0.1353596186084101,-0.14426005783757662,-0.16232376852246908,-0.4484227207484489,-0.45781414270900667,1.0117997894891146,0.5487962660699762,0.022510506870571764,-0.3634102841667316,0.015214093690465563,0.10955267852116708,-0.6698839383059018,-0.312245263274,-0.286629443350346,0.20824714689840684,-0.29442829266810777,-0.23673789550041713,0.2762646775490393,-0.5735536642040339,-0.2971144754118781,0.3464041926552851,0.034422869767314374,-0.266339335185116,-0.07180032156573603,-0.02310776256968193,0.09128795647232159,-0.23635391272284859,-0.3142269963029261,0.4492309030587805,-0.6507537753474333,-0.6901700565656669,0.33741249463043543,0.15038932286213433,-0.3442198019880035,-0.44656502702302187,0.0636492646248505,-0.878843996899682,0.2790447919402611,0.23120016321258124,0.5177010248963361,-0.06014913200392987,-0.15395345969465143,0.3771168918037669,-0.054306729426178604,0.6780842733128212,0.019673579884930917,-0.0635426821038658,-0.0021209292657529953,0.09091777830213446,0.02369169354003975,0.11136851308592091,0.32903057075885,0.23077367181507027,-0.09500654052867279,0.7566856705498679,0.14297118177434862,-0.04335004249229011,-0.5714531421936184,0.4875709900775152,0.03599856232061524,0.038773333851875244,0.8026762599017662,0.13903922212353878,0.40309202433236085,-0.015057180613998477,-0.5174867682341182,0.44110743476583975,0.36279701306961043,-0.3301859527037668,-0.17930858420760126,-0.3961286456887708,0.702660789363748,-0.23491380423518676,-0.26480595674417057,0.3443400688898285,0.8105105042906293,0.3758442766116806,0.16670341210012402,0.2974666512453104,0.2864547806990362,-0.33184179691808946,-0.4320970564468549,-0.057258862774501276,-0.34656468121697787,0.35242477136228895,-0.3216832311812045,-0.004294464950389646,0.23459302574416485,0.07997692192754793,0.0907718691663725,0.3464622977095133,-0.2713598383512602,0.7037118976412335,0.18928961569966832,-0.19267997406690746,-0.47721091914768216]

find = [{ "FindDescriptor": {
"set": "reid_vector",
"k_neighbors": 20,
"results": {
"list": ["_distance"],
"blob": True
}
}}]

find_blob = [np.array(blob_2, dtype="float32").tobytes()]

response, res_arr = db.query(find, [find_blob])

print(f"RESPONSE: {response}\nRES_ARR: {res_arr}")`

## Vision_AI/SceneScape/Functional Tests/23: Multi-thread camera calibration

**Affected Versions:** 2024.1, 2024.2

### Test summary

- The preprocessing/register data step in auto camera calibration runs on a different thread. This ensures that main thread is responsive to other callbacks. Only one scene can register at once.

### Test requirements mapping

- SAIL-2397: Handle register step termination for multiple updates to the same scene
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify Preconditions are met
   - Test data: `Click auto calibrate and verify accurate calibration based on camera and map image overlays.`
1. Update the scene "Queuing" in the scene config page.
   - Test data: `Upload map : raw.glb ( can be found in zip file ) 
Calibration mode : Markerless
Polycam data : Aug1at12-51PM-poly.zip`
1. While processing is running in the above step, update the scene again to re-trigger the register step
   - Test data: `On scene config page of Queueing Scene ,
upload map : folsom.glb`
1. While processing for Queuing scene is running in the above step ,
   create a new scene to trigger register step.
   - Test data: `In scene create page , create new scene :
name : Test
map : Aug1at12-51PM-poly.zip
Click Save`

## Vision_AI/SceneScape/Functional Tests/24: Verify Remote Child Scene MQTT Connection from UI

**Affected Versions:** 2024.2

### Test summary

- This test case verifies the MQTT connection between a remote child scene and the parent scene's scene controller when adding a remote child scene link through the Intel® SceneScape user interface (UI). It ensures that the appropriate MQTT topics are available and that the scene controller can subscribe to and receive messages from the remote child scene.

### Test requirements mapping

- SAIL-2500: Parent scene can connect to remote child scene
- SAIL-2944: Scene hierarchy child is disconnected from parent on several minutes
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- SAIL-2404: Distributed Scene Hierarchy - Crawl
- SAIL-3183: Distributed Scene Hierarchy - Walk
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up Intel® SceneScape on two different hosts (Host 1 and Host 2) within the same network.
1. On Host 1, deploy the parent scene (e.g., "Retail" scene).
1. On Host 2, deploy a child scene (e.g., "Retail_remote" scene).
1. Configure the MQTT settings on both Host 1 and Host 2 to enable communication between the hosts. Check user and password in UI from MQTT tab.
1. Using the Intel® SceneScape web UI on Host 1, navigate to the parent scene and add a new remote child scene link for the "Retail_remote" scene on Host 2.
1. Verify that the remote child scene link is successfully created through the UI.
1. Check the logs of the scene controller on Host 1 to ensure that it has subscribed to the appropriate MQTT topic for the "Retail_remote" remote child scene (e.g., "scenescape/data/scene/Retail_remote/+").
1. On Host 2, publish messages to the MQTT topic for the "Retail_remote" scene.
1. Verify in the logs of the scene controller on Host 1 that it is receiving the messages published by Host 2 for the "Retail_remote" remote child scene.

## Vision_AI/SceneScape/Functional Tests/25: Remove a Remote Child Scene Link

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the functionality of removing a remote child scene link from a parent scene in the Intel® SceneScape system. It ensures that the system can correctly handle the removal of a remote child scene and update the aggregated scene graph accordingly.

### Test requirements mapping

- SAIL-2500: Parent scene can connect to remote child scene
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- SAIL-2404: Distributed Scene Hierarchy - Crawl
- SAIL-3183: Distributed Scene Hierarchy - Walk
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up Intel® SceneScape on two different hosts (Host 1 and Host 2) within the same network.
1. On Host 1, deploy the parent scene (e.g., "parent").
1. On Host 2, deploy a child scene (e.g., "retail_remote").
1. Link the child scene "retail_remote" on Host 2 as a remote child to the parent scene on Host 1.
1. Verify that the remote child scene is successfully linked and the aggregated scene graph includes the data from both the parent and remote child scenes.
1. Remove the remote child scene link by unlinking the "retail_remote" scene from the parent scene on Host 1.
1. Verify that the remote child scene is successfully unlinked from the parent scene.
1. Observe the aggregated scene graph and ensure that the data from the removed remote child scene is no longer included.
1. Perform various actions or movements in the parent scene and verify that the changes are not reflected in the removed remote child scene.

## Vision_AI/SceneScape/Functional Tests/26: Remote Child Scene Trackers

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the functionality of tracking objects from a remote child scene into the parent scene when the remote child scene is not present in the parent's database. It ensures that the Intel® SceneScape system can correctly handle and track objects from a remote child scene, even if the child scene is not initially known to the parent.

### Test requirements mapping

- SAIL-2623: Remote child tracking fails in absence of scene object in parent db
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- SAIL-2404: Distributed Scene Hierarchy - Crawl
- SAIL-3183: Distributed Scene Hierarchy - Walk
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up Intel® SceneScape on two different hosts: Host A and Host B.
1. On Host A, deploy the parent scene.
1. On Host B, deploy the child scene.
1. Ensure that the parent scene and child scene have different names (no duplicate scene names).
1. On Host A, enable port forwarding for the NTP server (ntpserv).
1. On Host B, configure the NTP server (ntpserv) to point to the IP address of Host A.
1. Link the child scene on Host B as a remote child to the parent scene on Host A.
1. Verify that the remote child scene is successfully connected to the parent scene.
1. Introduce objects or entities in the remote child scene that need to be tracked.
1. Observe the parent scene and verify that the objects or entities from the remote child scene are being tracked and displayed correctly.
1. Perform various actions or movements with the objects or entities in the remote child scene.
1. Verify that the parent scene is accurately tracking and reflecting the changes in the remote child scene objects or entities.

## Vision_AI/SceneScape/Functional Tests/27: Test 3D DS model integration

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify the integration of 3rd party 3D models from DeepScenario.

### Test requirements mapping

- SAIL-2610: Percebro detector support for DeepScenario 3D model
- FAREQ-475: The system must support models that output data for 3D object detections.
- SAIL-2007: 3D Object Detection

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Place the 3D DS Module in an container-accessible location. Include input video/image file that will trigger model detections.
   Generate and place the corresponding model-config to load the model.
1. Enter the container and export the DS_MODULE variable to point to the 'utils.py' or equivalent file containing the 'preprocess', 'postprocess' and 'decrypt' functions.
1. Run percebro in post-process mode, using the corresponding input file and verify there is a corresponding .json file with the detection information.
1. Verify the object detections from the module match the expected number of objects and corresponding bounding boxes. Verify the format of the output matches the expected format.

## Vision_AI/SceneScape/Functional Tests/28: MQTT Analytics Hierarchy - Scene Events Include Analytics from Child

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the ability of the Intel® SceneScape system to include analytics from a child scene in the parent scene's MQTT event topic. It ensures that events, regions of interest (ROIs), tripwires, and sensors created in the child scene are correctly propagated and published in the parent scene's MQTT event topic, allowing for a unified view of the analytics hierarchy.

### Test requirements mapping

- SAIL-2716: User can visualize child scene sensor events and analytics in parent.
- SAIL-2501: Parent scene republishes the analytics from child in its coordinate space
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- FAREQ-308: The system must support a scene to be a child of another scene on the same scene controller.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Ensure that the preconditions are met
   - Test data: `Set up two scenes: "scene_1" with no cameras and "scene_2" with cameras.Ensure that Intel® SceneScape is running with both scenes.`
1. Create a local child link
   - Test data: `Link "scene_2" as a local child of "scene_1".Verify that the child link is created successfully.`
1. Create ROI, tripwire, and sensor in the child scene
   - Test data: `In the child scene ("scene_2"), create an ROI, a tripwire, and a sensor.Verify that events are observed in the child scene over MQTT.`
1. Verify the events in the parent scene
   - Test data: `Subscribe to the parent scene's MQTT EVENT topic.Verify that all event types (ROIs, tripwires, and sensors) from the child scene are republished in the parent scene's event topic.`

## Vision_AI/SceneScape/Functional Tests/29: Kubernetes Dynamic Camera Configuration check

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Make sure that camera configuration is being reflected as a corresponding kubernetes pod.

### Test requirements mapping

- SAIL-2724: Generate test cases for Dynamic Camera Configuration
- FAREQ-363: The system must operate as a standalone, containerized microservice.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Bring the kind Kubernetes cluster up.
   - Test data: `# make -C kubernetes/`
1. Make sure that the SceneScape pods are running. This can either be done using kubectl or k9s by checking each pod.
   - Test data: `# kubectl get pods -n scenescape -w

Or using the alternative TUI

# k9s`

1. Log into the SceneScape web UI and add a new Camera to a scene. To find out the admin password, check the helm chart values used to provision kubernetes.
   - Test data: `The admin password is located into the values yaml.

# grep supass kubernetes/scenescape-chart/values.yaml

For this example, use:
Sensor id: demo-camera-1
Name: Demo Camera 1
Scene: Retail
Command: sleep 300
Camerachain: camerachain-1`

1. Using kubectl verify that the camera is up and running
   - Test data: `# kubectl get pods -n scenescape`
1. Modify an existing camera from SceneScape.
   - Test data: `In the Retail scene, modify 'demo-camera-1' to be named:
Name: camera-mod-2
Sensor id: camera-mod2`
1. Using kubectl verify that the pod 'camera2' was replaced by a pod named 'camera-mod-2' and that is up and running
   - Test data: `# kubectl get pods -n scenescape`
1. Delete an existing camera from SceneScape.
   - Test data: `In the Retail scene, delete 'camera-mod-2'.`
1. Using kubectl verify that the pod 'camera-mod-2' was removed.
   - Test data: `# kubectl get pods -n scenescape`
1. Tear down the Kubernetes cluster
   - Test data: `# make -C kubernetes uninstall`

## Vision_AI/SceneScape/Functional Tests/30: Verify 3D bounding box with LPR association.

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Ensure that 3d bounding boxes from 3d detectors are used correctly to propagate chained model detections.

### Test requirements mapping

- SAIL-2718: Associate all LPR detections to 3D object detections
- SAIL-2007: 3D Object Detection
- FAREQ-475: The system must support models that output data for 3D object detections.
- ITEP-82000: DeepScenario container exited due to image warping issue

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Run percebro against the input data, using the 3d model chained with the text-detection model and the text-recognition model. (Example uses deepscenario 3d model, td0001 and trresnet):

$ percebro/percebro -i sample_image.png -m vehicle3d+[td0001+trresnet] --preprocess --debug --frames 5 --intrinsics=70

- Test data: `image of vehicles with known tags / image of vehicles with super-imposed text. Known coordinates of the vehicle, and known text.`

## Vision_AI/SceneScape/Functional Tests/31: Toggle to Retrack Child Objects

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies the functionality of retracking child objects in a parent scene. Each child scene can specify in its link whether to retrack objects from the parent scene or not. The test case ensures that this feature is working correctly by toggling the retrack option and observing the behavior.

### Test requirements mapping

- SAIL-2763: Setup a toggle for child tracks in parent scene
- SAIL-3172: Retrack option should be to bypass tracker or not
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely
- ITEP-82623: Objects from the parent scene are not retracked in the child scene

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up Intel® SceneScape with two scenes: a parent scene and a child scene.
1. Link the child scene to the parent scene.
1. Verify the initial state of the retrack option for the child scene
   - Test data: `If the retrack option is enabled, observe that objects from the parent scene are being retracked in the child scene.If the retrack option is disabled, observe that objects from the parent scene are not being retracked in the child scene.`
1. Toggle the retrack option for the child scene
   - Test data: `If the retrack option was initially enabled, disable it.If the retrack option was initially disabled, enable it.`
1. Observe the behavior after toggling the retrack option
   - Test data: `If the retrack option was enabled, verify that objects from the parent scene are now being retracked in the child scene.If the retrack option was disabled, verify that objects from the parent scene are no longer being retracked in the child scene.`
1. Repeat steps 4 and 5 to toggle the retrack option multiple times and verify the expected behavior.
1. Shutdown all instances
   - Test data: `docker compose down --remove-orphans`

## Vision_AI/SceneScape/Functional Tests/32: Verify ID counter metric for Re-ID

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that the ID counter metric correctly counts unique ids

It was agreed that the feature is functionally successful if unique counts for objects is reduced by at least 50% when Re-ID is enabled compared to Re-ID disabled.

### Test requirements mapping

- SAIL-2491: Add counter for number of unique IDs detected in scene
- SAIL-2948: Update RE-ID test case SAIL-T661 to allow for acceptable variation and baselining for regression tracking
- FAREQ-469: The system must reidentify objects and persons that were tracked in the past.
- SAIL-2936: Automate RE-ID scenarios
- SAIL-3519: broken_tests list: automated release test cases
- ITEP-81878: RE-ID test failures due to frame skipping and tracker performance issue

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Start Scene Scape with the default sample configuration.
   - Test data: `# ./deploy.sh
docker-compose.yml already exists. Replace it with docker-compose-example.yml? yes`
1. Subscribe to the MQTT topics and verify that you receive messages from SceneScape.
   - Test data: `This step can be done using the GUI:
1. Open 'MQTT Explorer' and connect to SceneScape using the login data provided by the SceneScape tab.
1. Check if you are receiving events for any of the 2 available scenes (Retail / Queuing):
   /scenescape/data/scene/{Retail/Queuing}/person`
1. Check the 'unique_detection_count' field published through MQTT in the Queuing and Retail scene and verify that these are incrementing continuously.
   - Test data: `This step can be done using the MQTT Explorer by clicking the desired topic: /scenescape/data/scene/{Retail/Queuing}/person`
1. Stop SceneScape and restart it using Re-ID and the VDMS container enabled.
   - Test data: `To stop the previous SceneScape instance, bring down the running containers:

# docker compose down

Modify the docker-compose.yaml from the root directory and:

1. Uncomment the VDMS container section. It should looks something like this:
    vdms:
     image: intellabs/vdms:latest
     init: true
     networks:
       scenescape:
     restart: always

2. Add the reid model to the --camerachain for percebro in the desired scene.
   command:

- "percebro"
  ...
- "--camerachain=retail+reid"
  ...`

1. Check the 'unique_detection_count' field published through MQTT in the Queuing and Retail scene and verify that these stop incrementing after the first video loop.
   - Test data: `Uncomment out the vdms container and add +retail to modelchain for both scenes`

## Vision_AI/SceneScape/Functional Tests/33: Verify Secure Remote Child Connection

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies that a remote child scene can be securely connected to a parent scene running on a different system within the same network. It follows the steps outlined in the child-scenes README documentation to establish a secure connection between the parent and child scenes.

### Test requirements mapping

- SAIL-2560: README document is provided on how to setup a remote child connection
- SAIL-2404: Distributed Scene Hierarchy - Crawl
- FAREQ-309: The system must support a scene to be the child of another scene on a different scene controller.
- SAIL-3183: Distributed Scene Hierarchy - Walk
- ITEP-73641: Remote child scene failed to connected to the parent scene
- ITEP-81917: Connection issues when linking child scenes to parent scenes remotely

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Configure the Network Time Protocol (NTP) server
   - Test data: `On the parent system, enable port forwarding for the NTP server by uncommenting the UDP port in the docker-compose.yml file.On the child system, disable the NTP server by commenting or removing the "ntpserv" entry from the docker-compose.yml file. Replace "ntpserv" with the IP address of the parent system for services that depend on the NTP server.`
1. Set up a secure connection
   - Test data: `On the parent system: a. Remove any existing certificates and certificate authority (CA) files. b. Generate new certificates by running make -C certificates deploy-certificates and providing a certificate password when prompted. c. Copy the generated CA key (secrets/ca/scenescape-ca.key) and CA certificate (secrets/certs/scenescape-ca.pem) to the child system's Intel® SceneScape folder, maintaining the same file paths.On the child system: a. Generate certificates by running make -C certificates deploy-certificates IP_SAN=&lt;child's IP address&gt; and providing the same certificate password as the parent system. b. Deploy Intel® SceneScape on both systems by running the deploy.sh script or restarting the containers if they are already running.`
1. Create a remote child link
   - Test data: `On the child system, launch the Intel® SceneScape web interface, log in, navigate to the child scene, and copy the MQTT credentials.On the parent system, launch the Intel® SceneScape web interface, log in, navigate to the parent scene, and click the "Children" tab under the scene map.Click on "+ Link Child Scene" and provide the following details:Child type: RemoteChild Name: The name of the child sceneHostname or IP: The IP address or hostname of the child systemMQTT Username and Password: The copied values from the child systemTransform type and child transform valuesClick "Add Child Scene" to create the remote child link.`
1. Verify the secure connection
   - Test data: `Check the connection status in the child scene. It should be green (connected) or red (disconnected) securely to the remote child system.Once the connection is established, a client should be able to connect to the parent's event topics and observe base analytics (region of interest, tripwires, etc.) of the parent along with all its children's base analytics (properly transformed).`
1. Shutdown all instances
   - Test data: `docker compose down --remove-orphans`

## Vision_AI/SceneScape/Functional Tests/34: Inferring rotation from velocity

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Rotation from velocity setting in object asset library should control the rotation output of objects of that category from /data/scene/&lt;scene-id&gt; topic.
  When ON, it provides a rotation of the asset that is in the direction of the velocity measured.
  When OFF, the rotation is zero.

Above can be verified using API and mqtt messages.

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/35: tracker-with-no-detections

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that tracker updates objects when there are no detections.

### Test requirements mapping

- SAIL-2778: Number of objects never drops to zero even when nothing is detected

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify that precondition is met
1. number of objects drop to zero in tracker when no detections.
   - Test data: `object detections , empty and non-empty`

## Vision_AI/SceneScape/Functional Tests/36: The system must utilize ISO 8604 UTC format timestamps

**Affected Versions:** 2024.1, 2024.2

### Test summary

- All timestamps must conform to ISO 8604 UTC format, for example "2023-04-19T21:45:06.577Z".

### Test requirements mapping

- FAREQ-366: The system must utilize ISO 8604 UTC format timestamps.

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. In host console enter pgserver container and run psql:

docker exec -it scenescape-pgserver-1 bash
psql -U scenescape

1. For each field mentioned in the picture, verify if the timestamp is in the correct format.
   - Test data: `select map_processed from manager_scene;
select expire_date from django_session;
select applied from django_migrations;
select action_time from django_admin_log;
select attempt_time from axes_accesslog;`
1. Get all our timestamps from the postgres database.
   - Test data: `SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns WHERE data_type LIKE '%timestamp%';`

## Vision_AI/SceneScape/Functional Tests/37: Secrets files permissions settings

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Confirm that deployment script sets group/all permissions on secrets files to read.

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Enter web container:docker exec -it scenescape-web-1 bash
1. Inspect permissions on secrets files:find run/secrets/ -type f | xargs ls -la
   - Test data: `find run/secrets/ -type f | xargs ls -la`

## Vision_AI/SceneScape/Functional Tests/38: Verify that out of the box multi video playback remains in sync

**Affected Versions:** 2024.1, 2024.2

### Test summary

- When playing back videos in the out of box demo scenes, The system should keep each video and time the playback to be synchronized across all of the videos.

### Test requirements mapping

- SAIL-2981: Video playback from multiple video sources does not stay in sync
- FAREQ-346: The system must synchronize the processing of multiple video files.

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/39: Singleton sample code

**Affected Versions:** 2024.1, 2024.2

### Test summary

- See singleton.py for a sample of publishing random values to a singleton topic. You can run this sample by providing the required arguments from within a SceneScape container or adapt it to run in your own code.Here is its help output from inside a SceneScape container:~/scenescape$ docker/scenescape-start --shell
  scenescape@&lt;hostname&gt;:/home/&lt;user&gt;/scenescape$ ./utils/singleton.py -h
  usage: singleton.py [-h] -b BROKER [--port PORT] -p PASSWORD -u USERNAME -i ID [--min MIN] [--max MAX] [-t TIME]

Sample of publishing pseudo-random singleton data to SceneScape.

optional arguments:
-h, --help show this help message and exit
-b BROKER, --broker BROKER
MQTT broker (default: localhost)
--port PORT MQTT port (default: 1883)
-p PASSWORD, --password PASSWORD
MQTT password (default: None)
-u USERNAME, --username USERNAME
MQTT user name (default: None)
-i ID, --id ID Sensor ID (or mqttid) (default: None)
--min MIN Minimum sensor value (default: 0)
--max MAX Maximum sensor value (default: 1)
-t TIME, --time TIME Delay time in seconds between messages (default: 1.0)

Accessing singleton data on scene objectsWhen singleton data applies to a tracked object, it is available in the scene graph update for that object under the "singletons" property. Using the above example of a singleton named "temperature1" then a person traversing that sensor's measurement area will be tagged with an array of values and their associated timestamps:{
"timestamp": "2022-10-05T17:53:33.724Z",
...,
"objects": [
{
"category": "person",
...,
"translation": [
0.5735071548523805,
1.8229405125883953,
0
],
...,
"sensors": {
"temperature1": [
[
"2022-10-05T10:53:31.753z",
72.62185709310417
],
[
"2022-10-05T10:53:32.754z",
77.70613289111834
]
]
}
},
...
]
}

Using this data, a developer can easily write an application to trigger alerts or take other action based on the history of sensor data for a tracked object or person.

### Test requirements mapping

- SAIL-2480: Singleton sensor data not getting tagged on the scene objects
- SAIL-3101: Singleton sensor won't work unless the Name matches the Sensor ID

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Uncomment 1883 port forwarding for broker and Start SceneScape. Make sure that everything is working as expected
   - Test data: `# ./deploy.sh`
1. # Create a new sensor in any Queuing scene and make sure that it's a full scene one.
   - Test data: `Sensor id: temp1
Sensor name: Temperature 1`
1. Create emulate some data for that sensor
   - Test data: `# docker/scenescape-start --shell

# ./utils/singleton.py -a /run/secrets/percebro.auth -i temp1`

1. Open MQTT Explorer and see that when singleton data applies to a tracked object, it is available in the scene graph update for that object under the "singletons" property. Using the above example of a singleton named "temp1" then a person traversing that sensor's measurement area will be tagged with an array of values and their associated timestamps:
   - Test data: `scenescape/regulated/scene/Queuing`

## Vision_AI/SceneScape/Functional Tests/40: Run 3D object detection with LPR pipeline

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify the Vehicle, LP detection and OCR pipeline functionality.

### Test requirements mapping

- SAIL-2828: Wipro enabling - LPR association with 3D object detection
- FAREQ-352: The system must support model chaining where the output of one model is used as the input to the next model.
- ITEP-82000: DeepScenario container exited due to image warping issue

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Follow instructions in How-to-run-LPR-with-3D-object-detection.md
1. Verify published OCR data, and that it matches the expected license plates in the input data.
   Additionally verify the output plate format matches the pattern specified in the model-config for the OCR model.

## Vision_AI/SceneScape/Functional Tests/41: REST API fuzzing

**Affected Versions:** 2024.2

### Test summary

- Use the Microsoft fuzzer to check if the REST API doesn't have issues.

### Test requirements mapping

- SAIL-2037: CT631 - Create fuzzing tools for RESTler
- ITEP-66618: SceneScape Refactoring (Other)
- ITEP-82050: Fuzzing: 3 out of 5 requests failed to execute successfully

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Built the Microsoft restler fuzzer container on your tested machine.
   - Test data: `# git clone https://github.com/microsoft/restler-fuzzer

# cd restler-fuzzer

Make sure that you make the right replacement in the Dockerfile so that it's able to correctly install the python packages using pip. To do so, replace the line:
RUN pip3 install requests applicationinsights
with:
RUN pip3 install requests applicationinsights --break-system-packages

# docker build --build-arg http_proxy=http://proxy-dmz.intel.com:912 --build-arg https_proxy=http://proxy-dmz.intel.com:912 -t restler .`

1. Follow the readme file (tests/security/fuzzing/README.md) to correctly set up the fuzzer.
   - Test data: `Example on how the environment file should look like:

https_proxy=http://proxy-dmz.intel.com:912
instance_ip=10.237.26.63
auth_username=admin
auth_password=authpass
restler_mode=test

# Copy the certificate to the testing directory

cp secrets/certs/scenescape-ca.pem tests/security/fuzzing

# Execute the test as it's mentioned in the documentation:

# docker run --rm -v ./:/workspace restler sh /workspace/run_fuzzing.sh`

## Vision_AI/SceneScape/Functional Tests/42: Calibrate camera in 3D first and calibrate again camera in 2D using April Tag

**Affected Versions:** 2024.1

### Test summary

-

### Test requirements mapping

- SAIL-3102: Camera calibration with AprilTags is not available when transition from Markerless to AprilTag is used
- SAIL-3509: Auto Calibrate button for camera not working in 3D using markerless calibration type
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. SceneScape is started - web interface have one scene or more
   - Test data: `SceneScape is started - web interface have one scene or more`
1. Enter in Queuing scene, Press on Queuing scene
   - Test data: `Enter in Queuing scene`
1. Enter in 3D UI View, Press button 3D
   - Test data: `Enter in 3D UI`
1. Enter in Camera 1(atag-qcam1) menu, Press button to calibrate and Save
   - Test data: `Camera 1(atag-qcam1) is calibrated with new coordinates and this is saved in 3D UI`
1. Exit in 2D UI using Configure Queuing Scene button to recalibrate Camera 1(atag-qcam1).
   - Test data: `Enter in 2D UI`
1. Enter in camera configuration menu using Manage atag-qcam1 button
   - Test data: `Camera 1(atag-qcam1) configuration menu is open`
1. Press button Reset points to view 2D April Tags
   - Test data: `Button is pressed, 2D April Tag appear`
1. Press button Auto calibrate to calibrate camera
   - Test data: `Camera is calibrated automatically with April Tag in 2D View`
1. Press button Save Camera
   - Test data: `Camera 1(atag-qcam1) is calibrated with new coordinates and this is saved in 2D UI. Back in Queuing Scene when session is saved with new configuration`

## Vision_AI/SceneScape/Functional Tests/43: When scene name is updated the changes are reflected in the /data/scene topic metadata content

**Affected Versions:**

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Navigate to a scene settings page
1. Change the name and save settings
1. Open Mqtt explorer and observe the scene updates under /data/scene

## Vision_AI/SceneScape/Functional Tests/44: When scene scale is updated the changes are reflected in the scene controller behavior

**Affected Versions:**

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Go to scene settings page in UI
1. Edit the pixels per meter setting and save settings
1. Go to the scene home page

## Vision_AI/SceneScape/Functional Tests/45: Singleton-persistence

**Affected Versions:**

### Test summary

- To verify that attribute sensors data persists in tracked objects

### Test requirements mapping

- SAIL-481: Persist singleton data on a given object track in the scene graph
- SAIL-3284: Attribute sensors are still tagging old data on new objects

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify pre conditions are met
1. Add a sensor to Queuing scene
   - Test data: `Create a sensor named 'sensor1' of the environment type and a circle area.`
1. Verify attribute sensor.
   - Test data: `Update the sensor1 singleton_type to attribute.`

## Vision_AI/SceneScape/Functional Tests/46: Verify Prevention of Circular Dependency when Adding Child Scenes

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test case verifies that the Intel® SceneScape system prevents the creation of circular dependencies when adding child scenes to a parent scene. A circular dependency occurs when a child scene is linked to a parent scene that is already a child of the child scene, creating an infinite loop. The system should detect and prevent such circular dependencies to maintain the integrity of the scene graph.

### Test requirements mapping

- SAIL-2121: Creating a scene hierarchy with circular dependency causes a server 500 error.

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Set up a parent scene and a child scene in the Intel® SceneScape system.
1. Link the child scene to the parent scene.
1. Attempt to create a circular dependency by linking the parent scene as a child of the child scene.
1. Verify that the system detects and prevents the creation of the circular dependency.
1. Repeat steps 3 and 4 with different combinations of parent and child scenes to ensure consistent behavior.
1. Shutdown all instances

## Vision_AI/SceneScape/Functional Tests/47: temporal fidelity

**Affected Versions:**

### Test summary

- Verify the temporal fidelity i.e the rate of publish of regulated and external data.

### Test requirements mapping

- SAIL-3225: Control the temporal fidelity/resolution of a scene

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Setup scene
   - Test data: `Create a scene "test".`
1. Verify regulate rate of scene
   - Test data: `Update the regulated rate to 1 Hz.`
1. Verify regulate rate of scene
   - Test data: `Update the regulated rate to 10 Hz.`
1. Verify External rate
   - Test data: `Update the external rate of child scene to 10Hz.`
1. Verify External rate
   - Test data: `Update the external rate of child scene to 1Hz.`

## Vision_AI/SceneScape/Functional Tests/48: Validate API spec against OpenAPI 2.0 specification

**Affected Versions:**

### Test summary

- Validate compliance of api.yaml with OpenAPI 2.0 spec.

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Install npm (if you don't have)
   - Test data: `apt install npm`
1. Install npm package to validate swagger doc
   - Test data: `npm install -g swagger-cli@2.0.0`
1. Move to the directory docs/api/
   - Test data: `cd docs/user-guide/api-docs/`
1. validate documentation
   - Test data: `swagger-cli validate api.yaml`

## Vision_AI/SceneScape/Functional Tests/49: Verify 3d object closest face rotation and subdetection annotation

**Affected Versions:**

### Test summary

- Verify the 3d object face perspective correction is working as intended.
  Verify the sub-model detections (i.e. license plate detection) result annotation is mapped/drawn correctly.

### Test requirements mapping

- SAIL-3352: Implement 3d bounding box rotation before cropping for model-chaining.

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/50: Verify bottom-most sub-detection filtering.

**Affected Versions:**

### Test summary

- Ensure bottom-most sub-detection filtering is returning the bottom-most sub-detection only.

### Test requirements mapping

- SAIL-3406: License plate association with 3D object inside of percebro

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Add --filter bottom to the VA
1. Use video with license plates having text in arabic + english.
1. Setup the vehicle 3d + lpr + ocr chained pipeline in DLSPS
1. Verify the sub detections

## Vision_AI/SceneScape/Functional Tests/51: Verify oob scene with parallel model configuration

**Affected Versions:**

### Test summary

- Verify that both the annotation and inference is functional when doing parallel model inference. This is achieved by specifying models using a comma in the camerachain argument for percebro, example: "model1,model2".

### Test requirements mapping

- SAIL-3562: Parallel model inference (annotations) are broken

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Run oob and verify annotations with "retail,apriltag"
1. Run oob and verify annotations with "retail,hpe,apriltag" (Queuing video)

## Vision_AI/SceneScape/Functional Tests/52: Auto-calibration when camera from different scene is added

**Affected Versions:**

### Test summary

-

### Test requirements mapping

- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- SAIL-2524: If a camera from a different scene is added, inform the user when attempting auto calibration

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. SceneScape is started - web interface have one scene
   - Test data: `SceneScape is started - web interface have one scene`
1. Enter in Queuing scene, Press on Queuing scene
   - Test data: `Enter in Queuing scene`
1. Change calibration type to Markerless in Queuing scene settings
1. Enter in 3D UI View, Press button 3D
   - Test data: `Enter in 3D UI`
1. Enter in Camera 1(atag-qcam2) menu, Press button to auto calibrate and Save
   - Test data: `Camera 1(atag-qcam2) is calibrated with new coordinates and this is saved in 3D UI`
1. Enter in the Cameras menu, change the camera1 from Retail to Queuing scene
   - Test data: `Camera1 scene changed from Retail to Queuing`
1. Enter in 3D UI View of Queuing scene, Press button 3D
   - Test data: `Enter in 3D UI`
1. Enter in Camera (camera1) menu, Press button to auto calibrate and Save
   - Test data: `Camera (camera1) is not calibrated`

## Vision_AI/SceneScape/Functional Tests/53: Verify 3D LPR pipeline protection against invalid vertex detections

**Affected Versions:**

### Test summary

- This test case verifies that the model pipeline correctly identifies and discards invalid vertex detections to prevent them from being used in the closest face-correction algorithm.
  Specifically, the system should detect when the vertices (top left, top right, bottom left, bottom right) differ by less than half a pixel and discard such detections.

The way to artificially generate the failing case, is to run 3d LPR pipeline after applying this patch:diff --git a/dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_policies.py b/dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_policies.py
index e8b84de..8ddf0e5 100644
--- a/dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_policies.py
+++ b/dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_policies.py
@@ -76,7 +76,7 @@ def computeObjBoundingBoxParams3D(pobj, item):
pobj.update({
'translation': item['extra_params']['translation'],
'rotation': item['extra_params']['rotation'],

- 'size': item['extra_params']['dimension']

* 'size': [0.01, 0.01, 0.01]
  })

   x_min, y_min, z_min = pobj['translation']

As a result, the vehicle3d+lpdet pipeline didn't crash and no objects are detected.

### Test requirements mapping

- SAIL-3678: Review and validate the latest PRs (1733, 1747, 1748)

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/54: scenescape-sources image builds and contains source code for dependencies

**Affected Versions:**

### Test summary

-

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. make  build-sources-image
1. docker run --rm -it scenescape-sources:latest shls

## Vision_AI/SceneScape/Functional Tests/55: Verify camera_bounds in visibility topic.

**Affected Versions:**

### Test summary

- Verify the camera_bounds for the tracked objects (output of regulated or unregulated scene topics) is present, and correct.
  Use the --visibility_topic in the scene controller command to select from 'unregulated', 'regulated', or 'none'.

### Test requirements mapping

- SAIL-3446: Move heavy compute related to visibility and camera bounds to regulated topic only.

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. - Pass --visibility_topic unregulated in the scene controller command
1. - Pass --visibility_topic regulated in the scene controller command
1. - Pass --visibility_topic none in the scene controller command

## Vision_AI/SceneScape/Functional Tests/56: Test for API handling of large strings

**Affected Versions:**

### Test summary

- Generates a long string.Sends a request to the API with the long string.If the request does not return an error, the test is marked as PASSED.

### Test requirements mapping

- ITEP-18989: Investigate and fix: test case api-large-strings
- ITEP-66618: SceneScape Refactoring (Other)

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. make -C tests api-large-strings

## Vision_AI/SceneScape/Functional Tests/57: Attribute-persistence-along-track

**Affected Versions:**

### Test summary

- To verify that attributes from model chain inferences persist along the track

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify preconditions are met
1. Setup vehicle3D + lpr + ocr
1. Edit the tracker-config.json and restart scene-controller
   - Test data: `Add the following key value to the json file:
      "persist_attributes": {
        "car": [
            {"license_plates": "text"}
        ]
    }`
1. Verify that license_plate text persists
   - Test data: `text shown in the telemetry.`
1. Verify attribute persistence in mqtt

## Vision_AI/SceneScape/Functional Tests/58: Independently Deploy and Interact with Autocalibration service

**Affected Versions:**

### Test summary

- The purpose of this test is to validate whether deploying the Autocalibration service on its own (along with any services it depends on) allows the user to interact with the service's MQTT topic endpoint.

### Test requirements mapping

- ITEP-69628: Validate if each service can be build independently
- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)
- ITEP-72041: [MQTT][API] Service does not respond to request status message being published to endpoint

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, secrets, env etc. using command "make"
1. Make sure that no containers are up by using command "docker ps", and if there are any then use command "docker compose down --remove-orphans" to turn them off
1. Bring up Autocalibration service (and all required) by using command "docker compose up -d camcalibration"
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Publish a payload "isAlive" to the topic /sys/autocalibration/status

## Vision_AI/SceneScape/Functional Tests/59: Independently Deploy and Interact with Controller service

**Affected Versions:**

### Test summary

- The purpose of this test is to validate whether deploying the Controller service on its own (along with any services it depends on) allows the user to interact with the service's MQTT topic endpoint.

### Test requirements mapping

- ITEP-69628: Validate if each service can be build independently
- ITEP-72041: [MQTT][API] Service does not respond to request status message being published to endpoint

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, secrets, env etc. using command "make"
1. Make sure that no containers are up by using command "docker ps", and if there are any then use command "docker compose down --remove-orphans" to turn them off
1. Bring up Controller service (and all required) by using command "docker compose up -d scene"
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
Topics to listen to: "#" (all)
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Publish a payload "isConnected" to the topic /sys/child/status

## Vision_AI/SceneScape/Functional Tests/60: Validate if Scene Controller provides volumetric analytics

**Affected Versions:**

### Test summary

- This test verifies if Scene Controller provides volumetric analytics.
  This means that if the tracking of the object begins as immediately as it interacts with Region of Interest (ROI) or it's buffer, and also when it leaves ROI it's status is updated only after it leaves the ROI entirely.
  This functionality is optional, turned on by selecting option "Volumetric" when setting up ROI. By default tracking object location is triggered only by the center of the object, regardless if it enters or leaves ROI.

### Test requirements mapping

- ITEP-69623: Validate if Scene Controller provides volumetric analytics

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, env and deploy demo scenes using command "make demo"
1. Open configuration for a scene e.g. Queueing.
1. Add a Region of Interest (ROI) by going into Regions section, clicking "+ New Region" and selecting corners of the ROI and close it by clicking on the first corner.
   It is possible to make different shapes as long as any lines don't intersect.

This is the recommended size and placement of the ROI:

1. Add configuration to the created ROI:
1. Add a name
1. Select option "Volumetric"
1. Option "Height" is optional and is meaningless for this test scenario (leave at 1)
1. Option "Buffer" is optional and is validated in different test cases (leave at 0)
1. Click "Save Regions and Tripwires"
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
Topics to listen to: "#" (all)
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Open MQTT Explorer on topic scenescape/event/region/{region_id} and compare its updates to what is happening with the objects in the scene.

## Vision_AI/SceneScape/Functional Tests/61: Test ACC with no map file available produces error

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Verify that the ACC displays an appropriate error message and disables the calibration button when the map file is missing.

### Test requirements mapping

- ITEP-72716: Camcalibration container is restarting on main (deployment with DLS)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Log into SceneScape web app
1. Delete scene map:
   Enter Queuing scene's edit menu.Tick "Clear" next to the Scene MapSave changes
1. Check UI:Enter page for one of the Queuing scene's cameras.Mouse over the "Auto Calibrate" button
1. Check REST in the host machine console:Acquire scenescape-camcalibration container ID with "docker ps"Check container logs with "docker logs {ID_FROM_PREVIOUS_STEP}"
   - Test data: `Expected Result may take some time to appear`

## Vision_AI/SceneScape/Functional Tests/62: Independently Deploy and Interact with Manager service

**Affected Versions:**

### Test summary

- The purpose of this test is to validate whether deploying the Manager service on its own (along with any services it depends on) allows the user to interact with the service's MQTT topic endpoint.

### Test requirements mapping

- ITEP-69628: Validate if each service can be build independently

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, secrets, env etc. using command "make"
1. Make sure that no containers are up by using command "docker ps", and if there are any then use command "docker compose down --remove-orphans" to turn them off
1. Bring up Manager service (and all required) by using command "docker compose up -d web"
1. Interact with the service by querying its readiness endpoint by using this command:
   curl --insecure -X GET https://{local_ip}:443/api/v1/database-ready | grep 'true'10.91.106.170

## Vision_AI/SceneScape/Functional Tests/63: Verify Object Buffer Handling in Scene Volumetric Analytics

**Affected Versions:**

### Test summary

- This test verifies whether the Scene Controller correctly accounts for the object's buffer size when the "Volumetric" option is enabled for a Region of Interest (ROI).

When a buffer value is applied to an object, the system should trigger region events based on the expanded object mesh, not just the original object size. This functionality is optional and is activated by increasing the "Object buffer size in X/Y/Z axis" for the desired object configuration in the Object Library.

By default, object tracking is based solely on the object's center point. With volumetric analytics and buffer enabled, the system should detect entry and exit events based on mesh intersection, including the buffer.

### Test requirements mapping

- ITEP-69623: Validate if Scene Controller provides volumetric analytics
- ITEP-73442: Cannot create Region of Interest

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, env and deploy demo scenes using command "make demo"
1. Open configuration for a scene e.g. Queueing.
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
Topics to listen to: "#" (all)
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Add a Region of Interest (ROI) by going into Regions section, clicking "+ New Region" and selecting corners of the ROI and close it by clicking on the first corner.
   It is possible to make different shapes as long as any lines don't intersect.

This is the recommended size and placement of the ROI:

1. Add configuration to the created ROI:
1. Add a name
1. Select option "Volumetric"
1. Option "Height" is optional and is meaningless for this test scenario (leave at 1)
1. Option "Buffer" is optional and is validated in different test cases (leave at 0)
1. Click "Save Regions and Tripwires"
1. Verify default behavior (no object buffer):
   Open MQTT Explorer on topic scenescape/event/region/{region_id} and compare its updates to what is happening with the objects in the scene.
1. Apply object buffer:
1. Go to Object Library
1. Select the object used in the scene
1. Set desired values for "Object buffer size in {x/y/z}-axis" (e.g. 0.5)
1. Save object configuration by clicking "Update Object"
1. Verify buffer visualization by going into the 3D view of the scene and confirming that the object mesh now includes the buffer (is visually larger)
1. Verify volumetric intersection with buffer adjusted object:
1. Wait for the object to intersect with the ROI boundary
1. Observe the MQTT topic for region events
1. Confirm that entry/exit events are now triggered earlier/later based on the buffered mesh
1. Test clean-up:
1. Reset object buffer to the default value of 0.0 and save changes

## Vision_AI/SceneScape/Functional Tests/64: Verify ROI Buffer Handling in Scene Volumetric Analytics

**Affected Versions:**

### Test summary

- This test verifies whether the Scene Controller correctly accounts for the Region of Interest (ROI) buffer size when the "Volumetric" option is enabled.

When a buffer value is applied to an ROI, the system should trigger region events based on the expanded or reduced ROI mesh, not just the original polygon shape. This functionality is optional and is activated by adjusting the "Buffer" value in the ROI configuration.

By default, region events are triggered when the object’s mesh intersects with the original ROI shape. With volumetric analytics and ROI buffer enabled, the system should detect entry and exit events based on intersection with the buffered ROI mesh, which may be larger or smaller depending on the buffer value.

### Test requirements mapping

- ITEP-69623: Validate if Scene Controller provides volumetric analytics
- ITEP-73442: Cannot create Region of Interest

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build all services, env and deploy demo scenes using command "make demo"
1. Open configuration for a scene e.g. Queueing.
1. Open and configure MQTT Explorer
   - Test data: `protocol: mqtt, host: localhost ip, port: 1883
user: admin password: {SUPASS}
Topics to listen to: "#" (all)
IMPORTANT - supply MQTT Explorer with scenescape-ca.pem file that is created during "make" command execution. It's located in /manager/secrets/certs/`
1. Add a Region of Interest (ROI) by going into Regions section, clicking "+ New Region" and selecting corners of the ROI and close it by clicking on the first corner.
   It is possible to make different shapes as long as any lines don't intersect.

This is the recommended size and placement of the ROI:

1. Add basic configuration to the created ROI:
1. Add a name
1. Select option "Volumetric"
1. Option "Height" is optional and is meaningless for this test scenario (leave at 1)
1. Leave option "Buffer Size" at 0 to compare results when we apply the buffer
1. Click "Save Regions and Tripwires"
1. Verify default behavior (no object buffer):
1. In the 3D view observe and note the size of the ROI
1. Open MQTT Explorer on topic scenescape/event/region/{region_id} and compare its updates to what is happening with the objects in the scene
1. Apply ROI buffer:
1. Go back to configure scene view
1. Go into the Regions tab
1. Set a desired value for "Buffer Size", different than 0.
1. Click "Save Regions and Tripwires"
1. Verify volumetric intersection with buffer:
1. Enter 3D view
1. Note the size of the ROI and compare it to before applying changes to the buffer
1. Wait for the object to intersect with the ROI boundary
1. Observe the MQTT topic for region events
1. Confirm that entry/exit events are now triggered earlier/later based on the buffered mesh

## Vision_AI/SceneScape/Functional Tests/65: Scene Import API

**Affected Versions:**

### Test summary

- This test validates the behavior of the Scene Import API under various conditions including successful imports, empty zip files, invalid zip files, duplicate scenes, and orphaned components. It ensures that the API correctly handles each scenario, returns appropriate responses, and links scene components as expected.

### Test requirements mapping

- ITEP-79163: [Kubernetes][API][UI] Cannot import a scene when deployed on Kubernetes
- ITEP-80141: [Docker][API][UI] Importing a scene results in Server Error (500) on Docker
- ITEP-81834: [Kubernetes][API] Adding camera with minimal payload crashes kubeclient during pipeline generation

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Generate token using curl on host machine:
   curl --location --insecure -X POST \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": {SUPASS}}' \
   https://localhost/api/v1/auth
   - Test data: `{SUPASS} - generated or set during deployment`
1. Verify default behavior:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Retail-import.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step
Test assumes current directory is ~/scenescape`
1. Verify behavior when handling empty zip files:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Empty.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step`
1. Verify behavior when adding duplicate scene:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Retail-import.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step`
1. Verify local scene hierarchy behavior:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Parent.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step`
1. Verify behavior when adding scene with malformed JSON:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Invalid.zip | jqssag
   - Test data: `{TOKEN} - generated in the 1st step`
1. Check Correct behavior of orphaned cameras/sensors:
   Delete 'Retail-import' scene:Find scene UID with: curl --insecure -X GET https://localhost/api/v1/scenes -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" | jqDelete scene with: curl --insecure -X DELETE https://localhost/api/v1/scene/{UID} -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" | jq Re-add 'Retail-import' scene:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Retail-import.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step`
1. Check correct behavior when adding larger file:curl --insecure -X POST https://localhost/api/v1/import-scene/ -H "Authorization: Token {TOKEN}" -F zipFile=@tests/ui/test_media/Intersection-Demo.zip | jq
   - Test data: `{TOKEN} - generated in the 1st step`
1. Test Cleanup:Delete scenes added during the test in the same way 'Retail-import' scene was deleted in step 7

## Vision_AI/SceneScape/Functional Tests/66: Manual Camera Positioning API

**Affected Versions:**

### Test summary

- System must allow user to estimate the camera pose. Users should be able to successfully set and save camera pose settings via API. The camera pose setting may be set via entering parameters through API

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Generate token using curl on host machine:
   curl --location --insecure -X POST \
   -H "Content-Type: application/json" \
   -d '{"username": "admin", "password": {SUPASS}}' \
   https://localhost/api/v1/auth
   - Test data: `{SUPASS} - generated or set during deployment`
1. Get existing cameras' UIDs and Original Transforms from:curl --insecure -X GET https://localhost/api/v1/cameras -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" | jq
   - Test data: `{TOKEN} - generated in the 1st step
{ORIGINAL_CALIBRATION_POINTS} - The "Transform" value in the JSON. Save for the last step of the test`
1. For each camera:Change "Transforms" data with different calibration points using:
   curl --insecure -X POST https://localhost/api/v1/camera/{UID} -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" -d '{"transform_type": "3d-2d point correspondence", "transforms":[{MODIFIED_CALIBRATION_POINTS}]}' | jq
   - Test data: `{TOKEN} - generated in the 1st step
{UID} - from step 2
{MODIFIED_CALIBRATION_POINTS} - chosen arbitrarily, minimum 4 pairs of points.`
1. Make sure data is saved:curl --insecure -X GET https://localhost/api/v1/cameras -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" | jqCompare response data with response from step 3
   - Test data: `{TOKEN} - generated in the 1st step`
1. For each camera:Change "Transforms" data with original calibration points using:
   curl --insecure -X POST https://localhost/api/v1/camera/{UID} -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" -d '{"transform_type": "3d-2d point correspondence", "transforms":[{ORIGINAL_CALIBRATION_POINTS}]}' | jq
   - Test data: `{ORIGINAL_CALIBRATION_POINTS} - listed in the response of Step 2`

## Vision_AI/SceneScape/Functional Tests/67: Scene controller JSON data source support

**Affected Versions:**

### Test summary

- System must allow user to set up a scene and publish scene configuration messages without access to a database through REST API

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. For automatic execution: make -C tests scene-import-json
   For manual steps see below
1. Deploy scenescape:./deploy.shGet auth token through API:curl --location --insecure -X POST \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "{SUPASS}"}' \
    https://localhost/api/v1/authGet Queuing scene JSON file:curl --insecure -X GET https://localhost/api/v1/scene/{SCENE_UID} -H "Content-Type: application/json" -H "Authorization: Token {TOKEN}" | jqSave response as Queuing.json at /scenescape/sampledata
   - Test data: `{SUPASS} - generated during deployment
{SCENE_UID} - 302cf49a-97ec-402d-a324-c5077b280b7b (for Queuing scene)
{TOKEN} - generated in this step`
1. In scenescape/docker-compose.yml at 'scene' service:Remove '--restauth /run/secrets/controller.auth' commandAdd '--data_source /home/scenescape/SceneScape/sample_data/Queuing.json' command
1. Restart scenescape:docker compose down --remove-orphansdocker compose up -d
1. Subscribe to the regulated scene MQTT topic:Enter web container with:
   docker exec -it scenescape-web-1 bashSubscribe to the topic with:
   mosquitto_sub -d -h {BROKER} -p {PORT}\
    --cafile /run/secrets/certs/scenescape-ca.pem \
    -u {USER}\
    -P {PASSWORD}\
    -t "scenescape/regulated/scene/{SCENE_UID}"
   - Test data: `{BROKER}: broker.scenescape.intel.com
{PORT}: 1883
{USER}: admin
{PASSWORD}: change_me
{SCENE_UID} 302cf49a-97ec-402d-a324-c5077b280b7b (for Queuing scene)`
1. Cleanup:
   Exit container with 'exit' commandRevert changes done to docker-compose.yml at step 2docker compose down --remove-orphansdocker compose up -d

## Vision_AI/SceneScape/Functional Tests/68: Validate data persistence after pods restart

**Affected Versions:**

### Test summary

- Edit Scene, and note the changes made.
  Navigate to the home page, then back to the scene. Verify the changes made are persistence .
  From the command line, take down Kubernetes pods.
  From command line, start Kubernetes pods.
  ​Navigate to the Scene and verify all changes made persist across the system restart.

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Edit Scene, and note the changes made
   Navigate to the home page, then back to the scene. Verify the changes made are persistence
   From the command line, restart pods
   - Test data: `# Set namespace
     NAMESPACE="scenescape"

# Delete all pods in namespace

kubectl delete pods --all -n $NAMESPACE

# Wait for all pods to be ready

kubectl wait --for=condition=Ready pod --all -n $NAMESPACE --timeout=300s

# Verify all pods are up and running

kubectl get pods -n $NAMESPACE`

1. ​Navigate to the Scene and verify all changes made persist across the system restart
1. Restart scenescape-pgserver and scenescape-web pods
   Verify all scenes are available
1. Navigate to Web UI and add new Scene
   Restart Postgres and Web UI pods
   Verify that new scene is still available

## Vision_AI/SceneScape/Functional Tests/69: Verify Kind cluster and services work correctly after host machine restart

**Affected Versions:**

### Test summary

- Verify that Kind cluster and all services work properly after restarting host machine.

### Test requirements mapping

- ITEP-82375: [Kubernetes] Kind fail on host restart

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify kind cluster status
   - Test data: `kind get clusters`
1. Check pods status
   - Test data: `kubectl get pods --all-namespaces`
1. Check SceneScape pods status
   - Test data: `NAMESPACE="scenescape"
kubectl get all -n $NAMESPACE`
1. Restart machine
   - Test data: `sudo reboot`
1. Verify SceneScape after machine restart
   - Test data: `# Check docker status
     sudo systemctl status docker

# Check kind cluster

kind get clusters

# Check all pods status

kubectl get pods --all-namespaces

# Check SceneScape status

NAMESPACE="scene-namespace"
kubectl get all -n $NAMESPACE`

1. Navigate to the Scene and verify that data persists after host machine restart
1. Navigate to Web UI and add new Scene

## Vision_AI/SceneScape/Functional Tests/70: Verify Scenescape containers work correctly after host machine restart

**Affected Versions:**

### Test summary

- Verify that SceneScape works properly after restarting host machine

### Test requirements mapping

-

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Verify initial statof SceneScape containers
   - Test data: `docker ps`
1. Restart machine
   - Test data: `sudo reboot`
1. Verify SceneScape after machine restart
   - Test data: `sudo systemctl status docker

docker ps`

1. Navigate to the Scene and verify that data persists after host machine restart
1. Restart scenescape-pgserver-1 and scenescape-web-1 containers
   Verify all scenes are available
1. Navigate to Web UI and add new Scene

## Vision_AI/SceneScape/Functional Tests/71: Dynamic Camera Management

**Affected Versions:**

### Test summary

- Verify if cameras can be added, removed or modified dynamically in kubernetes environment

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Create an empty scene
   - Test data: `example payload:
scene map: use retail.png included in the demo scenes
pixels per meter: 100`
1. monitor the activity within kind cluster
   - Test data: `kubectl get pods -n scenescape 
or
k9s (live feed)`
1. Add a camera
   - Test data: `example payload:
video source = rtsp://mediaserver:8554/retail-cam1
camera chain = retail`
1. Verify if a pod has been created dynamically for the camera
1. Go into the camera settings and manually calibrate it
   - Test data: `set randomly 4 spots on the camera image and 4 on the scene`
1. Change any value in the camera and save it
1. Verify if a pod has been recreated dynamically for the camera
1. Remove the camera
1. Verify if the camera pod has been deleted

## Vision_AI/SceneScape/Functional Tests/72: Verify Camera Sources

**Affected Versions:**

### Test summary

- Verify camera source and pipelines work for RTSP and file inputs

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Create an empty scene
   - Test data: `example payload:
scene map: use retail.png included in the demo scenes
pixels per meter: 100`
1. Add a camera
   - Test data: `payload:
Video Source: rtsp://mediaserver:8554/queuing-cam1
camera chain = retail`
1. Verify if the camera is going online and providing visuals
1. Create another camera
   - Test data: `payload:
Video Source: file://qcam1.ts
camera chain = retail`
1. Verify if the camera is going online and providing visuals

## Vision_AI/SceneScape/Functional Tests/73: Detection Model Threshold

**Affected Versions:**

### Test summary

- Verify if model threshold works correctly. The lower the threshold the harsher detection of the objects

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Import a demo scene or use the one that comes with deployed demo scenescape
1. Modify the settings of a camera to lower the threshold to the minimum
   - Test data: `1. Click on "(Advanced) Use Camera Pipeline"
1. Click on "Generate Pipeline Preview"
1. Find a word "gvadetect" in the generated pipeline code
1. Insert "threshold=0.01" after it`
1. Wait for the camera to go online and verify if the change has been applied
1. Modify the settings of a camera to lower the threshold to the maximum
   - Test data: `1. Click on "(Advanced) Use Camera Pipeline"
1. Click on "Generate Pipeline Preview"
1. Find a word "gvadetect" in the generated pipeline code
1. Insert "threshold=0.99" after it`
1. Wait for the camera to go online and verify if the change has been applied

## Vision_AI/SceneScape/Functional Tests/74: Model Chaining in Kubernetes

**Affected Versions:**

### Test summary

- verify if model chaining works correctly
  model chaining documents can be found here: https://github.com/open-edge-platform/scenescape/blob/release-2025.2/docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md#model-chaining

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P2

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Enter configuration view of a valid scene with cameras
1. Modify a camera to change model chaining settings
   - Test data: `set Camera Chain = retail+reid`
1. Verify incoming data via MQTT topic
   - Test data: `scenescape/data/scene/{scene_id}/person`

## Vision_AI/SceneScape/Functional Tests/75: GPU Support in Dynamic Pipelines

**Affected Versions:**

### Test summary

- Verify that GPU can be used and works correctly when used with dynamic pipeline generation

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Enter configuration view of a valid scene with cameras
1. Modify a camera to change model chaining settings to GPU
   - Test data: `set Camera Chain = retail=GPU+reid=GPU`
1. Verify incoming data via MQTT topic
   - Test data: `scenescape/data/scene/{scene_id}/person`

## Vision_AI/SceneScape/Functional Tests/76: Kubeclient supports cameras with custom models and custom model_config after restart

**Affected Versions:**

### Test summary

- Verify that kubeclient correctly handles cameras configured with a custom model configuration file (including non-default models like reid) after a restart.

### Test requirements mapping

- ITEP-78992: Add / update dynamic Camera Configuration test cases

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Functional Tests/77: Detect AprilTags from DLStreamer input

**Affected Versions:**

### Test summary

- Receive a message from DLStreamer containing image data

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Receive message from DLStreamer containing image
1. Decode base64 image
1. Detect all visible AprilTags in the frame

## Vision_AI/SceneScape/Functional Tests/78: ACC succeeds with all unoccluded AprilTags using known camera intrinsics

**Affected Versions:**

### Test summary

- Verify that Auto Camera Calibration (ACC) successfully computes camera pose when all AprilTags are visible and camera intrinsics are provided.

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register a valid scene containing known AprilTag 3D positions
1. Provide an image where all AprilTags are fully visible and unobstructed
1. Start auto calibration including known camera intrinsics in the request
1. Poll calibration status until completion

## Vision_AI/SceneScape/Functional Tests/79: ACC succeeds with randomly occluded AprilTags while estimating camera intrinsics

**Affected Versions:**

### Test summary

- Verify that ACC can estimate camera intrinsics and successfully calibrate even when AprilTags are randomly occluded

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register a valid scene containing known AprilTag 3D positions
1. Provide an image where a random subset of AprilTags is occluded
1. Start auto calibration without providing camera intrinsics in the request
1. Poll calibration status until completion

## Vision_AI/SceneScape/Functional Tests/80: ACC returns error after MAX attempts when all AprilTags are occluded

**Affected Versions:**

### Test summary

- Verify that an error occured when no AprilTags are visible

### Test requirements mapping

-

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register a valid scene
1. Provide an image where all AprilTags are fully occluded
1. Start auto calibration
1. Poll calibration status
