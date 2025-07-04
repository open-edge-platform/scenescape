# Security malformed data tests

These tests check if system rejects malformed data correctly.

## Description

### Feeding malformed data to Scene controller.

This sends invalid sensor (camera) data thru MQTT, the tester must visually verify on the scene page whether the scene and camera feed get updated.

The test will cycle thru 13 tests. It will publish 500 frames for each of the steps.

Step 1: Invalid timestamp
Step 2: Invalid sensor ID.
Step 3: Invalid confidence (0 and negative)
Step 4: Invalid (negative) bounding box width
Step 5: Invalid (negative) bounding box height
Step 6: Invalid (negative) Center of Mass width
Step 7: Invalid (negative) Center of Mass height
Step 8: Invalid (negative and non-sequential) inference id
Step 9: Invalid (negative) framerate.
Back to step 0.

## How to run

Run the test_malformed_json.sh shell script. It will load the required containers and analyze the log for pass/fail criteria.

```
jrmencha@nuc:~/github/applications.ai.scene-intelligence.scenescape$ tests/security/malformed_data/test_malformed_json.sh
1517d5cc5a268485789347b393dba96709142884e21aa4ad464856b04c88523d
Creating applicationsaisceneintelligencescenescape_ntp_1 ...
Creating applicationsaisceneintelligencescenescape_pgserver_1 ...
Creating applicationsaisceneintelligencescenescape_broker_1 ...
Creating applicationsaisceneintelligencescenescape_ntp_1
Creating applicationsaisceneintelligencescenescape_broker_1
Creating applicationsaisceneintelligencescenescape_pgserver_1 ... done
Creating applicationsaisceneintelligencescenescape_web_1 ...
Creating applicationsaisceneintelligencescenescape_broker_1 ... done
Creating applicationsaisceneintelligencescenescape_scene_1 ...
Creating applicationsaisceneintelligencescenescape_scene_1 ... done
TIMEZONE IS
Getting MAC the hard way
Connecting to broker broker.scenescape.intel.com
Models:
   apriltag {'name': 'apriltag', 'device': 'CPU', 'depends': None}
   retail {'name': 'retail', 'device': 'CPU', 'depends': None}
   reid {'name': 'reid', 'device': 'CPU', 'depends': 'retail'}
Ordered: ['apriltag', 'reid', 'retail']
Range camera1 0 178.5
Range camera2 0 178.5
Starting model apriltag on CPU
Starting model retail on CPU
Starting model reid on CPU
1 : Setting timestamp to -1 for id camera1
4 scenescape/data/sensor/person/sensor1 {"timestamp": "-1", "id": "sensor1", "objects": [{"id": 1, "category": "person", "confidence": 0.8713905215263367, "bounding_box": {"x": 2, "y": 6, "width": 119, "height": 256}, "center_of_mass": {"x": 41, "y": 70, "width": 39.666666666666664, "height": 64.0}}], "rate": 1.1}

2 : Setting bad sensor id  invalid!
9 scenescape/data/sensor/person/invalid! {"timestamp": "2021-10-11T23:10:00.981Z", "id": "invalid!", "objects": [{"id": 1, "category": "person", "confidence": 0.9897421598434448, "bounding_box": {"x": 434, "y": 204, "width": 204, "height": 282}, "center_of_mass": {"x": 502, "y": 274, "width": 68.0, "height": 70.5}}], "rate": 1.2}

3 : Setting bad inference data (confidence) for id camera1
14 scenescape/data/sensor/person/sensor3 {"timestamp": "2021-10-11T23:10:01.072Z", "id": "sensor3", "objects": [{"id": 1, "category": "person", "confidence": 0.0, "bounding_box": {"x": 259, "y": -1, "width": 101, "height": 240}, "center_of_mass": {"x": 292, "y": 59, "width": 33.666666666666664, "height": 60.0}}, {"id": 2, "category": "person", "confidence": -0.88, "bounding_box": {"x": 387, "y": 3, "width": 108, "height": 205}, "center_of_mass": {"x": 423, "y": 54, "width": 36.0, "height": 51.25}}], "rate": 1.2}

4 : Setting bad inference data (bbox width) for id camera2
19 scenescape/data/sensor/person/sensor4 {"timestamp": "2021-10-11T23:10:01.183Z", "id": "sensor4", "objects": [{"id": 1, "category": "person", "confidence": 0.998502254486084, "bounding_box": {"x": 259, "y": -1, "width": -101, "height": 240}, "center_of_mass": {"x": 292, "y": 59, "width": 33.666666666666664, "height": 60.0}}, {"id": 2, "category": "person", "confidence": 0.8835878372192383, "bounding_box": {"x": 387, "y": 3, "width": -108, "height": 205}, "center_of_mass": {"x": 423, "y": 54, "width": 36.0, "height": 51.25}}], "rate": 1.2}

5 : Setting bad inference data (bbox height) for id camera1
24 scenescape/data/sensor/person/sensor5 {"timestamp": "2021-10-11T23:10:01.275Z", "id": "sensor5", "objects": [{"id": 1, "category": "person", "confidence": 0.998502254486084, "bounding_box": {"x": 259, "y": -1, "width": 101, "height": -240}, "center_of_mass": {"x": 292, "y": 59, "width": 33.666666666666664, "height": 60.0}}, {"id": 2, "category": "person", "confidence": 0.8835878372192383, "bounding_box": {"x": 387, "y": 3, "width": 108, "height": -205}, "center_of_mass": {"x": 423, "y": 54, "width": 36.0, "height": 51.25}}], "rate": 1.3}

6 : Setting bad inference data (COM width) for id camera2
29 scenescape/data/sensor/person/sensor6 {"timestamp": "2021-10-11T23:10:01.379Z", "id": "sensor6", "objects": [{"id": 1, "category": "person", "confidence": 0.998502254486084, "bounding_box": {"x": 259, "y": -1, "width": 101, "height": 240}, "center_of_mass": {"x": 292, "y": 59, "width": -33.666666666666664, "height": 60.0}}, {"id": 2, "category": "person", "confidence": 0.8835878372192383, "bounding_box": {"x": 387, "y": 3, "width": 108, "height": 205}, "center_of_mass": {"x": 423, "y": 54, "width": -36.0, "height": 51.25}}], "rate": 1.3}

7 : Setting bad inference data (COM height) for id camera1
34 scenescape/data/sensor/person/sensor7 {"timestamp": "2021-10-11T23:10:01.459Z", "id": "sensor7", "objects": [{"id": 1, "category": "person", "confidence": 0.998502254486084, "bounding_box": {"x": 259, "y": -1, "width": 101, "height": 240}, "center_of_mass": {"x": 292, "y": 59, "width": 33.666666666666664, "height": -60.0}}, {"id": 2, "category": "person", "confidence": 0.8835878372192383, "bounding_box": {"x": 387, "y": 3, "width": 108, "height": 205}, "center_of_mass": {"x": 423, "y": 54, "width": 36.0, "height": -51.25}}], "rate": 1.3}

8 : Setting bad inference id for id camera2
39 scenescape/data/sensor/person/sensor8 {"timestamp": "2021-10-11T23:10:01.576Z", "id": "sensor8", "objects": [{"id": -100, "category": "person"}, {"id": 200000000, "category": "person", "confidence": 0.8835878372192383, "bounding_box": {"x": 387, "y": 3, "width": 108, "height": 205}, "center_of_mass": {"x": 423, "y": 54, "width": 36.0, "height": 51.25}}], "rate": 1.3}

9: Sending bad frame rate for id camera1
44 scenescape/data/sensor/person/sensor9 {"timestamp": "2021-10-11T23:10:01.662Z", "id": "sensor9", "objects": [{"id": 1, "category": "person", "confidence": 0.9929850697517395, "bounding_box": {"x": 261, "y": -1, "width": 106, "height": 224}, "center_of_mass": {"x": 296, "y": 55, "width": 35.333333333333336, "height": 56.0}}], "rate": -1000}

49 scenescape/data/sensor/person/camera2 {"timestamp": "2021-10-11T23:10:01.754Z", "id": "camera2", "objects": [{"id": 1, "category": "person", "confidence": 0.9956735968589783, "bounding_box": {"x": 26, "y": 156, "width": 206, "height": 311}, "center_of_mass": {"x": 94, "y": 233, "width": 68.66666666666667, "height": 77.75}}], "rate": 1.4}

 docker logs 970aa047d976 > test_output.log
Stopping applicationsaisceneintelligencescenescape_scene_1      ... done
Stopping applicationsaisceneintelligencescenescape_web_1    ... done
Stopping applicationsaisceneintelligencescenescape_broker_1 ... done
Stopping applicationsaisceneintelligencescenescape_pgserver_1   ... done
Stopping applicationsaisceneintelligencescenescape_ntp_1    ... done
Removing applicationsaisceneintelligencescenescape_scene_1      ... done
Removing applicationsaisceneintelligencescenescape_web_1    ... done
Removing applicationsaisceneintelligencescenescape_broker_1 ... done
Removing applicationsaisceneintelligencescenescape_pgserver_1   ... done
Removing applicationsaisceneintelligencescenescape_ntp_1    ... done
Network scenescape_test is external, skipping
scenescape_test
8 frames failed validation. Expected 8 to fail
1 frames from unknown ID. Expected 1
Validate JSON files: Test Passed


```
