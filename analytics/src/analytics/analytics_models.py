# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Any, Optional

from scene_common.chain_data import ChainData
from scene_common.geometry import Point


def moving_object_to_analytics_object(obj) -> "AnalyticsObject":
  """Wrap any tracked-object duck type (MovingObject or SimpleNamespace) as AnalyticsObject.

  chain_data is kept as a shared reference so analytics mutations (region entry
  timestamps, sensor state, published location history) are visible on the
  source object and persist across frames.

  Optional fields (mesh, bbMeters, size, velocity, info, rotation, metadata,
  reid) are carried through via getattr so the function works identically for
  MovingObject instances and the lightweight SimpleNamespace wrappers produced
  by SceneDataIngestion.
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
    velocity=getattr(obj, 'velocity', None),
    info=getattr(obj, 'info', None),
    rotation=getattr(obj, 'rotation', None),
    metadata=getattr(obj, 'metadata', None),
    reid=getattr(obj, 'reid', None),
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
  by the 3-D mesh-intersection path.  Publishing fields (velocity, info,
  rotation, metadata, reid) are carried through from the source object so that
  detections_builder can serialise AnalyticsObject instances directly without
  any unwrapping step.

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
  # Publishing fields — copied from the source object so AnalyticsObject is
  # self-contained for serialisation (no unwrapping needed).
  velocity: Optional[Any] = None
  info: Optional[Any] = None
  rotation: Optional[Any] = None
  metadata: Optional[Any] = None
  reid: Optional[Any] = None
