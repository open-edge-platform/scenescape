#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64

from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from percebro import detector
from tests.sscape_tests.detector.conftest import model, plugin, threshold, openvino_cores, keep_aspect
from tests.sscape_tests.detector.config import detector_model, ovms_retail_model

detectorClass = 'percebro.detector.Detector'

def test_addModels(detector_object):
  """! Verifies the output of 'percebro.detector.Detector.addModels()' method.

  @param    detector_object     Detector object
  """

  new_models = {
    'test001': {
      'directory': "test001-directory"
    },
    'pv0078': {
      'directory': "updated_0078",
      'categories': ['background', 'person', 'vehicle', 'bicycle', 'test']
    }
  }
  detector_object.addModels(new_models)

  assert detector._default_model_config['test001']
  assert detector._default_model_config['test001']['directory'] == "test001-directory"
  assert detector._default_model_config['pv0078']['directory'] == "updated_0078"
  assert detector._default_model_config['pv0078']['categories'][4] == "test"

  return

def test_run(detector_object, mock_class):
  """! Verifies the output of 'percebro.detector.Detector.run()' method.

  @param    detector_object     Detector object
  @param    mock_class          Dummy class to mock a behavior
  """

  max_value = 255
  row = 3
  column = 10
  original_data = np.random.randint(max_value, size=(row, column))

  detector_object.task = mock_class
  detector_object.task.status = "SUCCESS"
  detector_object.task.result = [detector_object.serializeOutput(original_data[0]),
                                detector_object.serializeOutput(original_data[1]),
                                detector_object.serializeOutput(original_data[2])]
  detector_object.run()

  assert np.array_equal(detector_object.results, original_data[2])

  return

def test_callback(detector_object):
  """! Verifies the output of 'percebro.detector.Detector.callback()' method for multiple threads.

  @param    detector_object     Detector object
  """

  total_tasks = 10
  tasks = [i for i in range(total_tasks)]
  expected_result = [i for i in range(total_tasks)]

  with ThreadPoolExecutor(max_workers = 3) as executor:
    executor.map(lambda parameters: detector_object.callback(parameters), tasks)

  assert detector_object.tasksDone == expected_result

  detector_object.tasksDone = []
  return

@pytest.mark.parametrize("detector_instance, asynchronous",
                          [("detector_object", True),
                          ("detector_object", False),
                          ("ovms_detector", False)])
def test_startInfer(detector_instance, input_data, preprocessed_data, asynchronous, request):
  """! Verifies the output of 'percebro.detector.Detector.startInfer()' method

  @param    detector_instance   Detector object
  @param    input_data          IAData object that is created using frame
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  @param    asynchronous        Boolean value to determine whether async mode is on
  """

  detector_instance = request.getfixturevalue(detector_instance)
  detector_instance.asynchronous = asynchronous
  detector_instance.tasksRemainCount[input_data.id] = len(preprocessed_data)
  is_started = detector_instance.startInfer(preprocessed_data[0], input_data.id, debugFlag=False)

  assert is_started
  return

def test_startInfer_returns_false(detector_object, input_data, preprocessed_data):
  """! Verifies 'percebro.detector.Detector.startInfer()' method returns False when all
  available inference engines are busy.

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  """

  current_task = MagicMock()
  current_task.task = 0
  detector_object.tasksCur = [current_task]
  detector_object.tasksRemainCount[input_data.id] = len(preprocessed_data)
  is_started = detector_object.startInfer(preprocessed_data[0], input_data.id, debugFlag=False)

  assert not is_started
  return

@pytest.mark.parametrize("default_tasks, expected_output", [(True, True), (False, False)])
def test_checkDone(detector_object, start_inference, default_tasks, expected_output):
  """! Verifies the output of 'percebro.detector.Detector.checkDone()' method

  @param    detector_object     Detector object
  @param    start_inference     A boolean that tells whether inference has started or not
  @param    default_tasks     List of completed tasks
  @param    expected_output     Expected output
  """

  if not default_tasks:
    detector_object.tasksDone = []

  is_done = detector_object.checkDone()

  assert is_done == expected_output
  return

def test_checkDone_incomplete_tasks(detector_object, start_inference):
  """! Checks the incompleted tasks in 'percebro.detector.Detector.checkDone()' method

  @param    detector_object     Detector object
  @param    start_inference     A boolean that tells whether inference has started or not
  """

  task = detector_object.tasksCur[0]
  detector_object.tasksIncomplete[task.id] = [task]
  detector_object.tasksRemainCount[task.id] = 2
  is_done = detector_object.checkDone()

  assert is_done
  return

def test_getDone(detector_object, start_inference):
  """! Verifies the output of 'percebro.detector.Detector.getDone()' method

  @param    detector_object     Detector object
  @param    start_inference     A boolean that tells whether inference has started or not
  """

  detector_object.checkDone()
  detected_object = detector_object.getDone()

  assert detected_object
  assert type(detected_object[0].data) == np.ndarray
  return

@pytest.mark.parametrize("completed_tasks, expected_output", [([], None), ([None, None], None)])
def test_getDone_no_tasks(detector_object, start_inference, completed_tasks, expected_output):
  """! Verifies the output of 'percebro.detector.Detector.getDone()' method with no completed tasks

  @param    detector_object     Detector object
  @param    start_inference     A boolean that tells whether inference has started or not
  @param    completed_tasks     Dummy list of completed tasks
  @param    expected_output     Expected output
  """

  detector_object.checkDone()
  detector_object.tasksComplete = completed_tasks
  detected_object = detector_object.getDone()

  assert detected_object == expected_output
  return

@pytest.mark.parametrize("detector_instance", [("detector_object"),("ovms_detector")])
def test_detect(detector_instance, input_data, request):
  """! Verifies the output of 'percebro.detector.Detector.detect()' method

  @param    detector_instance   Detector object
  @param    input_data          IAData object that is created using frame
  """

  detector_instance = request.getfixturevalue(detector_instance)
  result = detector_instance.detect(input_data)

  assert result
  assert result.data[0][0]['id'] == 1
  assert result.data[0][0]['category'] == 'person'
  assert result.data[0][0]['confidence']
  assert result.data[0][0]['bounding_box']
  assert result.data[0][0]['center_of_mass']

  return

@pytest.mark.parametrize("processed_input, expected_output",
                        [(None, None),
                        ([], [])])
def test_detect_none_preprocess(detector_object, input_data, processed_input, expected_output):
  """! Verifies the none result from 'percebro.detector.Detector.detect()' method
  when preprocess data is None or empty.

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    processed_input     Dummy preprocessed data
  @param    expected_output     Expected output
  """

  with patch(".".join((detectorClass, 'preprocess')), return_value=processed_input):
    result = detector_object.detect(input_data)

  assert result == expected_output or result.data == expected_output
  return

def test_detect_inference_not_started(detector_object, input_data):
  """! Verifies the none result from 'percebro.detector.Detector.detect()' method
  where inference engine has not started.

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  """

  with patch(".".join((detectorClass, 'startInfer')), side_effect=[False, True]):
    result = detector_object.detect(input_data)

  assert result == None
  return

def test_waitingIDs(detector_object, mock_class):
  """! Verifies the output of 'percebro.detector.Detector.waitingIDs()' property for multiple threads.

  @param    detector_object     Detector object
  @param    mock_class          Dummy class to mock a behavior
  """

  mock_class.id = 1

  current_tasks = [[mock_class], [mock_class] * 2, [mock_class] * 3]
  completed_tasks = [[[2, 5, 3], [8, 4, 5]], [[2, 7, 8]], [[1, 6, 0], [1, 4, 9], [2, 2, 4]]]
  expected_output = [{1, 3, 5}, {1, 8}, {1, 0, 9, 4}]

  results = []
  for current_task, completed_task in zip(current_tasks, completed_tasks):
    with ThreadPoolExecutor(max_workers = 3) as executor:
      detector_object.tasksCur = current_task
      detector_object.tasksComplete = completed_task

      executor.map(detector_object.waitingIDs)
      results.append(detector_object.waitingIDs)

  for result, output in zip(results, expected_output):
    assert result == output

  return

def test_waitingCount(detector_object):
  """! Verifies the output of 'percebro.detector.Detector.waitingCount()' property for multiple threads.

  @param    detector_object     Detector object
  """

  current_tasks = [[1, 2], [1, 2, 3], [1, 5, 3, 9]]
  completed_tasks = [[[2, 5, 3]], [[2, 5, 3], [8, 4, 5]], [[2, 5, 3], [8, 4, 5], [8, 4, 3]]]
  expected_output = [3, 5, 7]

  results = []

  for current_task, completed_task in zip(current_tasks, completed_tasks):
    with ThreadPoolExecutor(max_workers = 3) as executor:
      detector_object.tasksCur = current_task
      detector_object.tasksComplete = completed_task

      executor.map(detector_object.waitingCount)
      results.append(detector_object.waitingCount)

  for result, output in zip(results, expected_output):
    assert result == output

  return

@pytest.mark.parametrize("current_tasks, completed_tasks, expected_output",
                                    [([1, 2], [], True),
                                    ([1, 2], [8, 1, 2, 6], True),
                                    ([], [], False)])
def test_waiting(detector_object, current_tasks, completed_tasks, expected_output):
  """! Verifies the output of 'percebro.detector.Detector.waiting()' property.

  @param    detector_object     Detector object
  @param    current_tasks       List of current tasks
  @param    completed_tasks     List of completed tasks
  @param    expected_output     Expected output
  """

  detector_object.tasksCur = current_tasks
  detector_object.tasksComplete = completed_tasks

  assert detector_object.waiting == expected_output
  return

def test_configureDetector(detector_object):
  """! Verifies the output of 'percebro.detector.Detector.configureDetector()' method.

  @param    detector_object     Detector object
  """

  detector_object.configureDetector()

  assert detector_object.exec_network
  assert detector_object.core
  assert detector_object.async_queue
  assert len(detector_object.async_queue) > 0
  assert detector_object.inputs_info
  assert detector_object.input_blob
  assert detector_object.output_blob
  assert detector_object.h
  assert detector_object.w

  return

def test_ovms_configureDetector(ovms_detector):
  """! Verifies the output of 'percebro.detector.Detector.configureDetector()' method for ovms.

  @param    ovms_detector     OVMS detector object
  """

  ovms_detector.configureDetector()

  assert ovms_detector.client
  assert ovms_detector.model_metadata
  assert ovms_detector.input_blob

  return

@pytest.mark.parametrize("detector_instance, model_config, device",
                        [("detector_object", None, "CPU"),
                        ("detector_object", model, "CPU"),
                        ("detector_object", model, "GPU"),
                        ("detector_object", detector_model, "CPU"),
                        ("ovms_detector", ovms_retail_model, "CPU")])
def test_setParameters(detector_instance, model_config, device, request):
  """! Verifies the output of 'percebro.detector.Detector.setParameters()' method.

  @param    detector_object     Detector object
  @param    model_config        String or dictionary to set inference engine parameter
  @param    device              Device type to set inference engine parameter
  """

  detector_instance = request.getfixturevalue(detector_instance)

  with patch(".".join((detectorClass, 'configureDetector')), return_value=None):
    with patch(".".join((detectorClass, 'loadLabelSchema')), return_value=None):
      detector_instance.setParameters(model_config, device, plugin, threshold, openvino_cores)

  assert detector_instance.device == device
  assert detector_instance.model
  assert detector_instance.plugin == None
  assert detector_instance.threshold == 0.5
  assert detector_instance.ov_cores == 4

  return

@pytest.mark.parametrize("input",
                        [("input_data"),
                        (detector.IAData([np.zeros((10, 0))], 1))])
def test_preprocess(detector_object, input, request):
  """! Verifies the output of 'percebro.detector.Detector.preprocess()' method.

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    request             Pytest variable that provides information on the
                                executing test function
  """

  if isinstance(input, str):
    input = request.getfixturevalue(input)

  preprocessed_input = detector_object.preprocess(input)

  if input.data[0].shape[0] and input.data[0].shape[1]:
    assert preprocessed_input[0]
    assert type(preprocessed_input[0].data) == np.ndarray
  else:
    assert len(preprocessed_input) == 0

  return

@pytest.mark.parametrize("default_threshold, default_categories",
                        [(True, True), (False, True), (True, False)])
def test_postprocess(detector_object,
                    input_data,
                    preprocessed_data,
                    default_threshold,
                    default_categories):
  """! Verifies the output of 'percebro.detector.Detector.postprocess()' method.

  @param    detector_object     Detector object
  @param    input_data          IAData object that is created using frame
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  @param    default_threshold   Boolean value to determine whether to mock
                                threshold value or not
  @param    default_categories  Boolean value to determine whether to mock
                                categories value or not
  """

  detector_object.tasksRemainCount[input_data.id] = len(preprocessed_data)
  detector_object.startInfer(preprocessed_data[0], input_data.id, debugFlag=False)
  detector_object.checkDone()
  results = detector_object.getDone()

  if not default_threshold:
    detector_object.threshold = 1

  if not default_categories:
    detector_object.categories = []

  postprocessed_data = None
  if results and results[0]:
    postprocessed_data = detector_object.postprocess(results[0])

  if default_threshold:
    assert postprocessed_data
    assert postprocessed_data[0]['id'] == 1
    assert postprocessed_data[0]['category']
    assert postprocessed_data[0]['confidence']
    assert postprocessed_data[0]['bounding_box']
    assert postprocessed_data[0]['center_of_mass']

  else:
    assert len(postprocessed_data) == 0

  return

def test_serializeInput(detector_object, preprocessed_data):
  """! Verifies the output of 'percebro.detector.Detector.serializeInput()' method.

  @param    detector_object     Detector object
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  """

  reshaped = preprocessed_data[0].data.reshape((detector_object.h, detector_object.w, -1))
  encoded = cv2.imencode(".jpg", reshaped)[1]
  expected_output = base64.b64encode(encoded).decode("ASCII")

  original_output = detector_object.serializeInput(preprocessed_data[0].data)

  assert original_output == expected_output
  return

def test_deserializeInput(detector_object, preprocessed_data):
  """! Verifies the output of 'percebro.detector.Detector.deserializeInput()' method.

  @param    detector_object     Detector object
  @param    preprocessed_data   A list of preprocessed data as IAData objects
  """

  serialized = detector_object.serializeInput(preprocessed_data[0].data)
  deserialized = detector_object.deserializeInput(serialized)

  assert deserialized is not None
  assert type(deserialized) == np.ndarray

  return

def test_serializeOutput(detector_object, postprocessed_data):
  """! Verifies the output of 'percebro.detector.Detector.serializeOutput()' method.

  @param    detector_object       Detector object
  @param    postprocessed_data    A numpy array that contains postprocessed detected object
  """

  serialized_output = detector_object.serializeOutput(postprocessed_data)
  assert serialized_output is not None

  return

def test_deserializeOutput(detector_object, postprocessed_data):
  """! Verifies the output of 'percebro.detector.Detector.deserializeOutput()' method.

  @param    detector_object       Detector object
  @param    postprocessed_data    A numpy array that contains postprocessed detected object
  """

  serialized_output = detector_object.serializeOutput(postprocessed_data)
  deserialized_output = detector_object.deserializeOutput(serialized_output)

  assert np.array_equal(deserialized_output, postprocessed_data)

  return
