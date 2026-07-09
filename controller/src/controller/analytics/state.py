# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class RegionAnalyticsState:
  """Per-region analytics state owned by the analytics package.

  objects: current objects in the region, keyed by detection_type.  Persists
           across frames for enter/exit tracking.
  entered: objects that just entered this frame, keyed by detection_type.
           Consumed by the publishing pipeline and cleared by
           clear_frame_state() after each publish cycle.
  exited:  (object, dwell_seconds) pairs that just exited, keyed by
           detection_type.  Cleared the same way as entered.
  when:    epoch timestamp of the last debounced event.  Guards against
           repeated event emission within DEBOUNCE_DELAY.
  """
  objects: Dict[str, List[Any]] = field(default_factory=dict)
  entered: Dict[str, List[Any]] = field(default_factory=dict)
  exited: Dict[str, List[Tuple[Any, float]]] = field(default_factory=dict)
  when: float = 0.0

  def clear_frame_state(self):
    """Reset the per-frame enter/exit lists after publishing."""
    self.entered = {}
    self.exited = {}


@dataclass
class TripwireAnalyticsState:
  """Per-tripwire analytics state owned by the analytics package.

  objects: TripwireEvent objects currently crossing, keyed by detection_type.
  when:    epoch timestamp of the last debounced crossing event.
  """
  objects: Dict[str, List[Any]] = field(default_factory=dict)
  when: float = 0.0


class AnalyticsStateStore:
  """Owns all per-region and per-tripwire analytics state for one Scene.

  Replaces analytics-specific attributes (objects, entered, exited, when) that
  were previously stored directly on Region and Tripwire geometry objects.
  Geometry objects are now read-only from the analytics perspective — only
  their shape and configuration fields are accessed by the analytics library.

  State entries are created lazily on first access and removed explicitly when
  the corresponding geometry object is deleted (_updateRegions/_updateTripwires).
  """

  def __init__(self):
    self._regions: Dict[str, RegionAnalyticsState] = {}
    self._tripwires: Dict[str, TripwireAnalyticsState] = {}

  def region(self, key: str) -> RegionAnalyticsState:
    """Return the analytics state for region *key*, creating it on first access."""
    if key not in self._regions:
      self._regions[key] = RegionAnalyticsState()
    return self._regions[key]

  def tripwire(self, key: str) -> TripwireAnalyticsState:
    """Return the analytics state for tripwire *key*, creating it on first access."""
    if key not in self._tripwires:
      self._tripwires[key] = TripwireAnalyticsState()
    return self._tripwires[key]

  def remove_region(self, key: str) -> None:
    """Drop state for a deleted region or sensor."""
    self._regions.pop(key, None)

  def remove_tripwire(self, key: str) -> None:
    """Drop state for a deleted tripwire."""
    self._tripwires.pop(key, None)
