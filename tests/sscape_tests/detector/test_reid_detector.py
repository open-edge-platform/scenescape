#!/usr/bin/env python3

# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
