#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import cv2
import numpy as np

def test_postprocess(reid_postprocessed_data):
  """! Verifies the output of 'detector.REIDDetector.postprocess()' method.

  @param    reid_postprocessed_data  A numpy array that contains postprocessed detected object
  """

  assert reid_postprocessed_data is not None
  return

def test_serializeInput(reid_detector, reid_preprocessed_data):
  """! Verifies the output of 'detector.REIDDetector.serializeInput()' method.

  @param    reid_detector             REIDDetector object
  @param    reid_preprocessed_data    A list of preprocessed IAData objects
  """

  row = reid_preprocessed_data[0].data[0].transpose(1, 2, 0)
  encoded = cv2.imencode(".jpg", row)[1]

  expected_output = base64.b64encode(encoded).decode("ASCII")
  original_output = reid_detector.serializeInput(reid_preprocessed_data[0].data)

  assert original_output[0] == expected_output

  return

def test_deserializeInput(reid_detector, reid_preprocessed_data):
  """! Verifies the output of 'detector.REIDDetector.serializeInput()' method.

  @param    reid_detector             REIDDetector object
  @param    reid_preprocessed_data    A list of preprocessed IAData objects
  """

  serialized = reid_detector.serializeInput(reid_preprocessed_data[0].data)
  deserialized = reid_detector.deserializeInput(serialized)

  assert deserialized and type(deserialized[0]) == np.ndarray

  return

def test_serializeOutput(reid_detector, reid_postprocessed_data):
  """! Verifies the output of 'detector.REIDDetector.serializeOutput()' method.

  @param    reid_detector             REIDDetector object
  @param    reid_postprocessed_data   A numpy array that contains postprocessed detected object
  """

  serialized_output = reid_detector.serializeOutput(reid_postprocessed_data)
  assert serialized_output is not None

  return

def test_deserializeOutput(reid_detector, reid_postprocessed_data):
  """! Verifies the output of 'detector.REIDDetector.deserializeOutput()' method.

  @param    reid_detector             REIDDetector object
  @param    reid_postprocessed_data   A numpy array that contains postprocessed detected object
  """

  serialized_output = reid_detector.serializeOutput(reid_postprocessed_data)
  deserialized_output = reid_detector.deserializeOutput(serialized_output)

  assert np.array_equal(deserialized_output, reid_postprocessed_data)

  return
