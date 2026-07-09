# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from typing import Any, List, Optional

from controller.moving_object import ChainData
from scene_common.geometry import Point


def moving_object_to_analytics_object(obj) -> "AnalyticsObject":
  """Wrap any tracked-object duck type (MovingObject or SimpleNamespace) as AnalyticsObject.

  chain_data is kept as a shared reference so analytics mutations (region entry
  timestamps, sensor state, published location history) are visible on the
  source object and persist across frames.

  Optional mesh / bbMeters / size fields are carried through via getattr so the
  function works identically for MovingObject instances and the lightweight
  SimpleNamespace wrappers produced by _deserializeTrackedObjects.
  """
  return AnalyticsObject(
    gid=obj.gid,
    category=obj.category,
    frameCount=obj.frameCount,
    sceneLoc=obj.sceneLoc,
    chain_data=obj.chain_data,
    mesh=getattr(obj, 'mesh', None),
    bbMeters=getattr(obj, 'bbMeters', None),
    size=getattr(obj, 'size', None),
    raw_obj=obj,
  )


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
  raw_obj: Optional[Any] = None


def unwrap_for_publishing(obj):
  """Return the source object suitable for MQTT event publishing.

  Analytics computation flows through AnalyticsObject (the ACL contract).
  The Controller's detections_builder requires the full original object
  interface (velocity, info, reid, …).  This function returns raw_obj when
  set — i.e. the original MovingObject or SimpleNamespace passed into
  moving_object_to_analytics_object — and falls back to obj itself for
  test helpers that construct objects without the converter.
  """
  return getattr(obj, 'raw_obj', None) or obj


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
