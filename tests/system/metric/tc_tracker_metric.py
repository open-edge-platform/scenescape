#!/usr/bin/env python3

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

import json
import os

import cv2

import analytics.library.json_helper as json_helper
import analytics.library.metrics as metrics
import tests.common_test_utils as common
from controller.detections_builder import buildDetectionsList
from controller.scene import Scene
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader

MSOCE_MEAN = 0.3344
IDC_MEAN = 0.007
STD_VELOCITY_MAX = 0.36

msgs = []

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
  if int(params["camera_frame_rate"]) in [10, 1]:
    # run the tests with 1 fps camera files
    dir = os.path.dirname(os.path.abspath(__file__))
    input_cam_1 = os.path.join(dir, "test_data/Cam_x1_0_"+str(params["camera_frame_rate"])+"fps.json")
    input_cam_2 = os.path.join(dir, "test_data/Cam_x2_0_"+str(params["camera_frame_rate"])+"fps.json")
    params["input"] = [input_cam_1, input_cam_2]
  tracked_data = []
  scene = SceneLoader(params["config"], scene_model=Scene).scene
  mgr = CamManager(params["input"], scene)

  with open(params["trackerconfig"]) as f:
    trackerConfigData = json.load(f)
  scene.max_unreliable_time = trackerConfigData["max_unreliable_frames"]/trackerConfigData["baseline_frame_rate"]
  scene.non_measurement_time_dynamic = trackerConfigData["non_measurement_frames_dynamic"]/trackerConfigData["baseline_frame_rate"]
  scene.non_measurement_time_static = trackerConfigData["non_measurement_frames_static"]/trackerConfigData["baseline_frame_rate"]
  scene.updateTracker(scene.max_unreliable_time, scene.non_measurement_time_dynamic, scene.non_measurement_time_static)
  camera_fps = []
  for input_file in params["input"]:
    cam = cv2.VideoCapture(input_file.removesuffix('.json')+'.mp4')
    fps = cam.get(cv2.CAP_PROP_FPS)
    if fps == 0.0:
      fps = int(params["default_camera_frame_rate"]) # default value
    camera_fps.append(fps)
    cam.release()
  scene.ref_camera_frame_rate = int(min(camera_fps))
  print("reference camera frame rate = ", scene.ref_camera_frame_rate)

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

def test_tracker_metric(params, assets, record_xml_attribute):
  """! This function calulcates max_velocity, msoce or idc-error and
  compares it to a desired threshold value

  @param   params                    Dict of parameters needed for test
  @param   record_xml_attribute      Pytest fixture recording the test name
  @returns result                    0 on success else 1
  """

  TEST_NAME = "NEX-T10463_{}-metric".format(params["metric"])
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  params["assets"] = [assets[3]]
  result = 1

  try:
    if params["metric"] == "velocity":
      pred_data = track(params)
      _, curr_std_velocity = metrics.getVelocity(pred_data)
      print("std velocity: {}".format(curr_std_velocity))
      assert curr_std_velocity <= (1.0 + float(params["threshold"])) * STD_VELOCITY_MAX
      result = 0

    elif params["metric"] == "msoce":
      pred_data = track(params)
      gt_data, _, _ = json_helper.loadData(params["ground_truth"])
      msoce = metrics.getMeanSquareObjCountError(gt_data, pred_data)
      print("msoce: {}".format(msoce))
      assert msoce <= (1.0 + float(params["threshold"])) * MSOCE_MEAN
      result = 0

    elif params["metric"] == "idc-error":
      pred_data = track(params)
      gt_data, _, _ = json_helper.loadData(params["ground_truth"])
      idc_error = metrics.getMeanIdChangeErrors(gt_data, pred_data)
      print("idc_error: {}".format(idc_error))
      assert idc_error <= (1.0 + float(params["threshold"])) * IDC_MEAN
      result = 0

    else:
      print("invalid metric")

  finally:
    common.record_test_result(TEST_NAME, result)
  assert result == 0
  return result

if __name__ == "__main__":
  exit(test_tracker_metric() or 0)
