#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Phase-1 VIDETEC comparison: classical + roadside vs RadarPillars.

Orchestrates batch infer + ``eval_radarpillars_gnss.py`` on window 2100–4100
(stride 5), single-frame and H=5 accumulate, and writes a summary JSON/MD.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_VID = _ROOT / "VIDETEC-2"
_FRAMES = _VID / "converted" / "frames"
_EVAL = _ROOT / "eval_radarpillars_gnss.py"
_PY_RP = Path.home() / "mainline" / "RadarPillar" / ".venv" / "bin" / "python"
_PY_VID = _VID / ".venv" / "bin" / "python"
_PY = _PY_VID if _PY_VID.is_file() else Path(sys.executable)


def _run(cmd: list[str]):
  print("+", " ".join(str(c) for c in cmd), flush=True)
  subprocess.check_call(cmd)


def _eval(dets: Path, out: Path, categories: str) -> dict:
  gnss = next((_VID / "gnss" / "rosbag2_2025_10_09-14_43_55").glob("*_gps.csv"))
  cmd = [
    str(_PY), str(_EVAL),
    "--index", str(_FRAMES / "index.json"),
    "--detections", str(dets),
    "--gnss", str(gnss),
    "--sensor", str(_FRAMES / "sensor.json"),
    "--videtec-origin",
    "--max-dt", "0.2",
    "--categories", categories,
    "-o", str(out),
  ]
  _run(cmd)
  return json.loads(out.read_text())


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--skip-train", action="store_true")
  ap.add_argument("--epochs", type=int, default=40)
  ap.add_argument("--device", default="cuda")
  ap.add_argument("--out-dir", type=Path, default=_VID / "phase1_baselines")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  out_dir = args.out_dir
  out_dir.mkdir(parents=True, exist_ok=True)
  py = str(_PY_RP if _PY_RP.is_file() else _PY)
  gnss = next((_VID / "gnss" / "rosbag2_2025_10_09-14_43_55").glob("*_gps.csv"))

  ckpt = out_dir / "roadside_videtec_ccby.pt"
  if not args.skip_train or not ckpt.is_file():
    _run([
      py, str(_HERE / "train_roadside_weak.py"),
      "--frames-dir", str(_FRAMES),
      "--index", str(_FRAMES / "index.json"),
      "--gnss", str(gnss),
      "--sensor", str(_FRAMES / "sensor.json"),
      "--train-start", "500",
      "--train-end", "9000",
      "--exclude-start", "2100",
      "--exclude-end", "4100",
      "--stride", "2",
      "--accumulate-half-window", "5",
      "--epochs", str(args.epochs),
      "--device", args.device,
      "-o", str(ckpt),
    ])

  results = {}
  for half, tag in ((0, "h0"), (5, "h5")):
    dets = out_dir / f"classical_{tag}.jsonl"
    _run([
      str(_PY), str(_HERE / "classical_batch.py"),
      "--frames-dir", str(_FRAMES),
      "--index", str(_FRAMES / "index.json"),
      "--start", "2100", "--end", "4100", "--stride", "5",
      "--accumulate-half-window", str(half),
      "-o", str(dets),
    ])
    results[f"classical_{tag}_vru"] = _eval(
      dets, out_dir / f"classical_{tag}_vru.json", "person,pedestrian,cyclist")
    results[f"classical_{tag}_all"] = _eval(
      dets, out_dir / f"classical_{tag}_all.json", "")

  for half, tag in ((0, "h0"), (5, "h5")):
    dets = out_dir / f"roadside_{tag}.jsonl"
    _run([
      py, str(_HERE / "roadside_batch.py"),
      "--frames-dir", str(_FRAMES),
      "--index", str(_FRAMES / "index.json"),
      "--ckpt", str(ckpt),
      "--start", "2100", "--end", "4100", "--stride", "5",
      "--accumulate-half-window", str(half),
      "--device", args.device,
      "-o", str(dets),
    ])
    results[f"roadside_{tag}_vru"] = _eval(
      dets, out_dir / f"roadside_{tag}_vru.json", "person,pedestrian,cyclist")
    results[f"roadside_{tag}_all"] = _eval(
      dets, out_dir / f"roadside_{tag}_all.json", "")

  refs = {
    "radarpillars_ft2_h0": _VID / "gnss_w2100_4100_ft2ep11_vru.json",
    "radarpillars_ft2_h5": _VID / "gnss_w2100_4100_ft2ep11_acc5_vru.json",
    "radarpillars_ovft2_h5": _VID / "gnss_w2100_4100_ovft2_acc5_vru.json",
  }
  for name, path in refs.items():
    if path.is_file():
      results[name] = json.loads(path.read_text())

  summary = {"window": [2100, 4100], "stride": 5, "methods": {}}
  for name, rep in results.items():
    summary["methods"][name] = {
      "recall_at_m": rep.get("recall_at_m"),
      "position_error_m_when_matched": rep.get("position_error_m_when_matched"),
      "frames_gnss_in_pc_range": rep.get("frames_gnss_in_pc_range"),
    }

  summary_path = out_dir / "phase1_summary.json"
  summary_path.write_text(json.dumps(summary, indent=2) + "\n")
  md = _render_md(summary)
  md_path = out_dir / "PHASE1_COMPARE.md"
  md_path.write_text(md)
  print(md)
  print(f"wrote {summary_path} and {md_path}", flush=True)
  return 0


def _render_md(summary: dict) -> str:
  lines = [
    "# Phase-1 VIDETEC baseline comparison",
    "",
    "Window **2100–4100**, stride **5**, max |Δt| **0.2 s**, VIDETEC UTM origin + sensor.",
    "",
    "Attribution: VIDETEC-2, Zenodo 17799385, CC BY 4.0.",
    "",
    "| Method | @1m | @2m | @3m | Match mean err (m) | Frames |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
  ]
  order = [
    "classical_h0_vru", "classical_h5_vru",
    "roadside_h0_vru", "roadside_h5_vru",
    "radarpillars_ft2_h0", "radarpillars_ft2_h5", "radarpillars_ovft2_h5",
    "classical_h0_all", "classical_h5_all",
    "roadside_h0_all", "roadside_h5_all",
  ]
  for name in order:
    m = summary["methods"].get(name)
    if not m:
      continue
    r = m.get("recall_at_m") or {}
    err = (m.get("position_error_m_when_matched") or {}).get("mean")
    frames = m.get("frames_gnss_in_pc_range")

    def fmt(x):
      return "—" if x is None else f"{100 * float(x):.1f}%"

    def fmt_e(x):
      return "—" if x is None else f"{float(x):.2f}"

    lines.append(
      f"| `{name}` | {fmt(r.get('1.0'))} | {fmt(r.get('2.0'))} | "
      f"{fmt(r.get('3.0'))} | {fmt_e(err)} | {frames} |"
    )
  lines.extend([
    "",
    "## Notes",
    "",
    "- **classical**: cluster + NN track; live demo person iff |doppler| ∈ [0.4, 3.0) m/s "
    "(faster detections stay vehicle).",
    "- **roadside**: PointNet-style semantic seg + class-aware cluster (keeps 1-pt objects);",
    "  weakly trained on GNSS (person radius 3 m); train 500–9000 excluding eval 2100–4100.",
    "- **radarpillars_***: prior P0 FT2 / OV-FT2 GNSS JSON (not re-run here).",
    "- `_all` rows use empty category filter (any object near GNSS).",
    "- `_vru` rows filter person/pedestrian/cyclist.",
    "",
  ])
  return "\n".join(lines) + "\n"


if __name__ == "__main__":
  raise SystemExit(main())
