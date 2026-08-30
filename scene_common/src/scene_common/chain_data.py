# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ChainData — per-object analytics state shared between tracker and analytics.

Lives in scene_common so that the analytics service can import it without
depending on the controller package (which pulls in robot_vision).

All field access that may race across threads (tracker vs analytics publish)
must hold ``_lock``. Prefer the helpers below over touching fields directly.
"""

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List

from scene_common.geometry import Point


@dataclass
class ChainData:
  regions: Dict
  publishedLocations: List[Point]
  persist: Dict
  active_sensors: set = field(default_factory=set)
  env_sensor_state: Dict = field(default_factory=dict)  # {'sensor_id': {'readings': [(ts, val), ...]}}
  attr_sensor_events: Dict = field(default_factory=dict)  # {'sensor_id': [(ts, val), ...]}
  _lock: Lock = field(default_factory=Lock)

  def copyPersist(self) -> Dict:
    """Return a shallow copy of persist under the chain lock."""
    with self._lock:
      return dict(self.persist) if isinstance(self.persist, dict) else {}

  def mergePersistMissing(self, values: Dict) -> None:
    """Fill unset persist keys from ``values`` under the chain lock."""
    if not values:
      return
    with self._lock:
      for attr, value in values.items():
        if self.persist.get(attr) is None:
          self.persist[attr] = value
