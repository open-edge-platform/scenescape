#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import uuid

from percebro import detector

def verify_outputs(outputs, expected_outputs):
  """! Compares the original and expected output for multiple testcases.

  @param    outputs             Original outputs
  @param    expected_outputs    Expected outputs
  """
  assert len(outputs) == len(expected_outputs)

  for output, expected_output in zip(outputs, expected_outputs):
    print(expected_output)
    assert output
    assert output['category'] == 'apriltag'
    assert output['bounding_box']
    assert output['tag_id'] == expected_output.tag_id
    assert output['tag_family'] == expected_output.tag_family.decode("utf-8")
    assert output['corners'] == expected_output.corners.tolist()
    assert output['homography'] == expected_output.homography.tolist()
    assert output['center'] == expected_output.center.tolist()
    assert output['hamming'] == expected_output.hamming
    assert output['decision_margin'] == expected_output.decision_margin

  return

def test_detect(atag_detector, atag_frame):
  """! Verifies the output of 'atag.ATagDetector.detect()' method.

  @param    atag_detector       ATagDetector object
  @param    atag_frame          IAData object that contains an image with apriltags
  """

  keys = ['bounding_box', 'tag_id', 'tag_family', 'corners', 'homography', 'center', 'hamming', 'decision_margin']
  apriltags = atag_detector.detect(atag_frame)

  assert len(apriltags.data[0]) > 0

  for apriltag in apriltags.data[0]:
    assert apriltag
    assert apriltag['category'] == 'apriltag'

    for key in keys:
      assert key in apriltag

  return

def test_detect_none_input(atag_detector, mock_result):
  """! Verifies the output of 'atag.ATagDetector.detect()' method
  when None is passed through the detect method.

  @param    atag_detector       ATagDetector object
  @param    mock_result         List of mock classes that contain dummy results
  """

  dummy_result = detector.IAData(mock_result, 1)
  atag_detector.tasksComplete.append([dummy_result])

  outputs = atag_detector.detect(None)
  verify_outputs(outputs.data[0], mock_result)

  return

def test_preprocess(atag_detector, atag_frame):
  """! Verifies the output of 'atag.ATagDetector.preprocess()' method.

  @param    atag_detector       ATagDetector object
  @param    atag_frame          IAData object that contains an image with apriltags
  """

  grayscale = atag_detector.preprocess(atag_frame)
  assert grayscale[0].shape == (atag_frame.data[0].shape[0], atag_frame.data[0].shape[1])

  return

def test_postprocess(atag_detector, mock_result):
  """! Verifies the output of 'atag.ATagDetector.postprocess()' method.

  @param    atag_detector       ATagDetector object
  @param    mock_result         List of mock classes that contain dummy results
  """

  frame_id = uuid.uuid4()
  iadata = detector.IAData(mock_result, frame_id)

  outputs = atag_detector.postprocess(iadata)
  verify_outputs(outputs, mock_result)

  return
