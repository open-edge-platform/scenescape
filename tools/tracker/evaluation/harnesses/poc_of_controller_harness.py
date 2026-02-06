#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import time

from controller.detections_builder import buildDetectionsList
from controller.scene import Scene
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader
from scene_common.camera import Camera
from scene_common.geometry import Region, Tripwire

# the ratio of effective object update rate to camera frame rate
# equal to number of cameras that observe the detected objects at the same time
CAMERA_OVERLAP_RATIO = 2
TRACKER_PROCESSING_INTERVAL = 0.025  # 25 ms

def _sleep_until_time(expected_time):
  current_time = time.time()
  sleep_time = expected_time - current_time
  if sleep_time > 0:
    time.sleep(sleep_time)

def _dump_pred_data(pred_data):
  """! Dump prediction data and parameters to files.

  @param    pred_data      The prediction data to dump
  """
  output_dir = "."
  output_file = os.path.join(output_dir, "output.json")
  with open(output_file, "w") as f:
    json.dump(pred_data, f, indent=2)
  print(f"Dumped pred_data to {output_file}")

def get_detections(tracked_data, scene, objects, jdata):
  """! This function builds the object list for the
  tracked data and returns it

  @param    tracked_data  The list of tracked data
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

  with open(params["tracker_config"]) as f:
    trackerConfigData = json.load(f)
  max_unreliable_time = trackerConfigData["max_unreliable_time_s"]
  non_measurement_time_dynamic = trackerConfigData["non_measurement_time_dynamic_s"]
  non_measurement_time_static = trackerConfigData["non_measurement_time_static_s"]
  effective_object_update_rate = trackerConfigData.get("effective_object_update_rate")
  time_chunking_enabled = trackerConfigData["time_chunking_enabled"]
  time_chunking_rate_fps = trackerConfigData.get("time_chunking_rate_fps")

  ref_camera_fps = params["camera_frame_rate"]

  if time_chunking_enabled:
    time_chunking_rate_fps = ref_camera_fps
    print(f"Time chunking ENABLED with rate: {time_chunking_rate_fps} FPS")
  else:
    effective_object_update_rate = ref_camera_fps * CAMERA_OVERLAP_RATIO
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
    effective_object_update_rate=effective_object_update_rate,
    time_chunking_enabled=time_chunking_enabled,
    time_chunking_rate_fps=time_chunking_rate_fps
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
  mgr = CamManager(params["cameras"], scene)

  if 'assets' in params:
    scene.tracker.updateObjectClasses(params['assets'])

  camera_count = len(params["cameras"])
  # frame interval in seconds: how long we wait per camera frame for processing thread before collecting detections
  # - in case of time chunking, it is 1 / (cumulative camera FPS)
  # - otherwise, it is a fixed small interval to allow tracker processing
  frame_interval = 1.0 / (ref_camera_fps * camera_count) if time_chunking_enabled else TRACKER_PROCESSING_INTERVAL
  start_time = time.time()
  frame_count = 0

  while True:
    _, cam_detect, _ = mgr.nextFrame(scene, loop=False)
    if not cam_detect:
      break
    objects = cam_detect["objects"]

    # this call is non-blocking, detections are put into queue and processed in separate thread
    scene.processCameraData(cam_detect)

    frame_count += 1

    if time_chunking_enabled:
      # in time chunking mode, camera FPS is equal to time-chunking rate and we simulate real time processing
      # before collecting detections from all cameras, wait until time-chunking interval elapses
      if frame_count % camera_count == 0:
        _sleep_until_time(start_time + (frame_count * frame_interval))
        jdata = {
            "cam_id": "all_cameras",
            "frame": cam_detect["frame"],
            "timestamp": cam_detect["timestamp"]
        }
        get_detections(tracked_data, scene, objects, jdata)

    else:
      # before collecting detections from this camera, wait fixed small interval to allow tracker processing
      _sleep_until_time(start_time + (frame_count * frame_interval))
      jdata = {
          "cam_id": cam_detect["id"],
          "frame": cam_detect["frame"],
          "timestamp": cam_detect["timestamp"]
      }
      get_detections(tracked_data, scene, objects, jdata)

  scene.tracker.join()
  return tracked_data

def main():
  params = {"tracker_config" : "tracker-config.json", "cameras": ['Cam_x1_0.json','Cam_x2_0.json'], "camera_frame_rate": 30, "config": "config.json"}
  pred_data = track(params)
  _dump_pred_data(pred_data)

if __name__ == "__main__":
  exit(main() or 0)
