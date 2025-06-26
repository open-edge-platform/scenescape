#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import analytics.library.json_helper as json_helper
import analytics.library.metrics as metrics
import tests.common_test_utils as common
from controller.detections_builder import buildDetectionsList
from controller.scene import Scene
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader


def get_detections(tracked_data, scene, objects, jdata):
  """! This function builds the object list for the
  tracked data and returns it

  @param    tracked_data  The empty list of tracked data
  @param    scene         The current scene being processed
  @param    objects       The dict of detection objects
  @param    jdata         Json data which contains detection info
  @return   tracked_data  The filled list of tracked data
  """

  obj_list = []
  for category in objects.keys():
    curr_objects = scene.tracker.currentObjects(category)
    for obj in curr_objects:
      obj_list.append(obj)

  jdata['objects'] = buildDetectionsList(obj_list, None)
  tracked_data.append(jdata)
  return

def track(params):
  """! This function calls the tracking routine and
  returns the tracked objects in list of dicts

  @param    params        Dict of parameters needed for tracking
  @return   tracked_data  The filled list of tracked data
  """

  tracked_data = []
  scene = SceneLoader(params["config"], scene_model=Scene).scene
  mgr = CamManager(params["input"], scene)

  detected_category = None
  if 'assets' in params:
    scene.tracker.updateObjectClasses(params['assets'])

  while True:
    _, cam_detect, _ = mgr.nextFrame(scene, loop=False)
    if not cam_detect:
      break
    objects = cam_detect["objects"]
    scene.processCameraData(cam_detect)

    jdata = {
        "cam_id": cam_detect["id"],
        "frame": cam_detect["frame"],
        "timestamp": cam_detect["timestamp"]
    }
    get_detections(tracked_data, scene, objects, jdata)

  scene.tracker.join()
  return tracked_data

def get_msoce_value(params):
  """! Calculates msoce and returns it

  @param  params                     Dict of parameters needed for test
  @return msoce                      Mean Squared Object Count Error
  """

  pred_data = track(params)
  gt_data, _, _ = json_helper.loadData(params["ground_truth"])
  msoce = metrics.getMeanSquareObjCountError(gt_data, pred_data)
  print("msoce: {}".format(msoce))
  return msoce

def test_distance_msoce(params, assets, record_xml_attribute):
  """! This function calculates msoce based on the default input variables
  then compares it with the modified calculated values based on the modified
  Library Object proprieties.

  @param   params                    Dict of parameters needed for test
  @param   assets                    Touple of Object Library assets
  @returns result                    0 on success else 1
  """

  TEST_NAME = "NEX-T10524"
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  result = 1

  try:
    # For adding different object classes and trying out different parameters
    msoce0 = get_msoce_value(params)

    params["assets"] = [assets[0], assets[3]]
    msoce1 = get_msoce_value(params)

    params["assets"] = [assets[1], assets[3]]
    msoce2 = get_msoce_value(params)

    params["assets"] = [assets[2], assets[3]]
    msoce3 = get_msoce_value(params)

    print(f"Verifying that {msoce0=} is greater than {msoce1=}")
    assert msoce0 >= msoce1

    print(f"Verifying that {msoce2=} is greater than {msoce1=}")
    assert msoce2 >= msoce1

    print(f"Verifying that {msoce3=} is greater than {msoce1=}")
    assert msoce3 >= msoce1
    result = 0

  finally:
    common.record_test_result(TEST_NAME, result)

  assert result == 0
  return result


if __name__ == "__main__":
  exit(test_distance_msoce() or 0)
