# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import re
import time
import sys
import pytest
import argparse
import json
import paths
import numpy as np

percebro = paths.init()

from percebro.inferizer import Inferizer
from percebro.modelchain import ModelChain
from percebro import modelchain
from scene_common.timestamp import get_iso_time, get_epoch_time
from scene_common.mqtt import PubSub


CVCORES = 2
OVCORES = 4

def on_connect_image(mqttc, obj, flags, rc):
  """! Call back fuction for test_publish_events. Subscribes
  to CMD_CAMERA topic

  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    flags     the response sent by the broker
  @param    rc        the connection result
  """
  print( "Connected to MQTT Broker" )
  mqttc.subscribe(PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id="camera1"), 0)

  return

def on_message_image(mqttc, obj, msg):
  """! Call back fuction for test_publish_events for receiving
  messages

  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    msg       the instance of MQTTMessage. Has members topic, payload, etc.
  """
  pytest.msg = str(msg.payload.decode("utf-8"))

  if pytest.msg:
    mqttc.loopStop()

  return

def test_buildArgparser(params):
  """! verifies the output of 'buildArgparser' function

  @param    params     fixture which contains percebro arguments

  """
  pytest.args = percebro.build_argparser().parse_args(['-m', params['model'],\
                                                       '-i', params['camera'], \
                                                       '--intrinsics', params['intrinsics'], \
                                                      '--cameraid', params['cameraid']])

  assert pytest.args.broker == 'localhost'
  assert len(pytest.args.camera) > 0
  assert pytest.args.camerachain == 'retail+reid'
  assert pytest.args.cvcores == CVCORES
  assert pytest.args.ovcores == OVCORES
  assert pytest.args.rootcert == '/run/secrets/certs/scenescape-ca.pem'

  return

def test_setup_mqtt_for_other_tests():
  # FIXME - test functions rely on mqtt_client being set up ahead of
  #         time. Putting it in a global and hoping it gets there in
  #         time doesn't seem like a good way to handle it.
  pytest.mqtt_client = PubSub(None, None, pytest.args.rootcert, pytest.args.broker)
  return

def test_getMACAddress():
  """!  verifies the output of 'getMACAddress' function

  """
  os.environ['MACADDR'] = '54:b2:03:fd:36:1e'
  pytest.mac_addr = percebro.getMACAddress()
  pattern = re.compile(r'(?:[0-9a-fA-F]:?){12}')
  matchSet = re.findall(pattern, pytest.mac_addr)

  del os.environ['MACADDR']
  pytest.mac_addr = percebro.getMACAddress()
  pattern = re.compile(r'(?:[0-9a-fA-F]:?){12}')
  matchUnset = re.findall(pattern, pytest.mac_addr)

  assert len(matchSet) > 0
  assert len(matchUnset) > 0

  return

def test_setupCameras():
  """! verifies the output of 'setupCameras' function

  """
  pytest.cams = percebro.setupCameras(pytest.mac_addr,
                                      pytest.args.camera,
                                      pytest.args.intrinsics,
                                      pytest.args.distortion,
                                      pytest.args.aspect,
                                      pytest.args.cameraid,
                                      pytest.args.realtime,
                                      pytest.args.usetimestamps,
                                      pytest.args.preprocess,
                                      pytest.args.unwarp)

  assert len(pytest.cams) > 0

  return

def test_mqttDidConnect():
  """! verifies the output of 'mqttDidConnect' function

  """
  userdata = None
  flags = 1
  rc = 0
  percebro.cams = pytest.cams
  ret = percebro.mqttDidConnect(pytest.mqtt_client, userdata, flags, rc)

  assert ret == None
  assert percebro.cams[0].sendImage == True

  return

@pytest.mark.parametrize("name, names, expected_result",
                        [("cam_1_test", ["cam_2_test", "cam_3_test", "cam_4_test"], "1"),
                        ("cam_1_test", ["cam_2_test"], "cam_2_test")])
def test_findUnique(name, names, expected_result):
  """! Verifies the output of 'scenescape.scenescape.findUnique()' method.

  @param    name              A name to find the unique characters
  @param    names             List of names with a common prefix and suffix
  @param    expected_result   Expected Result
  """

  result = percebro.findUnique(name, names)

  assert result == expected_result
  return

@pytest.mark.parametrize("topic",
                         [(PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id="camera1"))])
def test_handleCameraMessage(topic):
  """! verifies the output of 'handleCameraMessage' function

  @param    topic     the mqtt topic to receive message

  """
  message = argparse.Namespace()
  message.payload = b"getimage"
  message.topic = topic
  ret = percebro.handleCameraMessage(pytest.mqtt_client, None, message)

  assert ret == None
  assert percebro.cams

  return

def test_publishObjects(video_data):
  """! verifies the output of 'publishObjects' function

  @param    video_data     A VideoFrame object that stores information about a frame

  """
  now = get_epoch_time()
  video_data.end = now
  ts = get_iso_time(now)
  ts_end = get_iso_time(video_data.end)

  cam = pytest.cams[0].mqttID
  fps = 1
  otype = 'motion'
  ogroup = [{'category': 'motion',
            'bounding_box': {'x': 20, 'y': 80, 'width': 640, 'height': 480},
            'id': 1}]

  ret = percebro.publishObjects(ogroup,
                                ts,
                                pytest.mac_addr,
                                cam,
                                pytest.mqtt_client,
                                fps,
                                ts_end,
                                video_data.end - video_data.begin,
                                video_data.cam.intrinsics.asDict())
  assert ret == None

  return

def test_loadModelConfig(params):
  """! verifies the output of 'loadModelConfig' function

  @param    params     param fixture which contains percebro arguments

  """
  pytest.modelconfig = params['modelconfig']
  Inferizer.loadModelConfig(pytest.modelconfig)
  pytest.visionModels = Inferizer.visionModels

  assert 'retail' in Inferizer.visionModels
  assert 'reid' in Inferizer.visionModels

  return

def test_setupModels(params, model_parser, inference_params):
  """! verifies the output of 'setupModels' function

  @param    params     param fixture which contains percebro arguments

  """
  models = model_parser.setupModels(inference_params)
  expected_models = params['model'].split('+')

  assert list(models.keys()) == expected_models
  return

def test_sortDependencies(model_parser, inference_params):
  """! verifies the output of 'ModelChain.sortDependencies' function

  """
  models = model_parser.setupModels(inference_params)
  pytest.ordered = ModelChain.sortDependencies(models)

  pytest.actual = pytest.ordered
  pytest.expected = ['reid', 'retail']

  assert pytest.expected == pytest.actual

  return

@pytest.mark.parametrize("models", [('model_knn'), ('model_retail')])
def test_startEngine(models, request):
  """! verifies the output of 'models' and 'vision_models' from function 'startEngine'

  @param    threshold     Threshold to filter keypoints.
  @param    ovcores       Number of OpenVINO infer requests to be created
  @param    models        Contains detection models parsed from input arguments
  @param    request       used to request the fixture

  """
  result = request.getfixturevalue(models)

  for m in result.keys():
    assert result[m].engine is not None

  for m in modelchain.Inferizer.visionModels.keys():
    assert modelchain.Inferizer.visionModels[m]['engine'] is not None

  return

def test_addResults(video_data, output_ready, model_chain):
  """! verifies the output of 'addResults' function

  @param    video_data     A VideoFrame object that stores information about a frame
  @param    output_ready   A list of detected objects used for test

  """
  odata = output_ready[0][1]
  video_data.addResults('retail', model_chain.orderedModels, odata)
  video_data.addResults('reid', model_chain.orderedModels, odata)

  assert 'retail' in video_data.output
  assert 'reid' in video_data.output

  return

def test_annotateObjects(video_data):
  """! verifies the output of 'annotateObjects' function

  @param    video_data     A VideoFrame object that stores information about a frame

  """
  objects = {"person": [{
                "id": 1,
                "category": "person",
                "confidence": 0.76,
                "bounding_box_mp": {"x": -0.55, "y": -0.16, "width": 0.15, "height": 0.50},
                "center_of_mass": {"x": 33, "y": 218, "width": 30, "height": 72.25},
                "bounding_box_px": {"x": 3, "y": 146, "width": 91.0, "height": 289.0}
                }]
              }
  bbox = objects["person"][0]["bounding_box_px"]
  expected_color = (0, 0, 255)
  frame = video_data.frames[0]

  flat_objects = ModelChain.flatten(objects)
  video_data.annotateObjects(frame, flat_objects)

  assert np.array_equal(frame[bbox["y"], bbox["x"]], np.array(expected_color))
  assert np.array_equal(frame[int(bbox["y"] + bbox["height"]),
                              int(bbox["x"] + bbox["width"])],
                        np.array(expected_color))

  return

def test_cropBounds(video_data, output_ready):
  """! verifies the output of 'cropBounds' function

  @param    video_data     A VideoFrame object that stores information about a frame
  @param    output_ready   A list of detected objects used for test

  """
  input = output_ready[0]
  pytest.fdata = input[1].data[0]
  frame = video_data.frames[0]
  bounds = [{'category': 'motion',
            'bounding_box': {'x': 20, 'y': 80, 'width': 640, 'height': 480},
            'id': 1}]

  cropped_frames = video_data.cropBounds(frame, bounds)
  assert cropped_frames

  return

def test_annotateHPE(video_data, output_ready):
  """! verifies the output of 'annotateHPE' function

  @param    video_data     A VideoFrame object that stores information about a frame
  @param    output_ready   A list of detected objects used for test

  """
  obj = output_ready[0][1].data[0][0]
  obj['pose'] = [(138, 163), (127, 193), (116, 208), (127, 260),
                (150, 301), (138, 178), (161, 163), (157, 144),
                (142, 286), (168, 335), (187, 395), (161, 279),
                (172, 331), (123, 365), (135, 159), (138, 155),
                (112, 163), ()]

  frame = video_data.frames[0]
  ret = video_data.annotateHPE(frame, obj)

  assert ret == None

  return

def test_flattenAllObjects():
  """! verifies the output of 'flattenAllObjects' function

  """
  allObjects = {'motion': [{'category': 'motion',
                'bounding_box': {'x': 0, 'y': 0, 'width': 640, 'height': 480
                }}]}

  keys = ['category', 'bounding_box', 'id']

  pytest.flatObjects = ModelChain.flatten(allObjects)

  assert pytest.flatObjects

  for k in keys:
    assert k in pytest.flatObjects[0]

  return

def test_publishImage(video_data, params):
  """! verifies the output of 'publishImage' function

  @param    video_data     A VideoFrame object that stores information about a frame

  """

  client = PubSub(params['auth'], None, params['rootcert'],
                  params['broker_url'], params['broker_port'])
  client.onConnect = on_connect_image
  client.onMessage = on_message_image
  client.connect()
  client.loopStart()
  topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id="camera1")
  time.sleep(3)
  percebro.publishImage(topic, video_data.frames[0], video_data, client, get_epoch_time(), None)
  time.sleep(3)
  client.loopStop()

  msg = json.loads(pytest.msg)
  assert msg
  assert msg['timestamp']
  assert msg['id']
  assert msg['image']

  return

def test_main(params):
  """! verifies the output of 'main' function

  @param    params     param fixture which contains percebro arguments

  """
  sys.argv = ['', 'percebro', '--camera', 'sample_data/apriltag-cam1.mp4',
              '--cameraid', params['cameraid'], '--camerachain', 'apriltag',
              '--intrinsics', params['intrinsics'],
              '--modelconfig', 'model-config.json',
              '--stats', '--debug', '--frames', params['frames'],
              '--virtual', '[[250,100,640,480]]',
              '--aspect', '4:3', '--usetimestamps', '--preprocess']

  ret = percebro.main()

  assert ret is None
  assert percebro.cams
  assert percebro.sendAllCamImages is False

  return
