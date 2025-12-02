#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
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

  scene.tracker.waitForComplete()
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
  print("Using tracker config: " + params["trackerconfig"])
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


if __name__ == "__main__":
  exit(test_distance_msoce() or 0)
