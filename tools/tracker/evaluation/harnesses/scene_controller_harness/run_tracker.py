#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tracking script executed inside scene controller container.

This script is copied to the temporary workspace and executed inside
the container to run the tracker on input data.
"""

import json
import time

from controller.detections_builder import buildDetectionsList
from controller.scene import Scene
from controller.controller_mode import ControllerMode
from scene_common.scenescape import SceneLoader
from scene_common.camera import Camera
from scene_common.geometry import Region, Tripwire

TRACKER_PROCESSING_INTERVAL = 0.025  # 25 ms


def _sleep_until_time(expected_time):
  """Sleep until expected time is reached."""
  current_time = time.time()
  sleep_time = expected_time - current_time
  if sleep_time > 0:
    time.sleep(sleep_time)


def get_detections(tracked_data, scene, objects, jdata):
  """Build tracked object list and append to tracked data.

  Args:
    tracked_data: List to append tracked data to
    scene: Current scene being processed
    objects: Dict of detection objects
    jdata: JSON data containing detection info
  """
  obj_list = []
  for category in objects.keys():
    curr_objects = scene.tracker.currentObjects(category)
    for obj in curr_objects:
      obj_list.append(obj)

  jdata['objects'] = buildDetectionsList(obj_list, None)
  tracked_data.append(jdata)


def track():
  """Run tracking routine and return tracked objects.

  Returns:
    List of dicts containing tracked data
  """
  tracked_data = []

  # Load tracker configuration
  with open("tracker-config.json") as f:
    trackerConfigData = json.load(f)
  max_unreliable_time = trackerConfigData["max_unreliable_time_s"]
  non_measurement_time_dynamic = trackerConfigData["non_measurement_time_dynamic_s"]
  non_measurement_time_static = trackerConfigData["non_measurement_time_static_s"]
  effective_object_update_rate = trackerConfigData.get("effective_object_update_rate")
  time_chunking_enabled = trackerConfigData["time_chunking_enabled"]
  time_chunking_rate_fps = trackerConfigData.get("time_chunking_rate_fps")

  # Load scene configuration
  loader = SceneLoader("config.json")
  scene_config = loader.config
  ControllerMode.initialize(analytics_only=False)

  if time_chunking_enabled:
    ref_camera_fps = time_chunking_rate_fps
    print(f"Time chunking ENABLED with rate: {time_chunking_rate_fps} FPS")
  else:
    ref_camera_fps = effective_object_update_rate
    print("Time chunking DISABLED")

  # Create scene
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

  # Set up cameras
  if 'sensors' in scene_config:
    for name in scene_config['sensors']:
      info = scene_config['sensors'][name]
      if 'map points' in info:
        if scene.areCoordinatesInPixels(info['map points']):
          info['map points'] = scene.mapPixelsToMetric(info['map points'])
      camera = Camera(name, info)
      scene.cameras[name] = camera

  # Set up regions
  if 'regions' in scene_config:
    for region in scene_config['regions']:
      points = region['points']
      if scene.areCoordinatesInPixels(points):
        region['points'] = scene.mapPixelsToMetric(points)
      region_obj = Region(region['uuid'], region['name'], {'points': region['points']})
      scene.regions[region_obj.name] = region_obj

  # Set up tripwires
  if 'tripwires' in scene_config:
    for tripwire in scene_config['tripwires']:
      points = tripwire['points']
      if scene.areCoordinatesInPixels(points):
        points = scene.mapPixelsToMetric(points)
      tripwire_obj = Tripwire(tripwire['uuid'], tripwire['name'], {'points': points})
      scene.tripwires[tripwire_obj.name] = tripwire_obj

  scene.ref_camera_frame_rate = ref_camera_fps

  # Load inputs from single file (newline-delimited JSON)
  # Inputs are already sorted by timestamp from dataset
  input_frames = []
  with open("inputs.json", 'r') as f:
    for line in f:
      if line.strip():
        frame = json.loads(line.strip())
        input_frames.append(frame)

  # Count unique cameras to determine frame interval
  camera_ids = set(frame['id'] for frame in input_frames)
  camera_count = len(camera_ids)

  if time_chunking_enabled and ref_camera_fps and camera_count:
    frame_interval = 1.0 / (ref_camera_fps * camera_count)
  else:
    frame_interval = TRACKER_PROCESSING_INTERVAL
  start_time = time.time()
  frame_count = 0

  # Process all frames
  for cam_detect in input_frames:
    objects = cam_detect.get("objects", {})

    # Process camera data through tracker
    scene.processCameraData(cam_detect)

    frame_count += 1

    if time_chunking_enabled:
      if frame_count % camera_count == 0:
        _sleep_until_time(start_time + (frame_count * frame_interval))
        jdata = {
          "cam_id": "all_cameras",
          "frame": cam_detect.get("frame"),
          "timestamp": cam_detect["timestamp"]
        }
        get_detections(tracked_data, scene, objects, jdata)
    else:
      _sleep_until_time(start_time + (frame_count * frame_interval))
      jdata = {
        "cam_id": cam_detect["id"],
        "frame": cam_detect.get("frame"),
        "timestamp": cam_detect["timestamp"]
      }
      get_detections(tracked_data, scene, objects, jdata)

  scene.tracker.join()
  return tracked_data


def main():
  """Main entry point."""
  print("Starting tracking script...")
  try:
    pred_data = track()

    # Write output
    with open("output.json", "w") as f:
      json.dump(pred_data, f, indent=2)
    print(f"Wrote {len(pred_data)} outputs to output.json")
    return 0
  except Exception as exc:
    print(f"Tracking run failed: {exc}")
    return 1


if __name__ == "__main__":
  exit(main() or 0)
