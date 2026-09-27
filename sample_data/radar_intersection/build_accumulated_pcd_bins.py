#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Build densified VoD ``pcd_bin`` for g3dinference multifilesrc playback.

For each kept frame index, concatenates gantry-static neighbors
``[fi - H, fi + H]`` and writes ``%06d.bin`` (float32, 7 features/point).
Point the demo ``RADAR_DATA_PATH`` at the output directory to get the same
±H densify used in offline GNSS eval without changing the GStreamer graph.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from videtec_accumulate import accumulate_points  # noqa: E402


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True,
                  help="VIDETEC frames/ with %%06d.npy (preferred) or pcd_bin/")
  ap.add_argument("-o", "--out-dir", type=Path, required=True,
                  help="Output densified pcd_bin directory")
  ap.add_argument("--accumulate-half-window", type=int, default=5,
                  help="Stack ±N neighbors (default 5, matches offline peak)")
  ap.add_argument("--start-index", type=int, default=0)
  ap.add_argument("--stop-index", type=int, default=None)
  ap.add_argument("--stride", type=int, default=1,
                  help="Only write every Nth frame index (default 1 = all)")
  ap.add_argument("--copy-index", action="store_true",
                  help="Also copy index.json / sensor.json under out-dir parent/frames/")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  frames_dir = args.frames_dir
  if any(frames_dir.glob("*.npy")):
    extension = ".npy"
  elif any(frames_dir.glob("*.bin")):
    extension = ".bin"
  else:
    raise SystemExit(f"no .npy/.bin under {frames_dir}")

  index_path = frames_dir / "index.json"
  if index_path.is_file():
    entries = json.loads(index_path.read_text())
    index_set = {int(e["frame_index"]) for e in entries}
  else:
    index_set = {
      int(p.stem) for p in frames_dir.glob(f"*{extension}") if p.stem.isdigit()}

  start = args.start_index
  stop = args.stop_index if args.stop_index is not None else max(index_set)
  stride = max(1, int(args.stride))
  half = max(0, int(args.accumulate_half_window))
  args.out_dir.mkdir(parents=True, exist_ok=True)

  n_written = 0
  for fi in range(start, stop + 1, stride):
    if fi not in index_set and not (frames_dir / f"{fi:06d}{extension}").is_file():
      continue
    pts = accumulate_points(frames_dir, fi, half, extension=extension)
    pts.astype(np.float32).tofile(args.out_dir / f"{fi:06d}.bin")
    n_written += 1
    if n_written % 500 == 0:
      print(f"... {n_written} densified bins", flush=True)

  meta = {
    "accumulate_half_window": half,
    "source_frames_dir": str(frames_dir),
    "extension": extension,
    "start_index": start,
    "stop_index": stop,
    "stride": stride,
    "n_written": n_written,
  }
  (args.out_dir / "accumulate_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
  print(f"Wrote {n_written} densified bins (±{half}) → {args.out_dir}")

  if args.copy_index:
    frames_out = args.out_dir.parent / "frames"
    frames_out.mkdir(parents=True, exist_ok=True)
    for name in ("index.json", "sensor.json"):
      src = frames_dir / name
      if src.is_file():
        shutil.copy2(src, frames_out / name)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
