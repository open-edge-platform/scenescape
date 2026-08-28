# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 radar perception: spherical→XYZ, distance cluster, nearest-neighbor track."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from radar_frame import as_frame, default_object_size, spherical_to_xyz

DEFAULT_CLUSTER_DISTANCE_M = 2.5
DEFAULT_TRACK_DISTANCE_M = 5.0
DEFAULT_TRACK_TTL_FRAMES = 5
DEFAULT_CATEGORY = "vehicle"


@dataclass
class Track:
  track_id: int
  position: np.ndarray
  missed: int = 0
  confidence: float = 0.5


@dataclass
class RadarPerception:
  """Stateful cluster + track pipeline for (N, 5) frames."""

  cluster_distance_m: float = DEFAULT_CLUSTER_DISTANCE_M
  track_distance_m: float = DEFAULT_TRACK_DISTANCE_M
  track_ttl_frames: int = DEFAULT_TRACK_TTL_FRAMES
  category: str = DEFAULT_CATEGORY
  _next_id: int = 1
  _tracks: dict[int, Track] = field(default_factory=dict)

  def process(self, frame) -> dict[str, list[dict]]:
    """Return detector-style objects map for one frame (may be empty)."""
    xyz = spherical_to_xyz(as_frame(frame))
    clusters = self._cluster(xyz)
    matched = self._associate(clusters)
    objects = []
    for track in matched:
      objects.append({
        "id": track.track_id,
        "category": self.category,
        "translation": track.position.astype(float).tolist(),
        "size": default_object_size(),
        "confidence": float(track.confidence),
      })
    return {self.category: objects} if objects else {self.category: []}

  def _cluster(self, xyz: np.ndarray) -> list[np.ndarray]:
    if xyz.shape[0] == 0:
      return []
    remaining = list(range(xyz.shape[0]))
    clusters: list[np.ndarray] = []
    while remaining:
      seed = remaining.pop(0)
      members = [seed]
      changed = True
      while changed:
        changed = False
        centroid = xyz[members].mean(axis=0)
        keep = []
        for idx in remaining:
          if float(np.linalg.norm(xyz[idx] - centroid)) <= self.cluster_distance_m:
            members.append(idx)
            changed = True
          else:
            keep.append(idx)
        remaining = keep
      clusters.append(xyz[members].mean(axis=0))
    return clusters

  def _associate(self, clusters: list[np.ndarray]) -> list[Track]:
    unmatched_clusters = list(clusters)
    updated: dict[int, Track] = {}

    for track_id, track in self._tracks.items():
      best_idx = None
      best_dist = self.track_distance_m
      for i, cluster in enumerate(unmatched_clusters):
        dist = float(np.linalg.norm(cluster - track.position))
        if dist < best_dist:
          best_dist = dist
          best_idx = i
      if best_idx is not None:
        cluster = unmatched_clusters.pop(best_idx)
        updated[track_id] = Track(
          track_id=track_id,
          position=cluster,
          missed=0,
          confidence=min(1.0, track.confidence + 0.05),
        )
      else:
        missed = track.missed + 1
        if missed <= self.track_ttl_frames:
          updated[track_id] = Track(
            track_id=track_id,
            position=track.position,
            missed=missed,
            confidence=track.confidence * 0.8,
          )

    for cluster in unmatched_clusters:
      tid = self._next_id
      self._next_id += 1
      updated[tid] = Track(track_id=tid, position=cluster, missed=0, confidence=0.5)

    self._tracks = {tid: t for tid, t in updated.items() if t.missed == 0}
    return [t for t in updated.values() if t.missed == 0]
