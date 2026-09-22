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

from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime


def parse_timestamp(timestamp: str) -> datetime:
  """Parse an ISO 8601 timestamp (accepting a trailing ``Z``) into a datetime."""
  return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def resolve_ground_truth_path(ground_truth) -> str:
  """Return the ground-truth file path from a str or length-1 iterator.

  The iterator form exists only for compatibility with the base evaluator
  signature; pipelines always pass a plain path string.
  """
  if isinstance(ground_truth, str):
    return ground_truth
  items = list(ground_truth)
  if items and isinstance(items[0], str):
    return items[0]
  raise RuntimeError(
    "Ground truth must be a file path string. "
    "Ensure dataset.get_ground_truth() returns a JSONL file path."
  )


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


def require_fps(base_fps: Optional[float]) -> float:
  """Return the explicitly configured frame rate, or raise if it is missing.

  Frame rate must come from configuration (dataset ``camera_fps`` forwarded via
  ``set_base_fps``). Inferring it from tracker-output timestamp spans is
  intentionally unsupported so evaluation never silently guesses the rate.
  """
  if base_fps is None:
    raise RuntimeError(
      "Frame rate is required but was not configured. Set 'camera_fps' in the "
      "dataset pipeline config; it is forwarded to evaluators via set_base_fps()."
    )
  return base_fps


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
