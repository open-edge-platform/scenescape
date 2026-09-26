#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Prepare radar demo inputs: (N,5) frames and/or VoD-style ``pcd_bin`` .bin files.

Prefer real VIDETEC-2 frames when ``--frames-dir`` or ``--hdf5`` is set; otherwise
generate synthetic frames (CI / no-archive fallback).

Writes under ``--out-dir``:
  frames/%06d.npy
  pcd_bin/%06d.bin   float32 (N,7)
  frames/index.json  (copied or generated; includes timestamps when available)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

# Allow running from / inside the data-init container (script mounted at /).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from videtec_to_pcd import videtec_to_pcd  # noqa: E402


def _write_pcd_from_frames(frames_dir: Path, pcd_dir: Path) -> int:
  pcd_dir.mkdir(parents=True, exist_ok=True)
  npy_files = sorted(frames_dir.glob("*.npy"))
  if not npy_files:
    raise SystemExit(f"no *.npy frames under {frames_dir}")
  for path in npy_files:
    frame = np.load(path)
    videtec_to_pcd(frame).tofile(pcd_dir / f"{path.stem}.bin")
  return len(npy_files)


def _copy_frames(src: Path, dst: Path) -> None:
  dst.mkdir(parents=True, exist_ok=True)
  if src.resolve() == dst.resolve():
    return
  for path in src.glob("*.npy"):
    shutil.copy2(path, dst / path.name)
  for name in ("index.json", "sensor.json"):
    src_meta = src / name
    if src_meta.is_file():
      shutil.copy2(src_meta, dst / name)


def _from_hdf5(hdf5: Path, frames_dir: Path, max_frames: int | None) -> None:
  radar_dir = Path(__file__).resolve().parents[2] / "radar"
  # Host layout: sample_data/radar_intersection → repo/radar
  # Container layout: scripts mounted at /; converter at /videtec_hdf5_to_frames.py
  candidates = [
    Path("/videtec_hdf5_to_frames.py"),
    radar_dir / "videtec_hdf5_to_frames.py",
    _HERE.parent.parent / "radar" / "videtec_hdf5_to_frames.py",
  ]
  converter = next((p for p in candidates if p.is_file()), None)
  if converter is None:
    raise SystemExit("videtec_hdf5_to_frames.py not found")
  sys.path.insert(0, str(converter.parent))
  import videtec_hdf5_to_frames as vhf  # noqa: E402
  argv = [str(hdf5), "-o", str(frames_dir)]
  if max_frames is not None:
    argv.extend(["--max-frames", str(max_frames)])
  rc = vhf.main(argv)
  if rc:
    raise SystemExit(rc)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("-o", "--out-dir", type=Path, required=True,
                  help="Base radar_intersection output dir")
  ap.add_argument("--frames-dir", type=Path, default=None,
                  help="Existing (N,5) .npy frames (real VIDETEC preferred)")
  ap.add_argument("--hdf5", type=Path, default=None,
                  help="VIDETEC HDF5 to convert when frames-dir absent")
  ap.add_argument("--pcd-bin-dir", type=Path, default=None,
                  help="Existing pcd_bin to copy (skips conversion)")
  ap.add_argument("-n", "--num-frames", type=int, default=60,
                  help="Synthetic frame count (fallback only)")
  ap.add_argument("--max-frames", type=int, default=None,
                  help="Cap real HDF5 frames written")
  ap.add_argument("--seed", type=int, default=0)
  ap.add_argument("--require-real", action="store_true",
                  help="Fail if neither frames-dir, hdf5, nor pcd-bin is usable")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  out = args.out_dir
  frames_dst = out / "frames"
  pcd_dst = out / "pcd_bin"
  frames_dst.mkdir(parents=True, exist_ok=True)
  pcd_dst.mkdir(parents=True, exist_ok=True)

  used_real = False

  if args.pcd_bin_dir and args.pcd_bin_dir.is_dir() and any(args.pcd_bin_dir.glob("*.bin")):
    for path in sorted(args.pcd_bin_dir.glob("*.bin")):
      shutil.copy2(path, pcd_dst / path.name)
    if args.frames_dir and args.frames_dir.is_dir():
      _copy_frames(args.frames_dir, frames_dst)
    used_real = True
    print(f"Copied real pcd_bin from {args.pcd_bin_dir} → {pcd_dst}")
  elif args.frames_dir and args.frames_dir.is_dir() and any(args.frames_dir.glob("*.npy")):
    _copy_frames(args.frames_dir, frames_dst)
    n = _write_pcd_from_frames(frames_dst, pcd_dst)
    used_real = True
    print(f"Prepared {n} real frames from {args.frames_dir}")
  elif args.hdf5 and args.hdf5.is_file():
    _from_hdf5(args.hdf5, frames_dst, args.max_frames)
    n = _write_pcd_from_frames(frames_dst, pcd_dst)
    used_real = True
    print(f"Converted HDF5 {args.hdf5} → {n} frames + pcd_bin")
  else:
    if args.require_real:
      raise SystemExit(
        "require-real set but no usable --frames-dir / --hdf5 / --pcd-bin-dir")
    # Inline synthetic to avoid argparse re-entry quirks when imported.
    from generate_synthetic_radar_frames import make_videtec_frame
    rng = np.random.default_rng(args.seed)
    index = []
    for i in range(args.num_frames):
      t = i / max(1, args.num_frames - 1)
      clusters = [
        (8.0 + 4.0 * t, -5.0 + 2.0 * t, 28, 18.0),
        (18.0 + 6.0 * t, 12.0 - 3.0 * t, 24, 20.0),
        (12.0 + 2.0 * np.sin(t * 6), -15.0 + 8.0 * t, 20, 16.0),
      ]
      frame = make_videtec_frame(rng, clusters)
      np.save(frames_dst / f"{i:06d}.npy", frame)
      videtec_to_pcd(frame).tofile(pcd_dst / f"{i:06d}.bin")
      index.append({"frame_index": i, "path": f"{i:06d}.npy", "n": int(frame.shape[0])})
    (frames_dst / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"Synthetic fallback: {args.num_frames} frames → {out}")

  marker = out / "DATA_SOURCE.txt"
  marker.write_text("real-videtec\n" if used_real else "synthetic\n")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
