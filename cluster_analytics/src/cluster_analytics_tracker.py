# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Lightweight greedy nearest-centroid cluster tracker.

Replaces the previous FSM-based implementation.  A cluster retains its UUID
across frames as long as its centroid is re-matched within `max_matching_distance`
and the cluster reappears within `expiry_seconds`.
"""

import math
import uuid as _uuid_mod
from dataclasses import dataclass
from typing import Dict, List, Optional

from scene_common import log


@dataclass
class TrackedCluster:
  """A DBSCAN cluster with a UUID that persists across frames."""
  uuid: str
  category: str
  centroid: Dict[str, float]        # {'x': float, 'y': float}
  objects_count: int
  shape_analysis: Dict
  velocity_analysis: Dict
  object_ids: List[str]
  dbscan_params: Dict
  first_seen: float
  last_seen: float

  def to_dict(self) -> Dict:
    """Convert to the dictionary format expected by MQTT publishing."""
    return {
      'id': self.uuid,
      'category': self.category,
      'objects_count': self.objects_count,
      'center_of_mass': self.centroid,
      'shape_analysis': self.shape_analysis,
      'velocity_analysis': self.velocity_analysis,
      'object_ids': self.object_ids,
      'dbscan_params': self.dbscan_params,
      'tracking': {
        'tracking_id': self.uuid,
        'first_seen': self.first_seen,
        'last_seen': self.last_seen,
      },
    }


class ClusterTracker:
  """
  Track clusters across frames using greedy nearest-centroid matching.

  Matching is done per category.  For each incoming detection the
  closest existing non-expired cluster (within ``max_matching_distance``)
  is reused; otherwise a new cluster with a fresh UUID is created.

  Clusters are considered expired when they have not been matched for
  longer than ``expiry_seconds``.
  """

  def __init__(self, max_matching_distance: float = 2.0,
               expiry_seconds: float = 10.0) -> None:
    self._max_dist = max_matching_distance
    self._expiry = expiry_seconds
    # {scene_id: {uuid: TrackedCluster}}
    self._clusters: Dict[str, Dict[str, TrackedCluster]] = {}
    # Latest timestamp seen per scene — used by get_clusters() for expiry
    self._current_time: Dict[str, float] = {}

  # ------------------------------------------------------------------
  # Public API
  # ------------------------------------------------------------------

  def update(self, scene_id: str, raw_detections: List[Dict],
             timestamp: float) -> None:
    """
    Match *raw_detections* against existing clusters and update state.

    Each element of *raw_detections* must contain at least:
      'category'      : str
      'center_of_mass': {'x': float, 'y': float}
      'objects_count' : int
      'shape_analysis', 'velocity_analysis', 'object_ids', 'dbscan_params'

    Clusters not matched in this frame retain their last_seen timestamp
    and are returned by get_clusters() until they expire.
    """
    self._current_time[scene_id] = timestamp
    scene_clusters = self._clusters.setdefault(scene_id, {})

    # Index non-expired clusters by category for fast lookup
    available: Dict[str, List[TrackedCluster]] = {}
    for cluster in scene_clusters.values():
      if timestamp - cluster.last_seen <= self._expiry:
        available.setdefault(cluster.category, []).append(cluster)

    matched_uuids: set = set()

    for det in raw_detections:
      category = det['category']
      cx = float(det['center_of_mass']['x'])
      cy = float(det['center_of_mass']['y'])

      candidates = [c for c in available.get(category, [])
                    if c.uuid not in matched_uuids]
      best, best_dist = self._nearest(cx, cy, candidates)

      if best is not None and best_dist <= self._max_dist:
        # Re-use existing cluster — update payload, preserve UUID
        best.centroid = {'x': cx, 'y': cy}
        best.objects_count = det['objects_count']
        best.shape_analysis = det['shape_analysis']
        best.velocity_analysis = det['velocity_analysis']
        best.object_ids = det['object_ids']
        best.dbscan_params = det['dbscan_params']
        best.last_seen = timestamp
        matched_uuids.add(best.uuid)
      else:
        # No suitable existing cluster — create a new one
        new_uuid = str(_uuid_mod.uuid4())
        scene_clusters[new_uuid] = TrackedCluster(
          uuid=new_uuid,
          category=category,
          centroid={'x': cx, 'y': cy},
          objects_count=det['objects_count'],
          shape_analysis=det['shape_analysis'],
          velocity_analysis=det['velocity_analysis'],
          object_ids=det['object_ids'],
          dbscan_params=det['dbscan_params'],
          first_seen=timestamp,
          last_seen=timestamp,
        )
        log.debug(f"New cluster {new_uuid[:8]} ({category}) at ({cx:.2f}, {cy:.2f})")

  def get_clusters(self, scene_id: str) -> List[TrackedCluster]:
    """Return all non-expired clusters for *scene_id*."""
    now = self._current_time.get(scene_id, 0.0)
    return [
      c for c in self._clusters.get(scene_id, {}).values()
      if now - c.last_seen <= self._expiry
    ]

  def clear_scene(self, scene_id: str) -> None:
    """Remove all tracked clusters for *scene_id* immediately.

    Call this when clustering settings change so that stale clusters
    do not linger until the normal expiry window elapses.
    """
    self._clusters.pop(scene_id, None)
    self._current_time.pop(scene_id, None)
    log.debug(f"Cleared cluster state for scene {scene_id}")

  # ------------------------------------------------------------------
  # Helpers
  # ------------------------------------------------------------------

  @staticmethod
  def _nearest(cx: float, cy: float,
               candidates: List[TrackedCluster]):
    """Return (closest_cluster, distance) or (None, inf) if empty."""
    best: Optional[TrackedCluster] = None
    best_dist = float('inf')
    for c in candidates:
      dx = c.centroid['x'] - cx
      dy = c.centroid['y'] - cy
      dist = math.sqrt(dx * dx + dy * dy)
      if dist < best_dist:
        best_dist = dist
        best = c
    return best, best_dist
