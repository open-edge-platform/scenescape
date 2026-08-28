#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for radar frame contract and v1 perception.

Import path: ``tests/sscape_tests/radar/conftest.py`` adds ``radar/`` to sys.path.
"""

import numpy as np

from radar_frame import as_frame, spherical_to_xyz
from radar_perception import RadarPerception


def test_as_frame_empty():
  frame = as_frame([])
  assert frame.shape == (0, 5)


def test_spherical_to_xyz_forward():
  # range 10 m, az 0, el 0 -> (10, 0, 0)
  frame = as_frame([[10.0, 0.0, 0.0, 0.0, 1.0]])
  xyz = spherical_to_xyz(frame)
  assert xyz.shape == (1, 3)
  np.testing.assert_allclose(xyz[0], [10.0, 0.0, 0.0], atol=1e-5)


def test_perception_clusters_and_tracks():
  perc = RadarPerception(cluster_distance_m=2.0, track_distance_m=5.0)
  frame1 = [
    [10.0, 0.0, 0.0, 0.0, 1.0],
    [10.2, 0.0, 1.0, 0.0, 1.0],
  ]
  objects = perc.process(frame1)
  assert "vehicle" in objects
  assert len(objects["vehicle"]) == 1
  tid = objects["vehicle"][0]["id"]

  frame2 = [[10.5, 0.0, 0.0, 0.0, 1.0]]
  objects2 = perc.process(frame2)
  assert len(objects2["vehicle"]) == 1
  assert objects2["vehicle"][0]["id"] == tid


def test_perception_empty_clears():
  perc = RadarPerception()
  objects = perc.process([])
  assert objects == {"vehicle": []}
