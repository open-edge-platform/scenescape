#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from percebro import detector_geti
from tests.sscape_tests.detector.conftest import geti_model, device, plugin, threshold, openvino_cores, keep_aspect
from tests.sscape_tests.detector.config import dummy_ovms_result

@pytest.mark.parametrize("input", [("input_data"), (None)])
def test_preprocess(geti_detector, input, request):
  """! Verifies the output of 'percebro.detector_geti.GetiDetector.preprocess()' method.

  @param    geti_detector   GetiDetector object
  @param    input             IAData object that contains an image with text
  @param    request           Pytest variable that provides information on the
                              executing test function
  """

  if isinstance(input, str):
    input = request.getfixturevalue(input)

  if input:
    mock_preprocess_return(geti_detector, input)
    preprocessed_data = geti_detector.preprocess(input)
    assert preprocessed_data[0]
    assert type(preprocessed_data[0].data) == np.ndarray

  else:
    preprocessed_data = geti_detector.preprocess(input)
    assert len(preprocessed_data) == 0

  return

def mock_preprocess_return(geti_detector, input_data):
  """ Mock OpenVINO 'Model.preprocess()' return value. Need to mock it because the mock
  pretrained model that was used to test this module returned preprocessed data where
  the image was stored under 'data' key while the GetiDetector.preprocess() was
  expecting data to be stored under 'image' key.

  @param    geti_detector   GetiDetector object
  @param    input_data        IAData object that contains an image with text
  """

  patched_image, patched_meta = geti_detector.detector.preprocess(input_data.data[0])

  if 'data' in patched_image:
    patched_image['image'] = patched_image['data']

  geti_detector.detector.preprocess = MagicMock(return_value=(patched_image, patched_meta))
  return

def test_ovms_geti_preprocess(ovms_geti, input_data):
  """! Verifies the output of 'percebro.detector_geti.GetiDetector.preprocess()'
  method using OVMS.

  @param    ovms_geti         OVMS GetiDetector object
  @param    input_data        IAData object that contains an image
  """

  preprocessed_data = ovms_geti.preprocess(input_data)

  assert preprocessed_data[0]
  assert type(preprocessed_data[0].data) == np.ndarray

  return

@pytest.mark.parametrize("swap_x, swap_y",
                        [(True, True),
                        (True, False),
                        (False, True),
                        (False, False)])

def test_postprocess(geti_detector, input_data, swap_x, swap_y):
  """! Postprocesses the detected objects


  @param    geti_detector   GetiDetector object
  @param    input_data        IAData object that contains an image with text
  @param    swap_x            Boolean value to determine whether swap needed
                              between x_min and x_max
  @param    swap_y            Boolean value to determine whether swap needed
                              between y_min and y_max
  """

  mock_preprocess_return(geti_detector, input_data)
  preprocessed_data = geti_detector.preprocess(input_data)

  geti_detector.tasksRemainCount[input_data.id] = len(preprocessed_data)
  geti_detector.startInfer(preprocessed_data[0], input_data.id, debugFlag=False)
  geti_detector.checkDone()

  outputs = geti_detector.getDone()

  postprocessed_data = None
  if outputs and outputs[0]:
    postprocessed_data = geti_detector.postprocess(outputs[0])

  assert postprocessed_data
  assert postprocessed_data[0]['id']
  assert postprocessed_data[0]['category']
  assert postprocessed_data[0]['confidence']
  assert postprocessed_data[0]['bounding_box']

  return

def test_ovms_postprocess(ovms_geti):
  """! Postprocesses dummy raw result using OVMS

  @param    ovms_geti               OVMS GetiDetector object
  """
  postprocessed_data = ovms_geti.postprocess(dummy_ovms_result)

  assert postprocessed_data
  assert postprocessed_data[0]['id']
  assert postprocessed_data[0]['category']
  assert postprocessed_data[0]['confidence']
  assert postprocessed_data[0]['bounding_box']

  return

@pytest.mark.parametrize("model, is_parameters",
                        [(geti_model, True),
                        (geti_model, False)])

def test_setParameters(model, is_parameters):
  """! Verifies the output of 'percebro.detector_geti.GetiDetector.setParameters()' method.

  @param    model           Detection model to pass on setParameters()
  @param    is_parameters   Boolean value to determine whether parameters are None
  """

  geti_detector = detector_geti.GetiDetector()

  if not is_parameters:
    detector_geti.json.load = MagicMock(return_value=None)

  geti_detector.setParameters(model, device, plugin, threshold, openvino_cores)

  assert geti_detector.threshold
  if is_parameters:
    assert geti_detector.device == device
    assert geti_detector.ov_cores == openvino_cores
    assert geti_detector.detector
    assert geti_detector.input_blob
    assert geti_detector.output_blob

  return
