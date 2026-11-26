# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""WildtrackDataset adapter for the tracker evaluation pipeline.

Serves the artifacts produced by ``datasets.wildtrack.preprocess``. Cameras may
be selected by integer id (0-6) or by canonical name (``cam0``..``cam6``).
"""

from typing import Union
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets.canonical_dataset import CanonicalDataset


class WildtrackDataset(CanonicalDataset):
  """Dataset adapter for the preprocessed Wildtrack dataset.

  Contains:
  - Scene: Wildtrack (single built-in scene)
  - Cameras: cam0..cam6 (7 static cameras)
  - FPS: 2 (native annotation cadence; no interpolation)
  """

  SCENE_NAME = "Wildtrack"
  NUM_CAMERAS = 7
  SUPPORTED_CAMERAS = [f"cam{i}" for i in range(NUM_CAMERAS)]
  SUPPORTED_FPS = [2]
  DEFAULT_FPS = 2

  @classmethod
  def _normalize_camera(cls, camera: Union[str, int]) -> str:
    """Normalize a camera selector (int 0-6 or ``camN``) to a canonical id."""
    if isinstance(camera, bool):
      raise ValueError(f"Invalid camera selector: {camera}")
    if isinstance(camera, int):
      camera = f"cam{camera}"
    try:
      return super()._normalize_camera(camera)
    except ValueError:
      raise ValueError(
        f"Unsupported camera: {camera}. Supported ids: {cls.SUPPORTED_CAMERAS} "
        f"(or integers 0-{cls.NUM_CAMERAS - 1})"
      ) from None
