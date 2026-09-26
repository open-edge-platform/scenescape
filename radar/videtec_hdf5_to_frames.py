#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Convert VIDETEC-2 HDF5 ``/detections`` (+ ``/frames``) into (N, 5) frame files.

Archive-only helper. Live ingest uses the same float32 layout produced here.

Columns written: range_m, doppler_mps, azimuth_deg, elevation_deg, magnitude.

Also writes ``index.json`` with per-frame ``timestamp`` (from ``/frames/timestamp``
when present) and optional ``sensor.json`` from ``/sensor`` attributes.

VIDETEC-2 (https://zenodo.org/records/17799385) is licensed CC BY 4.0.
Cite the dataset when redistributing converted frames.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

FRAME_COLUMNS = ("range_m", "doppler_mps", "azimuth_deg", "elevation_deg", "magnitude")


def _load_h5(path: Path):
  try:
    import h5py
  except ImportError as exc:
    raise SystemExit("h5py is required: pip install h5py") from exc
  return h5py.File(path, "r")


def _attr_float(obj, *keys, default=1.0):
  """Read the first matching float attribute or compound field."""
  attrs = getattr(obj, "attrs", {})
  for key in keys:
    if key in attrs:
      val = attrs[key]
      if hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
        return float(val[0])
      return float(val)
  # Fallback: compound / scalar dataset body (older sketches).
  data = obj[()] if hasattr(obj, "__getitem__") else obj
  if hasattr(data, "dtype") and data.dtype.names:
    row = data[0] if getattr(data, "shape", ()) else data
    for key in keys:
      if key in data.dtype.names:
        return float(row[key])
  return float(default)


def scale_params(h5):
  """Return range/doppler bin→physical scale factors from /radar_params."""
  params = h5.get("radar_params")
  if params is None:
    return 1.0, 1.0
  range_scale = _attr_float(
    params, "range_resolution_m", "range_resolution", "range_res", "range_bin_m",
    default=1.0)
  doppler_scale = _attr_float(
    params, "doppler_resolution_mps", "doppler_resolution", "doppler_res",
    "velocity_resolution", default=1.0)
  return range_scale, doppler_scale


def detections_table(h5):
  if "detections" not in h5:
    raise SystemExit("HDF5 missing /detections")
  return h5["detections"]


def frame_timestamps(h5):
  """Return 1-D int64 timestamps aligned with frame_index, or None."""
  frames = h5.get("frames")
  if frames is None:
    return None
  if "timestamp" in frames:
    return np.asarray(frames["timestamp"][()], dtype=np.int64)
  if hasattr(frames, "dtype") and getattr(frames.dtype, "names", None):
    if "timestamp" in frames.dtype.names:
      return np.asarray(frames["timestamp"][()], dtype=np.int64)
  return None


def sensor_metadata(h5):
  """Collect /sensor attributes into a JSON-serializable dict."""
  sensor = h5.get("sensor")
  if sensor is None:
    return {}
  out = {}
  for key, val in sensor.attrs.items():
    if isinstance(val, bytes):
      out[key] = val.decode("utf-8", errors="replace")
    elif hasattr(val, "tolist"):
      out[key] = val.tolist()
    else:
      out[key] = val if isinstance(val, (str, int, float, bool)) else str(val)
  return out


def frames_from_detections(dets, range_scale: float, doppler_scale: float,
                           n_frames: int | None = None):
  """Yield (frame_index, float32 (N,5)) for every frame index in [0, n_frames).

  Empty frames (no detections) yield shape (0, 5). When ``n_frames`` is None,
  only indices that appear in the detections table are emitted (legacy).
  """
  data = dets[()]
  if not hasattr(data, "dtype") or data.dtype.names is None:
    raise SystemExit("/detections must be a compound dataset")
  names = set(data.dtype.names)
  required = {"frame_index", "range", "doppler", "azimuth", "elevation", "magnitude"}
  missing = required - names
  if missing:
    raise SystemExit(f"/detections missing fields: {sorted(missing)}")

  by_index: dict[int, np.ndarray] = {}
  if data.size:
    frame_ids = data["frame_index"]
    for frame_index in np.unique(frame_ids):
      rows = data[frame_ids == frame_index]
      by_index[int(frame_index)] = np.column_stack([
        rows["range"].astype(np.float32) * range_scale,
        rows["doppler"].astype(np.float32) * doppler_scale,
        rows["azimuth"].astype(np.float32),
        rows["elevation"].astype(np.float32),
        rows["magnitude"].astype(np.float32),
      ]).astype(np.float32)

  if n_frames is None:
    for frame_index in sorted(by_index):
      yield frame_index, by_index[frame_index]
    return

  empty = np.zeros((0, 5), dtype=np.float32)
  for frame_index in range(int(n_frames)):
    yield frame_index, by_index.get(frame_index, empty)


def write_frames(out_dir: Path, frames, fmt: str, timestamps=None):
  out_dir.mkdir(parents=True, exist_ok=True)
  index = []
  for frame_index, frame in frames:
    if fmt == "npy":
      path = out_dir / f"{frame_index:06d}.npy"
      np.save(path, frame)
    else:
      path = out_dir / f"{frame_index:06d}.npz"
      header = ",".join(FRAME_COLUMNS)
      np.savetxt(path, frame, delimiter=",", header=header, comments="")
    entry = {"frame_index": frame_index, "path": path.name, "n": int(frame.shape[0])}
    if timestamps is not None and 0 <= frame_index < len(timestamps):
      entry["timestamp"] = int(timestamps[frame_index])
    index.append(entry)
  (out_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n")
  return index


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("hdf5", type=Path, help="Path to VIDETEC HDF5 file")
  parser.add_argument("-o", "--output", type=Path, required=True, help="Output frames directory")
  parser.add_argument("--format", choices=("npy", "csv"), default="npy")
  parser.add_argument("--range-scale", type=float, default=None,
                      help="Override range bin→metres scale")
  parser.add_argument("--doppler-scale", type=float, default=None,
                      help="Override doppler bin→m/s scale")
  parser.add_argument("--skip-empty", action="store_true",
                      help="Omit frames with zero detections (default: keep all)")
  parser.add_argument("--max-frames", type=int, default=None,
                      help="Limit number of frames written (from the start)")
  return parser.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  with _load_h5(args.hdf5) as h5:
    range_scale, doppler_scale = scale_params(h5)
    if args.range_scale is not None:
      range_scale = args.range_scale
    if args.doppler_scale is not None:
      doppler_scale = args.doppler_scale
    dets = detections_table(h5)
    timestamps = frame_timestamps(h5)
    n_frames = None if args.skip_empty else (None if timestamps is None else len(timestamps))
    if timestamps is None and not args.skip_empty:
      # Still prefer contiguous indices when detections alone define the span.
      data = dets[()]
      if data.size:
        n_frames = int(np.max(data["frame_index"])) + 1
    frames = frames_from_detections(dets, range_scale, doppler_scale, n_frames)
    if args.max_frames is not None:
      frames = ((i, f) for i, f in frames if i < args.max_frames)
      if timestamps is not None:
        timestamps = timestamps[:args.max_frames]
    index = write_frames(args.output, frames, args.format, timestamps=timestamps)
    sensor = sensor_metadata(h5)
    if sensor:
      (args.output / "sensor.json").write_text(json.dumps(sensor, indent=2) + "\n")
  print(f"Wrote {len(index)} frames to {args.output} "
        f"(range_scale={range_scale}, doppler_scale={doppler_scale})")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
