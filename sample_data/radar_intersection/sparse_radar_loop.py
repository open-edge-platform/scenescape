#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Classical / roadside OpenVINO publish loop on VIDETEC (N,5) frames.

Used by the radar-intersection demo when ``RADAR_PERCEPTION`` is
``classical`` or ``roadside`` (Intel OpenVINO for roadside; host cluster
for classical). RadarPillars stays on the GStreamer ``g3dinference`` path.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))
# Host checkout: repo_root/radar. Container: PYTHONPATH …/radar_lib.
_RADAR_HOST = _HERE.parents[1] / "radar"
if _RADAR_HOST.is_dir() and str(_RADAR_HOST) not in sys.path:
  sys.path.insert(0, str(_RADAR_HOST))

from radar_frame import as_frame, spherical_to_xyz  # noqa: E402
from radar_perception import RadarPerception  # noqa: E402
from roadside_ov_infer import RoadsideOVInfer  # noqa: E402


def _wall_clock_timestamp() -> str:
  from datetime import datetime, timezone
  dt = datetime.now(tz=timezone.utc)
  ms = dt.microsecond // 1000
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def _load_frame(path: Path) -> np.ndarray:
  if not path.is_file():
    return np.zeros((0, 5), dtype=np.float32)
  return as_frame(np.load(path))


def _accumulate(frames_dir: Path, fi: int, half: int) -> np.ndarray:
  chunks = []
  for i in range(fi - half, fi + half + 1):
    arr = _load_frame(frames_dir / f"{i:06d}.npy")
    if arr.shape[0]:
      chunks.append(arr)
  if not chunks:
    return np.zeros((0, 5), dtype=np.float32)
  return np.concatenate(chunks, axis=0)


def _classical_objects(perc: RadarPerception, frame: np.ndarray,
                       doppler_person_mps: float) -> dict[str, list[dict]]:
  xyz = spherical_to_xyz(frame)
  clusters = perc._cluster(xyz)
  tracks = perc._associate(clusters)
  objects: dict[str, list[dict]] = {}
  for track in tracks:
    if frame.shape[0]:
      dist = np.linalg.norm(xyz - track.position.reshape(1, 3), axis=1)
      mask = dist <= max(perc.cluster_distance_m, 0.5)
      dop = float(np.mean(np.abs(frame[mask, 1]))) if np.any(mask) else float(
        abs(frame[int(np.argmin(dist)), 1]))
    else:
      dop = 0.0
    cat = "person" if dop >= doppler_person_mps else "vehicle"
    size = [0.6, 0.6, 1.7] if cat == "person" else [2.0, 1.5, 1.5]
    objects.setdefault(cat, []).append({
      "id": int(track.track_id),
      "category": cat,
      "translation": track.position.astype(float).tolist(),
      "size": size,
      "confidence": float(track.confidence),
      "source": "radar",
    })
  return objects


def build_sparse_message(sensor_id: str, objects: dict, fps: float) -> dict:
  return {
    "id": sensor_id,
    "timestamp": _wall_clock_timestamp(),
    "rate": round(float(fps), 2),
    "objects": objects,
  }


def run_sparse_radar_publish(
  *,
  method: str,
  frames_dir: Path,
  sensor_id: str,
  client,
  topic: str,
  fps: float,
  loop: bool,
  start_index: int,
  stop_index: int | None,
  accumulate_half_window: int,
  roadside_config: Path | None,
  roadside_device: str,
  cluster_distance_m: float,
  track_distance_m: float,
  doppler_person_mps: float,
  publish_fn,
) -> None:
  """Blocking publish loop (call from a daemon thread)."""
  method = method.strip().lower()
  frames_dir = Path(frames_dir)
  files = sorted(frames_dir.glob("*.npy"))
  if not files:
    raise SystemExit(f"no .npy frames in {frames_dir}")

  # Map start/stop to file indices when names are zero-padded.
  indices = [int(p.stem) for p in files]
  if start_index not in indices:
    # allow start as offset into sorted list
    lo = indices[0] if not indices else start_index
  else:
    lo = start_index
  hi = stop_index if stop_index is not None else indices[-1]

  perc = None
  roadside = None
  if method == "classical":
    perc = RadarPerception(
      cluster_distance_m=cluster_distance_m,
      track_distance_m=track_distance_m,
    )
  elif method == "roadside":
    if roadside_config is None or not Path(roadside_config).is_file():
      raise SystemExit(f"roadside config missing: {roadside_config}")
    roadside = RoadsideOVInfer(roadside_config, device=roadside_device)
  else:
    raise SystemExit(f"unsupported sparse method: {method}")

  half = max(0, int(accumulate_half_window))
  published = 0
  seq = [i for i in indices if lo <= i <= hi]
  if not seq:
    seq = indices
  pos = 0
  print(
    f"[sparse-radar] method={method} frames={len(seq)} half={half} "
    f"fps={fps} dir={frames_dir}",
    flush=True,
  )
  while True:
    fi = seq[pos]
    frame = _accumulate(frames_dir, fi, half) if half else _load_frame(
      frames_dir / f"{fi:06d}.npy")
    if method == "classical":
      objects = _classical_objects(perc, frame, doppler_person_mps)
    else:
      objects = roadside.predict_objects(frame)
    msg = build_sparse_message(sensor_id, objects, fps)
    publish_fn(client, topic, msg)
    published += 1
    if published % max(1, int(fps)) == 0:
      n = sum(len(v) for v in objects.values())
      print(f"[sparse-radar] frames={published} objects={n} fi={fi}", flush=True)
    pos += 1
    if pos >= len(seq):
      if not loop:
        print("[sparse-radar] EOS", flush=True)
        return
      pos = 0
    time.sleep(1.0 / max(fps, 1e-3))
