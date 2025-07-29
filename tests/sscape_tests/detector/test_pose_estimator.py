#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.sscape_tests.detector.conftest import pose_model, device
from tests.sscape_tests.detector.config import no_keypoints_poses, ovms_hpe_model

detectorClass = 'percebro.detector.Detector'

def test_detect(pose_estimator, input_data):
  """! Verifies the output of 'detector_pose.PoseEstimator.detect()' method.

  @param    pose_estimator       PoseEstimator object
  @param    input_data           IAData object that is created using frame
  """

  result = pose_estimator.detect(input_data)
  verify_outputs(result.data[0][0])

  return

def test_detect_none_input(pose_estimator, detected_poses):
  """! Verifies the output of 'detector_pose.PoseEstimator.detect()' method
  when None is passed through the detect method.

  @param    pose_estimator       PoseEstimator object
  @param    detected_poses       All detected poses
  """

  pose_estimator.tasksComplete.append(detected_poses)

  outputs = pose_estimator.detect(None)
  verify_outputs(outputs.data[0][0])

  return

@pytest.mark.parametrize("hpe_instance, model_config",
                        [("pose_estimator", pose_model),
                        ("ovms_hpe", ovms_hpe_model)])
def test_setParameters(hpe_instance, model_config, request):
  """! Verifies the output of 'percebro.detector_pose.PoseEstimator.setParameters()' method.

  @param    hpe_instance        HPE object
  @param    model_config        String or dictionary to set inference engine parameter
  @param    device              Device type to set inference engine parameter
  """

  hpe_instance = request.getfixturevalue(hpe_instance)

  assert hpe_instance.device == device
  assert hpe_instance.model
  assert hpe_instance.plugin == None
  assert hpe_instance.threshold == 0.5
  assert hpe_instance.ov_cores == 4

  return

@pytest.mark.parametrize("poses, has_keypoints",
                        [("detected_poses", True),
                        (no_keypoints_poses, False)])
def test_postprocess(pose_estimator, poses, has_keypoints, request):
  """! Verifies the output of 'detector_pose.PoseEstimator.postprocess()' method.

  @param    pose_estimator       PoseEstimator object
  @param    poses                All detected poses
  @param    has_keypoints        Boolean to determine whether detected
                                 poses have keypoints
  @param    request              Pytest variable that provides information on the
                                 executing test function
  """

  if isinstance(poses, str):
    poses = request.getfixturevalue(poses)

  people = pose_estimator.postprocess(poses[0])

  if has_keypoints:
    verify_outputs(people[0])
  else:
    assert len(people) == 0

  return

def verify_outputs(output):
  """! Verifies the output of multiple testcases.

  @param    output    Original output
  """

  assert output['category'] == 'person'
  assert output['bounding_box']
  assert output['center_of_mass']
  assert output['pose']

  return
