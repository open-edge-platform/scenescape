# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Load a PhysicalAI-SmartSpaces scene into the Scene Metadata event log.

Lab_000 uses the dataset's cartesian calibration and ground-truth tracks.
A north region is the half-plane y > 0. A tripwire is the line x = -2.5.
The tracks have no appearance attributes, so none are stored here.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scene_metadata.envelope import EventEnvelope

SCENE_ID = 'Lab_000'
REGION_ID = 'lab-north'
TRIPWIRE_ID = 'x-minus-2-5'
REGION_Y = 0.0
TRIPWIRE_X = -2.5
FPS = 30
EPOCH = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _when(frame: int) -> datetime:
  return EPOCH + timedelta(seconds=frame / FPS)


def _identity(object_id: int) -> str:
  return f'person-{object_id}'


def _attr(sensor: dict, name: str):
  for item in sensor.get('attributes') or []:
    if item.get('name') == name:
      return item.get('value')
  return None


def scene_events(calibration: dict, deployment_id: str, map_name: str) -> list[EventEnvelope]:
  """Register the floor map and each calibrated camera."""
  sensors = [s for s in calibration.get('sensors') or [] if s.get('type') == 'camera']
  events = [EventEnvelope(
    occurred_at=EPOCH,
    event_type='config_scene',
    source_topic='physicalai/scene/Lab_000',
    deployment_id=deployment_id,
    scene_id=SCENE_ID,
    source_message_id='config-scene-Lab_000',
    payload={
      'name': 'PhysicalAI Lab_000',
      'map': map_name,
      'calibration_type': calibration.get('calibrationType'),
      'camera_count': len(sensors),
      'source': 'nvidia/PhysicalAI-SmartSpaces',
      'license': 'CC-BY-4.0',
    },
  )]
  for sensor in sensors:
    camera_id = sensor['id']
    events.append(EventEnvelope(
      occurred_at=EPOCH,
      event_type='config_camera',
      source_topic=f'physicalai/camera/{camera_id}',
      deployment_id=deployment_id,
      scene_id=SCENE_ID,
      camera_id=camera_id,
      source_message_id=f'config-camera-{camera_id}',
      payload={
        'coordinates': sensor.get('coordinates'),
        'scale_factor': sensor.get('scaleFactor'),
        'translation_to_global': sensor.get('translationToGlobalCoordinates'),
        'fps': _attr(sensor, 'fps'),
        'direction': _attr(sensor, 'direction'),
        'frame_width': _attr(sensor, 'frameWidth'),
        'frame_height': _attr(sensor, 'frameHeight'),
      },
    ))
  return events


def track_events(ground_truth: dict, deployment_id: str) -> list[EventEnvelope]:
  """Turn labeled tracks into timeline, region, tripwire, and camera events."""
  frames = sorted(int(key) for key in ground_truth)
  by_id: dict[int, list[tuple[int, dict]]] = {}
  for frame in frames:
    for obj in ground_truth[str(frame)]:
      if obj.get('object type') != 'Person':
        continue
      by_id.setdefault(obj['object id'], []).append((frame, obj))

  events: list[EventEnvelope] = []
  for object_id, samples in by_id.items():
    identity = _identity(object_id)
    first_frame, first_obj = samples[0]
    last_frame, _last_obj = samples[-1]
    events.append(EventEnvelope(
      occurred_at=_when(first_frame),
      event_type='track_started',
      source_topic=f'physicalai/track/{identity}',
      deployment_id=deployment_id,
      scene_id=SCENE_ID,
      identity_id=identity,
      track_id=identity,
      source_message_id=f'track-start-{identity}',
      payload={
        'frame': first_frame,
        'location': first_obj.get('3d location'),
      },
    ))
    events.append(EventEnvelope(
      occurred_at=_when(last_frame),
      event_type='track_lost',
      source_topic=f'physicalai/track/{identity}',
      deployment_id=deployment_id,
      scene_id=SCENE_ID,
      identity_id=identity,
      track_id=identity,
      source_message_id=f'track-lost-{identity}',
      payload={'frame': last_frame},
    ))
    seen_cameras: set[str] = set()
    anchor_camera = None
    in_region = False
    prev_x = None
    for frame, obj in samples:
      loc = obj.get('3d location') or [None, None, None]
      x, y = loc[0], loc[1]
      visible = set((obj.get('2d bounding box visible') or {}))
      if anchor_camera is None and visible:
        anchor_camera = min(visible)
      for camera_id in sorted(visible - seen_cameras):
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='camera_visible',
          source_topic=f'physicalai/camera/{camera_id}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          camera_id=camera_id,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'cam-{identity}-{camera_id}-{frame}',
          payload={'frame': frame},
        ))
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='reid_link',
          source_topic=f'physicalai/reid/{identity}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          camera_id=camera_id,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'reid-{identity}-{camera_id}-{frame}',
          payload={
            'frame': frame,
            'global_id': identity,
            'camera_id': camera_id,
            'anchor_camera': anchor_camera,
            'score': 1.0,
            'method': 'ground_truth_object_id',
          },
        ))
      seen_cameras |= visible
      inside = y is not None and y > REGION_Y
      if inside and not in_region:
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='region_enter',
          source_topic=f'physicalai/region/{REGION_ID}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          region_id=REGION_ID,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'region-enter-{identity}-{frame}',
          payload={'frame': frame, 'location': loc, 'rule': 'y > 0'},
        ))
      elif in_region and not inside:
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='region_exit',
          source_topic=f'physicalai/region/{REGION_ID}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          region_id=REGION_ID,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'region-exit-{identity}-{frame}',
          payload={'frame': frame, 'location': loc, 'rule': 'y > 0'},
        ))
      in_region = inside
      if prev_x is not None and x is not None and (prev_x < TRIPWIRE_X) != (x < TRIPWIRE_X):
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='tripwire_cross',
          source_topic=f'physicalai/tripwire/{TRIPWIRE_ID}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          tripwire_id=TRIPWIRE_ID,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'tripwire-{identity}-{frame}',
          payload={
            'frame': frame,
            'from_x': prev_x,
            'to_x': x,
            'rule': 'x = -2.5',
            'cameras_visible': sorted(visible),
            'reid_cameras': sorted(seen_cameras),
          },
        ))
        events.append(EventEnvelope(
          occurred_at=_when(frame),
          event_type='reid_at_crossing',
          source_topic=f'physicalai/reid/{identity}',
          deployment_id=deployment_id,
          scene_id=SCENE_ID,
          tripwire_id=TRIPWIRE_ID,
          identity_id=identity,
          track_id=identity,
          source_message_id=f'reid-cross-{identity}-{frame}',
          payload={
            'frame': frame,
            'global_id': identity,
            'cameras_visible': sorted(visible),
            'reid_cameras': sorted(seen_cameras),
            'method': 'ground_truth_object_id',
          },
        ))
      prev_x = x
  return events


def load_directory(path: Path, deployment_id: str) -> list[EventEnvelope]:
  """Read calibration, map name, and ground truth from a dataset directory."""
  calibration = json.loads((path / 'calibration.json').read_text(encoding='utf-8'))
  ground_truth = json.loads((path / 'ground_truth.json').read_text(encoding='utf-8'))
  map_name = 'map.png' if (path / 'map.png').is_file() else ''
  return scene_events(calibration, deployment_id, map_name) + track_events(
    ground_truth, deployment_id)
