# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from typing import Any, List, Optional

from controller.moving_object import ChainData
from scene_common.geometry import Point


@dataclass
class AnalyticsObject:
  """Stable analytics contract for a single tracked object.

  Anti-Corruption Layer between Controller internals (MovingObject) and
  analytics logic.  Analytics methods must access tracked-object data only
  through this model — never directly through MovingObject or any other
  Controller-internal class.

  Required fields reflect the minimum surface accessed by region, tripwire,
  and sensor analytics.  Optional fields (mesh, bbMeters, size) are used only
  by the 3-D mesh-intersection path and default to None.

  chain_data is always a shared reference — analytics mutates it in-place to
  record region entry/exit timestamps, sensor state, and location history.
  """
  gid: str
  category: str
  frameCount: int
  sceneLoc: Point
  chain_data: ChainData
  mesh: Optional[Any] = None
  bbMeters: Optional[Any] = None
  size: Optional[Any] = None


@dataclass
class AnalyticsFrame:
  """A batch of AnalyticsObject instances for one detection-type / timestamp cycle."""
  detection_type: str
  timestamp: float
  objects: List[AnalyticsObject] = field(default_factory=list)


@dataclass
class AnalyticsEvent:
  """A single analytics output event.

  This is a stub for Phase 1.  Fully defined in Phase 2 when event generation
  is extracted from scene.py into the analytics library.
  """
  event_type: str
  key: str
  timestamp: float
