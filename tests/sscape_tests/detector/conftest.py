#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import os
import pytest
import uuid
import numpy as np
from PIL import Image
from PIL import ImageDraw
from unittest.mock import MagicMock

from percebro import videosource, detector, detector_tesseract, detector_atag, detector_motion, \
  detector_geti, detector_ocr, detector_pose
from scene_common.timestamp import get_epoch_time
from tests.sscape_tests.detector.config import ovms_retail_model, ovms_hpe_model
import tests.common_test_utils as common

os.unsetenv('http_proxy')
os.unsetenv('https_proxy')

VIDEO_PATH = "sample_data/apriltag-cam1.mp4"
ATAG_VIDEO_PATH = "sample_data/apriltag-cam1.mp4"
MOTION_VIDEO_PATH = "sample_data/qcam1.mp4"
model = 'retail'
pose_model = 'hpe'
reid_model = 'reid'
atag_model = 'apriltag'
motion_model = {'threshold': 400, 'history': 100}
geti_path = "/opt/intel/openvino/deployment_tools/intel_models/intel/"
dummy_model_name = "person-detection-retail-0013"
geti_model = {
  "model": "geti_ssd",
  "engine": "GetiDetector",
  "keep_aspect": 0,
  "directory": geti_path + dummy_model_name,
  "dummy_model": geti_path + dummy_model_name +"/FP32/" + dummy_model_name + ".xml",
  "categories" : ["background", "person"]
}
tesseract_model = 'tesseract'
device = 'CPU'
plugin = None
threshold = 0.5
openvino_cores = 4
keep_aspect = False

# All common fixtures are below
TEST_NAME = "NEX-T10449"
def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")

  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

@pytest.fixture
def mock_class():
  """! Creates a dummy class to mock a behavior """

  return type("MockClass", (), {})

@pytest.fixture(scope="module")
def frame():
  """! Captures a frame from video. First few frames don't have any objects, that's why
  the n-th frame was taken for testing. """

  nth_frame = 100
  video = videosource.VideoSource(VIDEO_PATH, None, None)
  frame = None
  for _ in range(nth_frame):
    frame = video.capture()

  return frame

@pytest.fixture(scope="module")
def input_data(frame):
  """! Creates IAData object for this module.

  @param    frame   A video frame
  """

  frame_id = uuid.uuid4()
  input_data = detector.IAData([frame], frame_id)

  return input_data

# All the fixtures below are for Detector class

@pytest.fixture
def detector_object():
  """! Creates a Detector object for this module """

  detector_obj = detector.Detector()
  detector_obj.setParameters(model, device, plugin, threshold, openvino_cores)

  return detector_obj

@pytest.fixture
def preprocessed_data(detector_object, input_data):
  """! Preprocesses and creates a list of IAData objects from input_data

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  """

  return detector_object.preprocess(input_data)

@pytest.fixture
def postprocessed_data(detector_object, input_data, preprocessed_data):
  """! Postprocesses the detected objects

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  """

  detector_object.tasksRemainCount[input_data.id] = len(preprocessed_data)
  detector_object.startInfer(preprocessed_data[0], input_data.id, debugFlag=False)
  detector_object.checkDone()
  results = detector_object.getDone()

  postprocessed = None
  if results and results[0]:
    postprocessed = detector_object.postprocess(results[0])

  return postprocessed

@pytest.fixture
def start_inference(detector_object, input_data, preprocessed_data):
  """! Returns true if inference is started

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  """

  detector_object.tasksRemainCount[input_data.id] = len(preprocessed_data)
  is_started = detector_object.startInfer(preprocessed_data[0],
                                          input_data.id,
                                          debugFlag=False)

  return is_started

# All the fixtures below are for Pose Estimator

@pytest.fixture(autouse=True, scope='session')
def pose_estimator():
  """! Creates a PoseEstimator object for this module """

  poseEstimator = detector_pose.PoseEstimator()
  poseEstimator.setParameters(pose_model, device, plugin, threshold, openvino_cores)

  return poseEstimator

@pytest.fixture(autouse=True, scope='session')
def initialize_poser(pose_estimator):
  """! Initializes poser for this session.

  @param    pose_estimator       PoseEstimator object
  """

  pose_estimator.setParameters(pose_model, device, plugin, threshold, openvino_cores)

  return

@pytest.fixture
def detected_poses(pose_estimator, input_data):
  """! Detects and returns all detected poses.

  @param    pose_estimator       PoseEstimator object
  @param    input_data           IAData object that is created using frame
  """
  preprocessed_input = pose_estimator.preprocess(input_data)
  pose_estimator.tasksRemainCount[ input_data.id] = len(preprocessed_input)
  pose_estimator.startInfer(preprocessed_input[0], input_data.id, debugFlag=False)
  pose_estimator.checkDone()

  return pose_estimator.getDone()

# All the fixtures below are for ReID Detector

@pytest.fixture(autouse=True, scope='session')
def reid_detector():
  """! Creates a REIDDetector object for this module """

  return detector.REIDDetector()

@pytest.fixture(autouse=True, scope='session')
def set_parameters(reid_detector):
  """! Sets inference engine parameters for this session.

  @param    reid_detector       REIDDetector object
  """

  reid_detector.setParameters(reid_model, device, plugin, threshold, openvino_cores)
  return

@pytest.fixture(scope="module")
def reid_preprocessed_data(reid_detector, input_data):
  """! Preprocesses and creates a list of IAData objects from input_data

  @param    reid_detector       REIDDetector object
  @param    input_data          IAData object that is created using frame
  """

  return reid_detector.preprocess(input_data)

@pytest.fixture(scope="module")
def reid_postprocessed_data(reid_detector, input_data, reid_preprocessed_data):
  """! Postprocesses the detected objects

  @param    reid_detector             REIDDetector object
  @param    input_data                IAData object that is created using frame
  @param    reid_preprocessed_data    A list of preprocessed IAData objects
  """

  reid_detector.tasksRemainCount[input_data.id] = len(reid_preprocessed_data)
  reid_detector.startInfer(reid_preprocessed_data[0], input_data.id, debugFlag=False)
  reid_detector.checkDone()
  detected_object = reid_detector.getDone()

  postprocessed_data = None
  if detected_object and detected_object[0]:
    postprocessed_data = reid_detector.postprocess(detected_object[0])

  return postprocessed_data

# All the fixtures below are for Motion Detector

@pytest.fixture(scope='module')
def motion_detector():
  """! Creates a motion Detector object for this module """

  motion_obj = detector_motion.MotionDetector()
  motion_obj.setParameters(motion_model, device, plugin, threshold, openvino_cores)

  return motion_obj

@pytest.fixture(scope='module')
def motion_frames():
  """! Creates a list of frames to be used to detect motion """

  numFrames = 200
  video = videosource.VideoSource(MOTION_VIDEO_PATH, None, None)
  frames = []

  for i in range(numFrames):
    frame = video.capture()
    input_data = detector.IAData([frame], i)
    input_data.cameraID = 'camera1'
    input_data.history = 100
    input_data.threshold = 400
    input_data.bgsAlg = 'mog2'
    frames.append(input_data)

  return frames

# All the fixtures below are for the OMZ OCR Detector

@pytest.fixture(scope='module')
def ocr_words():
  """! Defines the list of words for OCR detection"""
  return ["first", "2023", "f3r2", "second"]

@pytest.fixture(scope='module')
def ocr_positions():
  """! Defines the positions of words for OCR detection"""
  return [(100, 500), (250, 700), (650, 900), (250, 250)]

@pytest.fixture(scope='module')
def ocr_sample_image(ocr_words, ocr_positions):
  """! Creates an image with a sample text for OMZ Text Detection

  @param    ocr_words        List of words to include in image
  @param    ocr_positions    Postitions of words to include in image
  """

  image = np.zeros((1000, 1000, 3), np.uint8)
  image[:] = (255, 255, 255)
  for word, position in zip(ocr_words, ocr_positions):
    cv2.putText(image, word, position, cv2.FONT_HERSHEY_COMPLEX,
                1.5, (0, 0, 0), 2, cv2.LINE_AA)

  frame_id = uuid.uuid4()
  frame = detector.IAData([image], frame_id)

  return frame

@pytest.fixture(scope='module')
def ocr_sample_text(ocr_words):
  """! Creates a sample text images for OMZ Text Recognition

  @param    ocr_words    List of words to be recognized
  """

  images = [np.zeros((42, 112, 3), np.uint8),
            np.zeros((42, 120, 3), np.uint8),
            np.zeros((44, 106, 3), np.uint8),
            np.zeros((41, 180, 3), np.uint8)]
  for word, image in zip(ocr_words, images):
    image[:] = (255, 255, 255)
    cv2.putText(image, word, (0, (image.shape[0] - 5)), cv2.FONT_HERSHEY_COMPLEX,
                1.5, (0, 0, 0), 2, cv2.LINE_AA)

  frame_id = uuid.uuid4()
  frame = detector.IAData(images, frame_id)

  return frame

@pytest.fixture(scope='module')
def ocr_detect():
  """! Creates a OCR Detector object for this module """

  ocr_obj = detector_ocr.TextDetector()
  ocr_obj.setParameters('td0001', device, plugin, threshold, openvino_cores)

  return ocr_obj

@pytest.fixture(scope='module')
def ocr_recognize():
  """! Creates a OCR Recognizer object for this module """

  ocr_obj = detector_ocr.TextRecognition()
  ocr_obj.setParameters('trresnet', device, plugin, threshold, openvino_cores)

  return ocr_obj

# All the fixtures below are for Tesseract Detector

@pytest.fixture(scope='module')
def tesseract_detector():
  """! Creates a Tesseract Detector object for this module """

  tesseract_obj = detector_tesseract.TesseractDetector()
  tesseract_obj.setParameters(tesseract_model, device, plugin, threshold, openvino_cores)

  return tesseract_obj

@pytest.fixture(scope='module')
def text_frame():
  """! Creates an image with a sample text for OCR (Tesseract Detector) """

  image = Image.new('RGB', (1000, 500), (255, 255, 255))
  draw = ImageDraw.Draw(image)
  draw.text((100, 100), 'this \n is \n a \n sample \n text', spacing=100, fill=(0, 0, 0))
  opencv_image = np.array(image)

  frame_id = uuid.uuid4()
  frame = detector.IAData([opencv_image], frame_id)

  return frame

# All the fixtures below are for Apriltag Detector

@pytest.fixture(scope='module')
def atag_detector():
  """! Creates a Apriltag Detector object for this module """

  apriltag = detector_atag.ATagDetector()
  apriltag.setParameters(atag_model, device, plugin, threshold, openvino_cores)

  return apriltag

@pytest.fixture(scope="module")
def atag_frame(atag_detector):
  """! Captures a frame from video. First few frames don't have any tags, that's why
  the n-th frame was taken for testing. """

  video = videosource.VideoSource(ATAG_VIDEO_PATH, None, None)
  image = video.capture()
  frame_id = uuid.uuid4()
  frame = detector.IAData([image], frame_id)

  while image is not None:

    apriltags = atag_detector.detect(frame)

    if apriltags and len(apriltags.data[0]) > 0:
      return frame

    image = video.capture()
    frame = detector.IAData([image], frame_id)

  return frame

@pytest.fixture
def mock_result(mock_class):
  """! Returns a list of mock classes that contain dummy results. """

  mock_class.corners = np.asarray([[87, 230], [39, 237], [23, 203], [73, 197]])
  mock_class.tag_id = 1
  mock_class.tag_family = 'tag36h11'.encode("UTF-8")
  mock_class.homography = np.asarray([[0, 0, 1], [0, 0, 7], [0, 0, 0]])
  mock_class.center = np.asarray([56, 217])
  mock_class.hamming = 1
  mock_class.decision_margin = 73

  return [mock_class]

@pytest.fixture(scope="module")
def atag_object():
  """! Creates a ATagObject instance for this module """

  current_time = get_epoch_time()
  info = {
    'id': 1,
    'tag_id': 1,
    'category': "apriltag",
    'tag_family': 'tag36h11'.encode("UTF-8"),
    "bounding_box": {"x": 555, "y": 134, "width": 81, "height": 279},
  }

  camera_info = {
    "camera points": [[137, 328], [425, 162], [596, 208], [578, 443]],
    "map points": [[9, 105, 0], [399, 106, 0], [400, 305, 0], [109, 397, 0]],
    "intrinsics": {'fov': 70},
    "width": 640,
    "height": 480
  }

  # Create a mock ATagObject
  mock_atag_object = MagicMock()
  mock_atag_object.gid = None
  mock_atag_object.oid = 1
  mock_atag_object.sceneLoc.log = "(39.308, 894.481, 0.500)"
  mock_atag_object.location = [MagicMock(), MagicMock()]
  mock_atag_object.location[1].point.log = "(39.308, 894.481, 0.500)"
  mock_atag_object.vectors = ["Vector: (-142.369, 446.052, -268.732) (39.308, 894.481, 0.500) 1743713153.5581214"]

  mock_atag_object.__repr__ = lambda: (
    "ATagObject: None/1 (39.308, 894.481, 0.500) None vectors: "
    "[Vector: (-142.369, 446.052, -268.732) (39.308, 894.481, 0.500) 1743713153.5581214]"
  )
  return mock_atag_object

# All the fixtures below are for Geti Detector

@pytest.fixture(scope='module')
def geti_detector():
  """! Creates a GetiDetector object for this module """

  geti_obj = detector_geti.GetiDetector()

  geti_obj.setParameters(geti_model, device, plugin, threshold, openvino_cores)

  return geti_obj

# OVMS Fixtures

@pytest.fixture
def ovms_detector():
  """! Creates a OVMS Detector object for this module """

  detector_obj = detector.Detector(distributed=detector.Distributed.OVMS)
  detector_obj.setParameters(ovms_retail_model, device, plugin, threshold, openvino_cores)

  return detector_obj

@pytest.fixture
def ovms_hpe():
  """! Creates a OVMS HPE object for this module """

  detector_obj = detector_pose.PoseEstimator(distributed=detector.Distributed.OVMS)
  detector_obj.setParameters(ovms_hpe_model, device, plugin, threshold, openvino_cores)

  return detector_obj

@pytest.fixture
def ovms_geti():
  """! Creates a OVMS GetiDetector object for this module """

  ovms_geti_obj = detector_geti.GetiDetector(distributed=detector_geti.Distributed.OVMS)
  ovms_geti_obj.setParameters(ovms_retail_model, device, plugin, threshold, openvino_cores)

  return ovms_geti_obj
