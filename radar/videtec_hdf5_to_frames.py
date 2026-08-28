#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Convert VIDETEC-2 HDF5 ``/detections`` slices into (N, 5) frame files.

Archive-only helper. Live ingest uses the same float32 layout produced here.

Columns written: range_m, doppler_mps, azimuth_deg, elevation_deg, magnitude.

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


def scale_params(h5):
  """Return range/doppler bin→physical scale factors from /radar_params if present."""
  params = h5.get("radar_params")
  range_scale = 1.0
  doppler_scale = 1.0
  if params is None:
    return range_scale, doppler_scale
  # VIDETEC stores compound or dataset fields; accept common keys.
  data = params[()] if hasattr(params, "__getitem__") else params
  if hasattr(data, "dtype") and data.dtype.names:
    names = data.dtype.names
    row = data[0] if data.shape else data
    for key in ("range_resolution", "range_res", "range_bin_m"):
      if key in names:
        range_scale = float(row[key])
        break
    for key in ("doppler_resolution", "doppler_res", "velocity_resolution"):
      if key in names:
        doppler_scale = float(row[key])
        break
  elif isinstance(data, np.ndarray) and data.dtype == object:
    pass
  return range_scale, doppler_scale


def detections_table(h5):
  if "detections" not in h5:
    raise SystemExit("HDF5 missing /detections")
  return h5["detections"]


def frames_from_detections(dets, range_scale: float, doppler_scale: float):
  """Yield (frame_index, float32 (N,5)) from a VIDETEC detections compound table."""
  data = dets[()]
  if not hasattr(data, "dtype") or data.dtype.names is None:
    raise SystemExit("/detections must be a compound dataset")
  names = set(data.dtype.names)
  required = {"frame_index", "range", "doppler", "azimuth", "elevation", "magnitude"}
  missing = required - names
  if missing:
    raise SystemExit(f"/detections missing fields: {sorted(missing)}")

  frame_ids = np.unique(data["frame_index"])
  for frame_index in frame_ids:
    rows = data[data["frame_index"] == frame_index]
    frame = np.column_stack([
      rows["range"].astype(np.float32) * range_scale,
      rows["doppler"].astype(np.float32) * doppler_scale,
      rows["azimuth"].astype(np.float32),
      rows["elevation"].astype(np.float32),
      rows["magnitude"].astype(np.float32),
    ]).astype(np.float32)
    yield int(frame_index), frame


def write_frames(out_dir: Path, frames, fmt: str):
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
    index.append({"frame_index": frame_index, "path": path.name, "n": int(frame.shape[0])})
  (out_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n")
  return index


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("hdf5", type=Path, help="Path to VIDETEC HDF5 file")
  parser.add_argument("-o", "--output", type=Path, required=True, help="Output frames directory")
  parser.add_argument("--format", choices=("npy", "npz"), default="npy")
  parser.add_argument("--range-scale", type=float, default=None,
                      help="Override range bin→metres scale")
  parser.add_argument("--doppler-scale", type=float, default=None,
                      help="Override doppler bin→m/s scale")
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
    frames = frames_from_detections(dets, range_scale, doppler_scale)
    index = write_frames(args.output, frames, args.format)
  print(f"Wrote {len(index)} frames to {args.output} "
        f"(range_scale={range_scale}, doppler_scale={doppler_scale})")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
