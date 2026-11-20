# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""RollingTerrainDataset adapter for the tracker evaluation pipeline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets.canonical_dataset import CanonicalDataset


class RollingTerrainDataset(CanonicalDataset):
  """Dataset adapter for ``tests/system/metric/rolling_terrain_dataset``.

  Contains:
  - Scene: rolling-terrain (one person on a non-planar surface, scene mesh ``scene.glb``)
  - Cameras: cam_front_left, cam_back_right
  - FPS: 20 is the evaluation frame grid; the native timestamps are irregular
    (about 13 Hz, at least 58 ms apart), so every frame falls on its own grid cell
  """

  SCENE_NAME = "rolling-terrain"
  SUPPORTED_CAMERAS = ["cam_front_left", "cam_back_right"]
  SUPPORTED_FPS = [20]
  DEFAULT_FPS = 20
