#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
import uuid

from percebro import detector, detector_motion
from tests.sscape_tests.detector.conftest import motion_model, device, plugin, threshold, openvino_cores, keep_aspect

def verify_outputs(results, expected_bboxes):
  """! Compares the original and expected results for multiple testcases.

  @param    results             Original results
  @param    expected_bbox       Expected bounding box
  """
  assert len(results) == len(expected_bboxes)

  for result, expected_bbox in zip(results, expected_bboxes):
    assert result
    assert result['category'] == 'motion'
    assert result['bounding_box'] == expected_bbox

  return

@pytest.mark.parametrize("motion_obj, camera_id, expected_bboxes",
          [("motion_detector", "camera1", [{'x': 837, 'y': 0, 'width': 146, 'height': 169}]),
          (detector_motion.MotionMog2Detector(), "camera1", [{'x': 837, 'y': 0, 'width': 146, 'height': 169}]),
          (detector_motion.MotionKnnDetector(), "camera2", [{'x': 834, 'y': 0, 'width': 151, 'height': 253}]),
          (None, "camera3", [{'x': 837, 'y': 0, 'width': 146, 'height': 169}])])

def test_detect(motion_detector, motion_frames, motion_obj, camera_id, expected_bboxes, request):
  """! Verifies the output of 'detector.MotionDetector.detect()' method.

  @param    motion_detector       MotionDetector object
  @param    motion_frames         list of IAData objects
  @param    motion_obj            Different types of motion detector object passed
                                  using parametrize
  @param    camera_id             Camera ID
  @param    expected_bbox         Expected bounding box
  @param    request               Pytest variable that provides information on the
                                  executing test function
  """

  if not motion_obj:
    motion_detector.bgsAlg = "unknown"
    motion_obj = motion_detector

  elif isinstance(motion_obj, str):
    motion_obj = request.getfixturevalue(motion_obj)

  motion_obj.setParameters(motion_model, device, plugin, threshold, openvino_cores)

  for m in motion_frames:
    m.cameraID = camera_id
    motion = motion_obj.detect(m)

  verify_outputs(motion.data[0], expected_bboxes)

  return

def test_detect_none_input(motion_detector):
  """! Verifies the output of 'detector.MotionDetector.detect()' method
  when None is passed through the detect method.

  @param    motion_detector       MotionDetector object
  """

  frame_id = uuid.uuid4()
  raw_results = [(0, 370, 114, 110)]
  expected_bboxes = [{'x': 0, 'y': 370, 'width': 114, 'height': 110}]

  dummy_result = detector.IAData(raw_results, frame_id)
  motion_detector.tasksComplete.append([dummy_result])

  results = motion_detector.detect(None)
  verify_outputs(results.data[0], expected_bboxes)

  return

def test_preprocess(motion_detector, motion_frames):
  """! Verifies the output of 'detector.MotionDetector.preprocess()' method.

  @param    motion_detector       MotionDetector object
  @param    motion_frames         list of IAData objects
  """

  grayscale = motion_detector.preprocess(motion_frames[0])
  assert grayscale[0].shape == (motion_frames[0].data[0].shape[0], motion_frames[0].data[0].shape[1])

  return

def test_postprocess(motion_detector):
  """! Verifies the output of 'detector.MotionDetector.postprocess()' method.

  @param    motion_detector       MotionDetector object
  """
  frame_id = uuid.uuid4()
  raw_results = [(0, 370, 114, 110)]
  iadata = detector.IAData(raw_results, frame_id)

  results = motion_detector.postprocess(iadata)
  expected_bboxes = [{'x': 0, 'y': 370, 'width': 114, 'height': 110}]

  verify_outputs(results, expected_bboxes)

  return

@pytest.mark.parametrize("model, expected_output",
      [({'threshold': 400, 'history': 100}, {'threshold': 400, 'history': 100}),
      ({'threshold': 400, 'history': None}, {'threshold': 400, 'history': None}),
      ('motion', None),
      (None, None)])

def test_setParameters(model, expected_output):
  """! Verifies the output of 'detector.MotionDetector.setParameters()' method.

  @param    model                 Model name or model dictionary
  @param    expected_output       Expected output
  """

  motion_detector = detector_motion.MotionDetector()

  try:
    motion_detector.setParameters(model, device, plugin, threshold, openvino_cores)

    assert motion_detector.model
    assert motion_detector.model['threshold'] == expected_output['threshold']
    assert motion_detector.model['history'] == expected_output['history']
  except TypeError:
    assert not hasattr(motion_detector, 'model')

  return
