# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared timestamp/frame helpers for tracker evaluation.

Ground truth and tracker output share the same canonical (scene-data) format
with absolute ISO 8601 timestamps.  Track-vs-ground-truth matching is done by
mapping every absolute timestamp to an integer frame index using a common
reference epoch and frame rate (shared-reference quantization).  This keeps the
matching timestamp-based while remaining compatible with TrackEval, which
requires integer frame indices.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional
from datetime import datetime, timedelta, timezone


def parse_timestamp(timestamp: str) -> datetime:
  """Parse an ISO 8601 timestamp (accepting a trailing ``Z``) into a datetime."""
  return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def deduplicate_frames_by_timestamp(
  frames: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
  """Return frames with duplicate timestamps dropped, keeping the first seen."""
  seen: set = set()
  result: List[Dict[str, Any]] = []
  for frame in frames:
    ts = frame.get("timestamp")
    if ts in seen:
      continue
    seen.add(ts)
    result.append(frame)
  return result


def compute_fps(
  timestamps: List[datetime],
  base_fps: Optional[float] = None
) -> float:
  """Return frame rate, preferring ``base_fps`` and otherwise deriving it.

  When ``base_fps`` is None it is estimated from the span between the first and
  last timestamps; falls back to 30.0 for degenerate inputs.
  """
  if base_fps is not None:
    return base_fps
  if len(timestamps) > 1:
    span = (timestamps[-1] - timestamps[0]).total_seconds()
    return (len(timestamps) - 1) / span if span > 0 else 30.0
  return 30.0


def timestamp_to_frame(
  timestamp: datetime,
  reference: datetime,
  fps: float
) -> int:
  """Map an absolute timestamp to a 1-indexed frame relative to ``reference``."""
  return int(round((timestamp - reference).total_seconds() * fps)) + 1


def reference_timestamp(*frame_lists: List[Dict[str, Any]]) -> Optional[datetime]:
  """Return the earliest first-frame timestamp across the given frame lists.

  Provides the common reference epoch shared by ground truth and tracker output
  so that identical absolute timestamps map to the same frame index.
  """
  firsts: List[datetime] = []
  for frames in frame_lists:
    if frames:
      firsts.append(parse_timestamp(frames[0]["timestamp"]))
  return min(firsts) if firsts else None


def build_frame_indexed_tracks(
  frames: Iterable[Dict[str, Any]],
  reference: datetime,
  fps: float,
  id_fn: Callable[[Dict[str, Any]], Any],
  pos_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[Any, Dict[int, Any]]:
  """Build ``{track_key: {frame_index: position}}`` from canonical frames.

  ``id_fn`` extracts the track key from an object (returning None skips it) and
  ``pos_fn`` extracts the stored position value.
  """
  tracks: Dict[Any, Dict[int, Any]] = {}
  for frame in frames:
    frame_index = timestamp_to_frame(
      parse_timestamp(frame["timestamp"]), reference, fps
    )
    for obj in frame.get("objects", []):
      key = id_fn(obj)
      if key is None:
        continue
      tracks.setdefault(key, {})[frame_index] = pos_fn(obj)
  return tracks


def normalize_histories_to_fps(
  histories: Dict[Any, List[tuple]],
  fps: float
) -> Dict[Any, List[tuple]]:
  """Remap per-track ``(timestamp, value)`` histories onto an fps-fixed grid.

  Replaces wall-clock timestamps with ``epoch + index / fps`` based on the
  globally sorted unique timestamps, so kinematic derivatives are independent of
  processing speed while preserving relative frame ordering.
  """
  epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
  all_ts = sorted({ts for entries in histories.values() for ts, _ in entries})
  ts_to_idx = {ts: i for i, ts in enumerate(all_ts)}
  return {
    key: [
      (epoch + timedelta(seconds=ts_to_idx[ts] / fps), value)
      for ts, value in entries
    ]
    for key, entries in histories.items()
  }
