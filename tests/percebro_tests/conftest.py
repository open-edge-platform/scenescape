# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import pytest
import paths

percebro = paths.init()

from percebro.inferizer import InferenceParameters
from percebro.modelchain import ModelChain
from percebro.videoframe import VideoFrame
from percebro import modelchain, videosource
from scene_common.timestamp import get_epoch_time
import tests.common_test_utils as common

VIDEO_PATH = "sample_data/apriltag-cam1.mp4"
DEFAULT_INTRINSICS = "{\"fov\":70}"
TEST_NAME = "NEX-T10452"

def pytest_sessionstart(session):
  """! Executes at the start of the session. """

  print(f"Executing: {TEST_NAME}")

def pytest_sessionfinish(session, exitstatus):
  """! Executes at the end of the session. """
  common.record_test_result(TEST_NAME, exitstatus)

#fixture to create percebro arguments
@pytest.fixture(scope='module')
def params():
  params = {}
  params['model'] = "retail+reid"
  params['camera'] = VIDEO_PATH
  params['cameraid'] = 'camera1'
  params['intrinsics'] = DEFAULT_INTRINSICS
  params['modelconfig'] = "model-config.json"
  params['frames'] = '500'
  params['cvcores'] = '2'
  params['ovcores'] = 4
  params['threshold'] = '0.5'
  params['auth'] = '/run/secrets/controller.auth'
  params['rootcert'] =  '/run/secrets/certs/scenescape-ca.pem'
  params['broker_url'] = 'broker.scenescape.intel.com'
  params['broker_port'] = 1883
  params['ovmshost'] = "ovms:9000"

  return params

#fixture to prepare video Data
@pytest.fixture(scope='module')
def video_data():
  mac_addr = percebro.getMACAddress()
  camera = [VIDEO_PATH]
  intrinsics = [DEFAULT_INTRINSICS]
  cams = percebro.setupCameras(mac_addr, camera, intrinsics, None, None,
                      ['camera1'], False, False, False, False, False)

  now = get_epoch_time()
  video = videosource.VideoSource(VIDEO_PATH, None, None)
  frame = video.capture()
  vdata = VideoFrame(cams[0], frame, None)
  vdata.begin = now
  vdata.frameCount = 1

  return vdata

@pytest.fixture(scope='module')
def inference_params(params):
  return InferenceParameters(params['threshold'], params['ovcores'], params['ovmshost'])

@pytest.fixture(scope='module')
def model_chain(params, inference_params):
  modelchain.Inferizer.loadModelConfig(params['modelconfig'])
  return ModelChain(params['model'], inference_params)

#fixture to create a list of input dataset
@pytest.fixture(scope='module')
def input_ready(video_data, model_chain):
  model_chain.prepareInput(video_data)
  return model_chain.inputReady

#fixture to create a list of output dataset
@pytest.fixture(scope='module')
def output_ready(input_ready):
  output_ready = []

  detect = [{'id': 1,
            'category': 'person',
            'confidence': 0.8976750373840332,
            'bounding_box': {'x': 1, 'y': 220, 'width': 97, 'height': 200},
            'center_of_mass': {'x': 33, 'y': 270, 'width': 32.333333333333336, 'height': 50.0}}]

  output_ready = input_ready
  output_ready[0][1].data = [detect]

  return output_ready

@pytest.fixture(scope='module')
def model_parser(params):
  modelchain.Inferizer.loadModelConfig(params['modelconfig'])
  parser = ModelChain.Stack(params['model'])
  parser.groupDependencies()
  return parser

@pytest.fixture(scope='module')
def model_parser_knn(params):
  modelchain.Inferizer.loadModelConfig(params['modelconfig'])
  parser = ModelChain.Stack('motion-knn')
  parser.groupDependencies()
  return parser

#fixture to motion-knn model
@pytest.fixture(scope='module')
def model_knn(model_parser_knn, inference_params):
  return model_parser_knn.setupModels(inference_params)

#fixture to retail+[reid] model
@pytest.fixture(scope='module')
def model_retail(model_parser, inference_params):
  return model_parser.setupModels(inference_params)
