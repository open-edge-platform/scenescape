#!/usr/bin/python3

# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os
import argparse
import tests.external_models.external_models_test_common as common

TEST_ID = "NEX-T10514"
TEST_NAME = "Geti: Scene integration test"

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-z", "--zip", type=str,
                      help="Path to the .zip file of the model.", required=True)
  parser.add_argument("-i", "--inputs", type=str,
                      help="Camera device you are using.", required=True)
  parser.add_argument("-c", "--categories", type=str,
                      help="Comma separated list of categories for the model.", required=True )
  return parser

def test_scene_integration():
  args = build_argparser().parse_args()
  print( "{}: Starting".format(TEST_NAME))

  testResult = 1
  zip_path = args.zip
  env_model = os.path.splitext( os.path.basename(zip_path) )[0]

  if os.path.exists(zip_path):
    common.clean_model(env_model)
    cfg_file = common.prepare_model(zip_path, env_model)

    dbcleanCommand = ['rm', '-rf', 'tests/db', 'tests/media', 'tests/migrations']
    [cmd_res, cmd_out] = common.run_command( dbcleanCommand )

    expectedCategories = args.categories.split(',')
    os.environ['WAITFORCONTAINERS'] = "scene pgserver"
    os.environ['DBROOT'] = "tests"
    os.environ['TEST_INPUT'] = args.inputs
    os.environ['TEST_MODELS'] = env_model
    os.environ['MODEL_CONFIG'] = cfg_file
    # FIXME The test was removed in: https://github.com/intel-innersource/applications.ai.scene-intelligence.opensail/commit/fb6817df2d1dd1a09d39c548a4ef40a199609bfd
    testCommand = ['tests/runtest', 'tests/common-services-test_ext.yml', 'tests/system/smoke/tc_mqtt_running.py']

    testResult = common.run_and_check_output(testCommand, env_model, findText="Detected category", expectedText=expectedCategories)

    common.clean_model(env_model)
  else:
    print("No model was found/run")
    return 1

  if testResult == 0:
    print("{}: PASS".format(TEST_ID))
  else:
    print("{}: FAIL".format(TEST_ID))
  assert testResult == 0
  return testResult

if __name__ == '__main__':
  exit(test_scene_integration() or 0)
