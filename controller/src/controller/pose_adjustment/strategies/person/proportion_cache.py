# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from collections import deque
from statistics import median
from typing import Deque, Dict, Optional, Tuple

from scene_common import log


RATIO_FIELDS = (
  'ratio_ankle_nose_hip',
  'ratio_ankle_shoulder_hip',
  'ratio_ankle_nose_shoulder',
  'ratio_ankle_head_hip',
  'ratio_ankle_knee_hip',
  'x_offset_from_hip',
  'x_offset_from_knee',
  'x_offset_from_torso',
)


class PersonProportionEntry:
  """Container for per-person body-proportion samples."""

  def __init__(self, max_samples: int):
    self.max_samples = max_samples
    self.samples: Dict[str, Deque[float]] = {
      name: deque(maxlen=max_samples) for name in RATIO_FIELDS
    }
    self.detection_count = 0
    self.observation_count = 0
    self.first_seen: Optional[float] = None
    self.last_seen: Optional[float] = None

  def mark_seen(self, when: float) -> None:
    self.detection_count += 1
    if self.first_seen is None:
      self.first_seen = when
    self.last_seen = when

  def add_observation(self, ratios: Dict[str, float], when: float) -> None:
    if not ratios:
      self.last_seen = when
      if self.first_seen is None:
        self.first_seen = when
      return

    self.last_seen = when
    if self.first_seen is None:
      self.first_seen = when
    added_value = False
    for name, value in ratios.items():
      if name not in self.samples or value is None:
        continue
      self.samples[name].append(float(value))
      added_value = True

    if added_value:
      self.observation_count += 1

  def medians(self) -> Dict[str, float]:
    result = {}
    for name, values in self.samples.items():
      if values:
        result[name] = float(median(values))
    return result


class ProportionCache:
  """Track median body proportions by source detection identity."""

  def __init__(
    self,
    max_samples: int = 20,
    max_entry_age_seconds: float = 10.0,
    min_observations: int = 3,
  ):
    self.max_samples = max_samples
    self.max_entry_age_seconds = max_entry_age_seconds
    self.min_observations = min_observations
    self._entries: Dict[Tuple[str, str, str], PersonProportionEntry] = {}

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    self.max_entry_age_seconds = max_entry_age_seconds

  def prune(self, now: float) -> None:
    stale_keys = [
      key for key, entry in self._entries.items()
      if entry.last_seen is not None and now - entry.last_seen > self.max_entry_age_seconds
    ]
    if stale_keys:
      log.debug(
        f"Pruning {len(stale_keys)} stale pose cache entries at time {now:.3f}: {stale_keys}"
      )
    for key in stale_keys:
      del self._entries[key]

  def mark_seen(self, cache_key: Tuple[str, str, str], when: float) -> None:
    entry = self._entries.get(cache_key)
    if entry is None:
      entry = PersonProportionEntry(self.max_samples)
      self._entries[cache_key] = entry
    entry.mark_seen(when)

  def add_observation(
    self,
    cache_key: Tuple[str, str, str],
    ratios: Dict[str, float],
    when: float,
  ) -> None:
    entry = self._entries.get(cache_key)
    if entry is None:
      entry = PersonProportionEntry(self.max_samples)
      self._entries[cache_key] = entry
    entry.add_observation(ratios, when)

  def get_medians(self, cache_key: Tuple[str, str, str]) -> Dict[str, float]:
    entry = self._entries.get(cache_key)
    if entry is None:
      log.debug(f"No pose cache entry for {cache_key}")
      return {}
    if entry.observation_count < self.min_observations:
      log.debug(
        f"Pose cache not ready for {cache_key}: "
        f"observations={entry.observation_count}/{self.min_observations}, "
        f"detections={entry.detection_count}"
      )
      return {}
    medians = entry.medians()
    log.debug(
      f"Pose cache medians for {cache_key}: "
      f"observations={entry.observation_count}, medians={medians}"
    )
    return medians
