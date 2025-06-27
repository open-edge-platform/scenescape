#!/usr/bin/python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import argparse
import tests.external_models.external_models_test_common as common
import tests.common_test_utils as tests_common
import json
import numpy as np

TEST_NAME = "NEX-T10514_GETI_LABEL_ORDER"

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-c", "--config", type=str,
                      help="Config file matching input files vs expected labels.", required=True)
  return parser

def compare_expected_to_detections_single_frame( expected_detections, frame_detections ):
  frame_matching_failed = False
  num_objects = 0
  frame_matched_detections = 0
  test_tolerance = 2
  for expected in expected_detections:
    if expected['frame'] == frame_detections['frame'] :
      if not len(expected['objects']) == len(frame_detections['objects']):
        print( "Mismatch in number of expected {} vs detected {} objects".format(
          len(expected['objects']), len(frame_detections['objects']) ) )
        frame_matching_failed = True
        break

      num_objects = len(expected['objects'])
      for exp_obj in expected['objects']:
        for det_obj in frame_detections['objects']:

          if np.isclose( det_obj['bounding_box_px']['x'], exp_obj['bounding_box_px']['x'], atol=test_tolerance )\
              and np.isclose( det_obj['bounding_box_px']['y'], exp_obj['bounding_box_px']['y'], atol=test_tolerance )\
              and np.isclose( det_obj['bounding_box_px']['width'], exp_obj['bounding_box_px']['width'], atol=test_tolerance )\
              and np.isclose( det_obj['bounding_box_px']['height'], exp_obj['bounding_box_px']['height'], atol=test_tolerance ) :
            if exp_obj['category'] == det_obj['category']:
              frame_matched_detections += 1

              print( "Matching Detection vs Expected for frame {} object {}".format( frame_detections['frame'], det_obj['category'] ) )
            else:
              print( "Mismatch in category! For frame {} expected {}, got {}".format( frame_detections['frame'], exp_obj['category'], det_obj['category'] ) )
              frame_matching_failed = True
              break

      if num_objects != frame_matched_detections:
        print( "Mismatch in number of objects detected (detection positions dont match!)" )
        frame_matching_failed = True
        break
      else:
        print( "Frame {} matches ok".format( expected['frame'] ) )

  if not frame_matching_failed and frame_matched_detections == num_objects:
    return True
  return False

def compare_output_with_detections( test_config ):
  comparison_result = False
  with open(test_config['output'],'r') as output_fd:
    comparison_result = True
    done = False
    while not done:
      detection_line = output_fd.readline()
      if not detection_line:
        done = True
      else:
        detections = json.loads(detection_line)

        if not compare_expected_to_detections_single_frame( test_config['expected_detections'], detections ):
          print( "Test failed at frame {}".format( detections['frame'] ) )
          comparison_result = False

  return comparison_result

def test_detection():
  args = build_argparser().parse_args()
  print( "{}: Starting".format(TEST_NAME))

  test_config = None
  with open(args.config,'r') as config_fd:
    test_config = json.load(config_fd)

  testResult = 1
  zip_path = test_config['model_zip']
  env_model = os.path.splitext( os.path.basename(zip_path) )[0]

  if os.path.exists(zip_path):
    common.clean_model(env_model)
    cfg_file = common.prepare_model(zip_path, env_model)
    os.environ['TARGET_FPS'] = "{}".format(1)
    os.environ['INPUTS'] = test_config['input']
    os.environ['MODELS'] = env_model
    os.environ['MODEL_CONFIG'] = cfg_file
    os.environ['VIDEO_FRAMES'] = "255"

    testCommand = ['tests/perf_tests/tc_inference_performance.sh']
    testResult = common.run_and_check_output(testCommand, env_model)

    # Check detections vs expected
    if not compare_output_with_detections( test_config ):
      print( "Normal config failed (Label order vs detections mismatch) !" )
      testResult = 1
    else:
      print( "Normal-order config : Expected Label vs detected label Ok!" )
      reversed_config_name = 'models/{}/model/reversed_config.json'.format(env_model)
      target_config_name = 'models/{}/model/config.json'.format(env_model)

    if testResult == 0 and os.path.exists(reversed_config_name):
      # Update the config.json file to point to the reversed one
      update_config_cmd = [ 'mv', reversed_config_name, target_config_name ]
      common.run_command( update_config_cmd )

      testCommand = ['tests/perf_tests/tc_inference_performance.sh']
      testResult = common.run_and_check_output(testCommand, env_model)

      if not compare_output_with_detections( test_config ):
        print( "Reversed config failed (Label order vs detections mismatch)!" )
        testResult = 1
      else:
        print( "Reversed-order config : Expected Label vs detected label Ok!" )

    common.clean_model(env_model)
  else:
    print("No model was found/run")

  tests_common.record_test_result(TEST_NAME, testResult)

  assert testResult == 0
  return testResult

if __name__ == '__main__':
  exit(test_detection() or 0)
