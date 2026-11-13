# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic replay of a scripted scene through IntelLabsTracking, with the tracks written as exact text.

Used to compare two tracker configurations bit for bit (``float.hex``) and, run as a script, to record a golden
file before a change and compare it after:

  python tracking_replay.py golden.txt
"""

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from controller.ilabs_tracking import IntelLabsTracking
from scene_common.geometry import Point

FPS = 10
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DURATION_S = 14.0
OCCLUSION_S = (5.0, 6.0)
ASSOCIATIONS = {
  'euclidean': {'method': 'euclidean'},
  'euclidean_max_radius': {'method': 'euclidean', 'max_radius_m': 2.0},
  'position_mahalanobis': {'method': 'position_mahalanobis', 'gate_probability': 0.99, 'max_radius_m': 10.0},
}
MODES = ('immediate', 'batched')


def _detection(x, y, z, size):
  return SimpleNamespace(sceneLoc=Point(x, y, z), size=size, has_detection_rotation=False, rotation=None,
                         confidence=0.9, metadata={}, tracking_radius=2.0, has_measured_z=False)


def _frames():
  """Two people crossing seen by two cameras with fixed noise; the first person is occluded for a second."""
  rng = np.random.default_rng(7)
  frames = []
  for index in range(int(DURATION_S * FPS)):
    t = (index + 1) / FPS
    people = [(-8.0 + 1.4 * t, 0.0), (0.5, -8.0 + 1.4 * t)]
    cameras = []
    for _ in range(2):
      objects = []
      for number, (x, y) in enumerate(people):
        if number == 0 and OCCLUSION_S[0] <= t < OCCLUSION_S[1]:
          continue
        noise = rng.normal(0.0, 0.1, 2)
        objects.append(_detection(x + noise[0], y + noise[1], 0.0, [0.5, 0.5, 1.7]))
      cameras.append(objects)
    frames.append((t, cameras))
  return frames


def _tracker(association, **kwargs):
  return IntelLabsTracking(1.0, 0.8, 1.6, FPS, association_config=association, **kwargs)


def _lines(label, t, tracker):
  lines = []
  for track in sorted(tracker.tracker.get_reliable_tracks(), key=lambda track: track.id):
    values = [track.x, track.y, track.z, track.vx, track.vy, track.vz, track.yaw,
              track.length, track.width, track.height]
    covariance = getattr(track, 'measurement_covariance', None)
    if covariance is not None:
      values.extend(np.asarray(covariance, dtype=float).ravel().tolist())
    lines.append('{} {} id={} {}'.format(label, float(t).hex(), track.id, ' '.join(float(v).hex() for v in values)))
  return lines


def replay(association, mode, **tracker_kwargs):
  """Lines (one per reliable track and frame) of one association config and feed mode, exact to the last bit."""
  tracker = _tracker(ASSOCIATIONS[association], **tracker_kwargs)
  lines = []
  for t, cameras in _frames():
    when = START + timedelta(seconds=t)
    if mode == 'batched':
      tracker.update_tracks_batched(cameras, when)
    else:
      tracker.update_tracks([obj for camera in cameras for obj in camera], when)
    lines.extend(_lines(f'{association}/{mode}', t, tracker))
  return lines


def replay_all(**tracker_kwargs):
  lines = []
  for association in ASSOCIATIONS:
    for mode in MODES:
      lines.extend(replay(association, mode, **tracker_kwargs))
  return lines


if __name__ == '__main__':
  with open(sys.argv[1], 'w') as golden:
    golden.write('\n'.join(replay_all()) + '\n')
