#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import uuid
import numpy as np
from unittest.mock import MagicMock, patch

from percebro import detector

def verify_outputs(results, expected_results):
  """! Compares the original and expected results for multiple testcases.

  @param    results             Original results
  @param    expected_results    Expected results
  """

  for result in results:
    assert result
    assert result['category'] == 'text'
    assert result['text'] in expected_results
    assert result['bounding_box']

  return

def test_detect(tesseract_detector, text_frame):
  """! Verifies the output of 'detector.TesseractDetector.detect()' method.

  @param    tesseract_detector       TesseractDetector object
  @param    text_frame               IAData object that contains an image with text
  """

  expected_words = {'this', 'is', 'a', 'sample', 'text'}
  words = tesseract_detector.detect(text_frame)
  verify_outputs(words.data[0], expected_words)

  return

def test_detect_none_input(tesseract_detector):
  """! Verifies the output of 'detector.TesseractDetector.detect()' method
  when None is passed through the detect method.

  @param    tesseract_detector       TesseractDetector object
  """
  frame_id = uuid.uuid4()
  raw_results = [[(0, 5, 10, 5), 'dummy']]
  expected_results = {'dummy'}

  dummy_result = detector.IAData(raw_results, frame_id)
  tesseract_detector.tasksComplete.append([dummy_result])

  outputs = tesseract_detector.detect(None)
  verify_outputs(outputs.data[0], expected_results)

  return

def test_detect_none_bbox_and_text(tesseract_detector):
  """! Verifies the output of 'detector.TesseractDetector.detect()' method
  when Bounding box is none or the text is empty.

  @param    tesseract_detector       TesseractDetector object
  """

  first_word = MagicMock()
  first_word.BoundingBox = MagicMock(return_value=None)

  sec_word = MagicMock()
  sec_word.BoundingBox = MagicMock(return_value=[1, 1, 5, 5])
  sec_word.GetUTF8Text = MagicMock()
  sec_word.GetUTF8Text.strip = MagicMock(return_value = [])

  with patch('percebro.detector_tesseract.iterate_level', return_value=[first_word, sec_word]):
    words = tesseract_detector.detect(detector.IAData([np.zeros((10, 10, 3), dtype=np.uint8)], 1))
    assert len(words.data[0]) == 0

  return

def test_preprocess(tesseract_detector, text_frame):
  """! Verifies the output of 'detector.TesseractDetector.preprocess()' method.

  @param    tesseract_detector       TesseractDetector object
  @param    text_frame               IAData object that contains an image with text
  """

  grayscale = tesseract_detector.preprocess(text_frame)
  assert grayscale[0].shape == (text_frame.data[0].shape[0], text_frame.data[0].shape[1])

  return

def test_postprocess(tesseract_detector):
  """! Verifies the output of 'detector.TesseractDetector.postprocess()' method.

  @param    tesseract_detector       TesseractDetector object
  """

  frame_id = uuid.uuid4()
  raw_results = [[(0, 5, 10, 5), 'dummy']]
  expected_results = {'dummy'}
  iadata = detector.IAData(raw_results, frame_id)

  results = tesseract_detector.postprocess(iadata)
  verify_outputs(results, expected_results)

  return
