#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import time

import cv2

import controller.tools.analytics.library.json_helper as json_helper
import controller.tools.analytics.library.metrics as metrics
import tests.common_test_utils as common
from controller.detections_builder import buildDetectionsList
from controller.scene import Scene
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader
from scene_common.camera import Camera
from scene_common.geometry import Region, Tripwire

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

  with open(params["trackerconfig"]) as f:
    trackerConfigData = json.load(f)
  max_unreliable_time = trackerConfigData["max_unreliable_frames"]/trackerConfigData["baseline_frame_rate"]
  non_measurement_time_dynamic = trackerConfigData["non_measurement_frames_dynamic"]/trackerConfigData["baseline_frame_rate"]
  non_measurement_time_static = trackerConfigData["non_measurement_frames_static"]/trackerConfigData["baseline_frame_rate"]
  time_chunking_enabled = trackerConfigData["time_chunking_enabled"]
  time_chunking_interval_ms = trackerConfigData["time_chunking_interval_milliseconds"]

  camera_fps = []
  for input_file in params["input"]:
    cam = cv2.VideoCapture(input_file.removesuffix('.json')+'.mp4')
    fps = cam.get(cv2.CAP_PROP_FPS)
    if fps == 0.0:
      fps = int(params["default_camera_frame_rate"]) # default value
    camera_fps.append(fps)
    cam.release()
  ref_camera_fps = int(min(camera_fps))

  if time_chunking_enabled:
    time_chunking_interval_ms = int((1 / ref_camera_fps) * 1000)
    print(f"Time chunking ENABLED with interval: {time_chunking_interval_ms}ms for {ref_camera_fps} FPS")
  else:
    print("Time chunking DISABLED")

  loader = SceneLoader(params["config"])
  scene_config = loader.config

  scene = Scene(
    scene_config['name'],
    scene_config.get('map'),
    scene_config.get('scale'),
    max_unreliable_time=max_unreliable_time,
    non_measurement_time_dynamic=non_measurement_time_dynamic,
    non_measurement_time_static=non_measurement_time_static,
    time_chunking_enabled=time_chunking_enabled,
    time_chunking_interval_milliseconds=time_chunking_interval_ms
  )

  if 'sensors' in scene_config:
    for name in scene_config['sensors']:
      info = scene_config['sensors'][name]
      if 'map points' in info:
        if scene.areCoordinatesInPixels(info['map points']):
          info['map points'] = scene.mapPixelsToMetric(info['map points'])
      camera = Camera(name, info)
      scene.cameras[name] = camera

  if 'regions' in scene_config:
    for region in scene_config['regions']:
      points = region['points']
      if scene.areCoordinatesInPixels(points):
        region['points'] = scene.mapPixelsToMetric(points)
      region_obj = Region(region['uuid'], region['name'], {'points': region['points']})
      scene.regions[region_obj.name] = region_obj

  if 'tripwires' in scene_config:
    for tripwire in scene_config['tripwires']:
      points = tripwire['points']
      if scene.areCoordinatesInPixels(points):
        points = scene.mapPixelsToMetric(points)
      tripwire_obj = Tripwire(tripwire['uuid'], tripwire['name'], {'points': points})
      scene.tripwires[tripwire_obj.name] = tripwire_obj

  scene.ref_camera_frame_rate = ref_camera_fps
  mgr = CamManager(params["input"], scene)

  if 'assets' in params:
    scene.tracker.updateObjectClasses(params['assets'])

  frame_interval = 1.0 / ref_camera_fps if time_chunking_enabled else 0
  start_time = time.time()
  frame_count = 0

  while True:
    _, cam_detect, _ = mgr.nextFrame(scene, loop=False)
    if not cam_detect:
      break
    objects = cam_detect["objects"]

    if time_chunking_enabled:
      frame_count += 1
      expected_time = start_time + (frame_count * frame_interval)
      current_time = time.time()
      sleep_time = expected_time - current_time
      if sleep_time > 0:
        time.sleep(sleep_time)

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

  TEST_NAME = "NEX-T10463_{}-metric-{}".format(params["metric"], params["trackerconfig_name"])
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  print("Using tracker config: " + params["trackerconfig"])
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


if __name__ == "__main__":
  exit(test_tracker_metric() or 0)
