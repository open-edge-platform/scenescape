# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Recorded per-frame detections and their lookup by video time or frame.

The metadata is a JSON Lines file with one SceneScape camera message per line
(as published on scenescape/data/camera/<cameraid>):

  {"timestamp": "2026-11-13T09:20:12.270Z",
   "objects": {"person": [{"category": "person", "confidence": 1.0,
                           "bounding_box_px": {"x": 120, "y": 235,
                                               "width": 78, "height": 227}}]}}

Only `timestamp` and each object's `category`, `confidence` and
`bounding_box_px` are used. Kept free of GStreamer imports so it can be unit
tested on the host.
"""

import bisect
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SYNC_MODES = ("time", "frame")


@dataclass(frozen=True)
class Detection:
  label: str
  confidence: float
  x: int
  y: int
  width: int
  height: int


def _parse_timestamp(value: str) -> int:
  """Microseconds since the epoch; integers keep record spacing exact."""
  moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
  if moment.tzinfo is None:
    moment = moment.replace(tzinfo=timezone.utc)
  return (moment - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(microseconds=1)


def _parse_detections(objects) -> tuple:
  detections = []
  for category, items in (objects or {}).items():
    for item in items:
      box = item["bounding_box_px"]
      detections.append(Detection(
        label=item.get("category") or category,
        confidence=float(item.get("confidence", 1.0)),
        x=int(box["x"]), y=int(box["y"]),
        width=int(box["width"]), height=int(box["height"]),
      ))
  return tuple(detections)


class DetectionTimeline:
  """Detections of one camera, indexed by time since the first record."""

  def __init__(self, records):
    """`records` is a list of (timestamp_microseconds, detections) in file order."""
    if not records:
      raise ValueError("Detection metadata has no records")
    times = [timestamp for timestamp, _ in records]
    if any(later < earlier for earlier, later in zip(times, times[1:])):
      raise ValueError("Detection metadata timestamps must not decrease")
    self.times = [(timestamp - times[0]) / 1_000_000 for timestamp in times]
    self.detections = [detections for _, detections in records]

  @classmethod
  def from_jsonl(cls, path):
    records = []
    with open(path, encoding="utf-8") as metadata:
      for number, line in enumerate(metadata, start=1):
        if not line.strip():
          continue
        try:
          message = json.loads(line)
          records.append((_parse_timestamp(message["timestamp"]),
                          _parse_detections(message.get("objects"))))
        except (KeyError, TypeError, ValueError) as error:
          raise ValueError(f"{path}:{number}: invalid detection record: {error}") from error
    return cls(records)

  def __len__(self):
    return len(self.detections)

  def at_time(self, seconds: float):
    """Detections of the first record at or after `seconds` of video time.

    Matches videos rendered at a constant frame rate from a variable-rate
    source: each video frame shows the next source frame not older than the
    frame's own time. Returns None past the last record.
    """
    index = bisect.bisect_left(self.times, seconds)
    return self.detections[index] if index < len(self.detections) else None

  def at_frame(self, frame: int):
    """Detections of the record at position `frame`, or None past the end."""
    return self.detections[frame] if 0 <= frame < len(self.detections) else None

  def lookup(self, mode: str, seconds: float, frame: int):
    if mode == "time":
      return self.at_time(seconds)
    if mode == "frame":
      return self.at_frame(frame)
    raise ValueError(f"Unknown sync mode '{mode}'. Valid: {SYNC_MODES}")
