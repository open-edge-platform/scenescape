# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Load robot-vision scenario recordings for plots and videos.

A scenario directory holds up to four JSONL files, written by ScenarioRecorder
(controller/src/robot_vision/test/support/ScenarioRecorder.hpp):

- groundtruth.jsonl: canonical ground truth, optionally with size, rotation,
  velocity and a "truth" object (speed, yaw_rate, acceleration)
- detections.jsonl: canonical camera-data frames with 3D detections
- tracks.jsonl: canonical tracker output
- estimator.jsonl: one "config" line per track, then one "step" line per
  estimator step

Any file may be missing, e.g. estimator.jsonl for real tracker output. Times
are in seconds since the earliest timestamp in the directory; ids are strings.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from utils.format_converters import stream_jsonl
from utils.timeline import parse_timestamp
from utils.tracks import match_tracks

GROUND_TRUTH_FILE = "groundtruth.jsonl"
DETECTIONS_FILE = "detections.jsonl"
TRACKS_FILE = "tracks.jsonl"
ESTIMATOR_FILE = "estimator.jsonl"
SCENARIO_FILES = (GROUND_TRUTH_FILE, DETECTIONS_FILE, TRACKS_FILE, ESTIMATOR_FILE)

GROUND_TRUTH_COLUMNS = [
  "t", "object_id", "category", "x", "y", "z", "length", "width", "height", "yaw",
  "vx", "vy", "speed", "yaw_rate", "acceleration",
]
DETECTION_COLUMNS = [
  "t", "sensor_id", "object_id", "category", "x", "y", "z", "length", "width", "height", "yaw",
]
TRACK_COLUMNS = [
  "t", "track_id", "category", "x", "y", "z", "length", "width", "height", "yaw", "vx", "vy",
]


@dataclass
class EstimatorTrace:
  """Estimator steps of one track. Arrays are indexed by step, in file order."""

  config: Dict[str, Any]
  t: np.ndarray                          # (N,) [s]
  model_probability: np.ndarray          # (N, models)
  state: np.ndarray                      # (N, 12)
  covariance: np.ndarray                 # (N, 12, 12)
  predicted_measurement: np.ndarray      # (N, 7), NaN at init
  predicted_measurement_cov: np.ndarray  # (N, 7, 7), NaN at init

  @property
  def motion_models(self) -> List[str]:
    """Motion model names, in the order of the model probabilities."""
    return list(self.config.get("motion_models", []))

  def state_index(self, name: str) -> int:
    """Index of a state such as "vx" or "yaw_rate" in the state vector."""
    return list(self.config["state_names"]).index(name)


@dataclass
class Scenario:
  """Contents of one scenario directory."""

  directory: Path
  start: Optional[datetime]
  ground_truth: pd.DataFrame
  detections: pd.DataFrame
  tracks: pd.DataFrame
  estimator: Dict[str, EstimatorTrace] = field(default_factory=dict)

  @property
  def object_ids(self) -> List[str]:
    """Ground-truth object ids."""
    return sorted(self.ground_truth["object_id"].unique())

  @property
  def track_ids(self) -> List[str]:
    """Track ids in tracks.jsonl."""
    return sorted(self.tracks["track_id"].unique())


def yaw_from_quaternion(rotation: Optional[Sequence[float]]) -> float:
  """Rotation about z of a quaternion [x, y, z, w]; NaN when there is none."""
  if not rotation:
    return math.nan
  qx, qy, qz, qw = rotation
  return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def load_scenario(directory) -> Scenario:
  """Load a scenario directory.

  Raises:
    FileNotFoundError: if the directory contains none of the scenario files.
  """
  directory = Path(directory)
  if not any((directory / name).is_file() for name in SCENARIO_FILES):
    raise FileNotFoundError(f"No scenario files ({', '.join(SCENARIO_FILES)}) in {directory}")

  raw = {name: _read(directory / name) for name in SCENARIO_FILES}
  timestamps = [stamp for lines in raw.values() for stamp, _ in lines if stamp is not None]
  start = min(timestamps) if timestamps else None

  def seconds(stamp: datetime) -> float:
    return (stamp - start).total_seconds()

  return Scenario(
    directory=directory,
    start=start,
    ground_truth=_ground_truth(raw[GROUND_TRUTH_FILE], seconds),
    detections=_detections(raw[DETECTIONS_FILE], seconds),
    tracks=_tracks(raw[TRACKS_FILE], seconds),
    estimator=_estimator(raw[ESTIMATOR_FILE], seconds),
  )


def frame_rate(table: pd.DataFrame) -> Optional[float]:
  """Frame rate from the median interval between distinct times; None for fewer than two."""
  times = np.unique(table["t"].to_numpy())
  if len(times) < 2:
    return None
  return 1.0 / float(np.median(np.diff(times)))


def match_tracks_to_truth(scenario: Scenario, fps: Optional[float] = None) -> List[Tuple[str, str]]:
  """(track_id, object_id) pairs from utils.tracks.match_tracks.

  Times are quantized to frames at `fps`, by default the ground-truth frame rate.
  Pairs need utils.tracks.MIN_OVERLAP_FRAMES shared frames.
  """
  fps = fps or frame_rate(scenario.ground_truth)
  if fps is None or scenario.tracks.empty:
    return []

  def positions(table: pd.DataFrame, id_column: str) -> Dict[str, Dict[int, tuple]]:
    result: Dict[str, Dict[int, tuple]] = {}
    for item_id, t, x, y in zip(table[id_column], table["t"], table["x"], table["y"]):
      result.setdefault(item_id, {})[round(t * fps)] = (x, y)
    return result

  return match_tracks(positions(scenario.tracks, "track_id"),
                      positions(scenario.ground_truth, "object_id"))


def align_track_to_truth(scenario: Scenario, track_id: str, object_id: Optional[str] = None,
                         tolerance: float = 1e-3) -> pd.DataFrame:
  """Rows of one track with the ground truth of one object at the same time.

  The object id defaults to the track id. Ground-truth columns get a "_gt"
  suffix; they are NaN where no ground truth lies within `tolerance` seconds,
  e.g. while the track coasts after the ground truth ends.
  """
  object_id = track_id if object_id is None else object_id
  track = scenario.tracks[scenario.tracks["track_id"] == track_id].sort_values("t")
  truth = scenario.ground_truth[scenario.ground_truth["object_id"] == object_id].sort_values("t")
  truth = truth.drop(columns=["object_id"]).add_suffix("_gt").rename(columns={"t_gt": "t"})
  return pd.merge_asof(track.reset_index(drop=True), truth.reset_index(drop=True), on="t",
                       direction="nearest", tolerance=tolerance)


def _read(path: Path) -> List[Tuple[Optional[datetime], Dict[str, Any]]]:
  if not path.is_file():
    return []
  lines = []
  for record in stream_jsonl(str(path)):
    stamp = record.get("timestamp")
    lines.append((parse_timestamp(stamp) if stamp else None, record))
  return lines


def _table(rows: List[Dict[str, Any]], columns: List[str]) -> pd.DataFrame:
  table = pd.DataFrame(rows, columns=columns).astype({"t": float})
  return table.sort_values("t", kind="stable").reset_index(drop=True)


def _vector(values: Optional[Sequence[float]], size: int) -> List[float]:
  return list(values) if values else [math.nan] * size


def _ground_truth(lines, seconds) -> pd.DataFrame:
  rows = []
  for stamp, frame in lines:
    for obj in frame.get("objects", []):
      x, y, z = _vector(obj.get("translation"), 3)
      length, width, height = _vector(obj.get("size"), 3)
      vx, vy, _ = _vector(obj.get("velocity"), 3)
      truth = obj.get("truth", {})
      rows.append({
        "t": seconds(stamp), "object_id": str(obj["id"]), "category": obj.get("category", ""),
        "x": x, "y": y, "z": z, "length": length, "width": width, "height": height,
        "yaw": yaw_from_quaternion(obj.get("rotation")), "vx": vx, "vy": vy,
        "speed": truth.get("speed", math.hypot(vx, vy)),
        "yaw_rate": truth.get("yaw_rate", math.nan),
        "acceleration": truth.get("acceleration", math.nan),
      })
  return _table(rows, GROUND_TRUTH_COLUMNS)


def _detections(lines, seconds) -> pd.DataFrame:
  rows = []
  for stamp, frame in lines:
    for category, objects in frame.get("objects", {}).items():
      for obj in objects:
        # Pixel-only detections have no world position.
        if "translation" not in obj:
          continue
        x, y, z = obj["translation"]
        length, width, height = _vector(obj.get("size"), 3)
        rows.append({
          "t": seconds(stamp), "sensor_id": frame.get("id", ""),
          "object_id": str(obj["id"]) if "id" in obj else "", "category": category,
          "x": x, "y": y, "z": z, "length": length, "width": width, "height": height,
          "yaw": yaw_from_quaternion(obj.get("rotation")),
        })
  return _table(rows, DETECTION_COLUMNS)


def _tracks(lines, seconds) -> pd.DataFrame:
  rows = []
  for stamp, frame in lines:
    for obj in frame.get("objects", []):
      x, y, z = obj["translation"]
      length, width, height = _vector(obj.get("size"), 3)
      vx, vy, _ = _vector(obj.get("velocity"), 3)
      rows.append({
        "t": seconds(stamp), "track_id": str(obj["id"]),
        "category": obj.get("category", obj.get("type", "")),
        "x": x, "y": y, "z": z, "length": length, "width": width, "height": height,
        "yaw": yaw_from_quaternion(obj.get("rotation")), "vx": vx, "vy": vy,
      })
  return _table(rows, TRACK_COLUMNS)


def _estimator(lines, seconds) -> Dict[str, EstimatorTrace]:
  configs = {}
  steps: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = {}
  for stamp, record in lines:
    track_id = str(record["track_id"])
    if record["type"] == "config":
      configs[track_id] = record
    elif record["type"] == "step":
      steps.setdefault(track_id, []).append((stamp, record))
  return {
    track_id: _trace(configs.get(track_id, {}), track_steps, seconds)
    for track_id, track_steps in steps.items()
  }


def _trace(config, steps, seconds) -> EstimatorTrace:
  def stack(key: str, shape: Tuple[int, ...]) -> np.ndarray:
    return np.array([
      np.asarray(step[key], dtype=float) if step[key] is not None else np.full(shape, math.nan)
      for _, step in steps
    ]).reshape((len(steps), *shape))

  states = len(steps[0][1]["x"])
  measurements = len(next((step["z_pred"] for _, step in steps if step["z_pred"] is not None),
                          config.get("measurement_names", [])))
  return EstimatorTrace(
    config=config,
    t=np.array([seconds(stamp) for stamp, _ in steps]),
    model_probability=stack("mu", (len(steps[0][1]["mu"]),)),
    state=stack("x", (states,)),
    covariance=stack("P", (states, states)),
    predicted_measurement=stack("z_pred", (measurements,)),
    predicted_measurement_cov=stack("S", (measurements, measurements)),
  )
