#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""First-deploy VIDETEC-2 fetch + convert for the radar-intersection demo.

Deterministic, idempotent host prep (gitignored under ``VIDETEC-2/``):

1. Download ``Radar_dataset.zip`` + ``gnss.zip`` from Zenodo 17799385 (CC BY 4.0)
2. Extract ``radar_dataset_51.h5`` / ``radar_dataset_52.h5`` (+ GNSS CSVs)
3. Convert to ``converted/`` (radar1) and ``converted_r52/`` (radar2):
   ``frames/``, ``frames_bin/``, ``pcd_bin/``

Camera JPEG staging stays in ``stage_videtec_camera_demo.py`` (needs
``converted/frames/index.json``). ``make demo-radar`` runs this target first.

Uses a local venv under ``VIDETEC-2/.venv`` (numpy + h5py) so the host does
not need system packages. Safe to re-run; skips work when outputs exist.

Example::

  python3 sample_data/radar_intersection/prepare/prepare_videtec_demo_data.py \\
    --root sample_data/radar_intersection/VIDETEC-2
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_RI_ROOT = _HERE.parent
_REPO_ROOT = _RI_ROOT.parents[1]
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from videtec_zenodo import (  # noqa: E402
  RADAR51_H5,
  RADAR52_H5,
  ZENODO_RECORD_URL,
  download_zenodo_file,
  extract_zip,
)

DEMO_READY = ".demo_ready"
DEMO_READY_VERSION = "1"
# Demo playback windows (must exist after convert).
RADAR1_CHECK_INDEX = 3270
RADAR2_CHECK_INDEX = 3098
MIN_BINS_HINT = 20_000


def _venv_python(root: Path) -> Path:
  return root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"


def _ensure_venv(root: Path) -> Path:
  """Create VIDETEC-2/.venv with numpy+h5py if missing."""
  py = _venv_python(root)
  marker = root / ".venv" / ".deps_ok"
  if py.is_file() and marker.is_file():
    return py
  print(f"[videtec-prep] creating venv at {root / '.venv'}", flush=True)
  root.mkdir(parents=True, exist_ok=True)
  venv.EnvBuilder(with_pip=True).create(root / ".venv")
  subprocess.check_call(
    [str(py), "-m", "pip", "install", "--upgrade", "pip"],
    stdout=subprocess.DEVNULL)
  subprocess.check_call(
    [str(py), "-m", "pip", "install", "--quiet", "numpy", "h5py"],
  )
  marker.write_text("numpy h5py\n")
  return py


def _unit_ready(out_dir: Path, check_index: int) -> bool:
  frames = out_dir / "frames"
  pcd = out_dir / "pcd_bin"
  index = frames / "index.json"
  sample = pcd / f"{check_index:06d}.bin"
  source = out_dir / "DATA_SOURCE.txt"
  if not index.is_file() or not sample.is_file():
    return False
  if source.is_file() and "real" not in source.read_text().lower():
    return False
  n_bins = sum(1 for _ in pcd.glob("*.bin"))
  return n_bins >= MIN_BINS_HINT


def _demo_ready(root: Path) -> bool:
  marker = root / DEMO_READY
  if not marker.is_file():
    return False
  if f"version={DEMO_READY_VERSION}" not in marker.read_text():
    return False
  return (
    _unit_ready(root / "converted", RADAR1_CHECK_INDEX)
    and _unit_ready(root / "converted_r52", RADAR2_CHECK_INDEX)
  )


def _write_ready(root: Path) -> None:
  c1 = root / "converted" / "pcd_bin"
  c2 = root / "converted_r52" / "pcd_bin"
  n1 = sum(1 for _ in c1.glob("*.bin"))
  n2 = sum(1 for _ in c2.glob("*.bin"))
  (root / DEMO_READY).write_text(
    f"version={DEMO_READY_VERSION}\n"
    f"zenodo={ZENODO_RECORD_URL}\n"
    f"radar51_bins={n1}\n"
    f"radar52_bins={n2}\n"
    "attribution=VIDETEC-2 CC BY 4.0\n"
  )
  print(f"[videtec-prep] wrote {root / DEMO_READY} (r51={n1} r52={n2})", flush=True)


def _pythonpath() -> str:
  parts = [str(_HERE), str(_REPO_ROOT / "radar")]
  existing = os.environ.get("PYTHONPATH", "")
  if existing:
    parts.append(existing)
  return os.pathsep.join(parts)


def _convert_unit(py: Path, hdf5: Path, out_dir: Path, check_index: int,
                  force: bool) -> None:
  if not force and _unit_ready(out_dir, check_index):
    print(f"[videtec-prep] skip convert {out_dir.name} (already ready)", flush=True)
    return
  print(f"[videtec-prep] converting {hdf5.name} → {out_dir}", flush=True)
  out_dir.mkdir(parents=True, exist_ok=True)
  cmd = [
    str(py),
    str(_HERE / "prepare_radar_demo_data.py"),
    "-o", str(out_dir),
    "--hdf5", str(hdf5),
    "--require-real",
  ]
  env = os.environ.copy()
  env["PYTHONPATH"] = _pythonpath()
  subprocess.check_call(cmd, env=env)
  if not _unit_ready(out_dir, check_index):
    raise SystemExit(
      f"[videtec-prep] convert incomplete for {out_dir}: "
      f"need pcd_bin/{check_index:06d}.bin and ≥{MIN_BINS_HINT} bins")


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--root", type=Path,
    default=_RI_ROOT / "VIDETEC-2",
    help="Gitignored VIDETEC-2 root (download + radar + converted*)")
  ap.add_argument(
    "--force", action="store_true",
    help="Re-download gates ignored; re-convert even if bins exist")
  ap.add_argument(
    "--skip-download", action="store_true",
    help="Require existing zips under root/download/")
  ap.add_argument(
    "--check-only", action="store_true",
    help="Exit 0 if demo data ready, else 1 (no download/convert)")
  return ap.parse_args(argv)


def main(argv=None) -> int:
  args = parse_args(argv)
  root = args.root.resolve()
  download_dir = root / "download"
  radar_dir = root / "radar"
  gnss_dir = root / "gnss"

  if args.check_only:
    ok = _demo_ready(root)
    print(f"[videtec-prep] check-only ready={ok} root={root}", flush=True)
    return 0 if ok else 1

  if not args.force and _demo_ready(root):
    print(f"[videtec-prep] already ready under {root} — skip", flush=True)
    return 0

  print(
    f"[videtec-prep] preparing VIDETEC-2 under {root}\n"
    f"[videtec-prep] attribution: VIDETEC-2, {ZENODO_RECORD_URL}, CC BY 4.0",
    flush=True)

  if args.skip_download:
    radar_zip = download_dir / "Radar_dataset.zip"
    gnss_zip = download_dir / "gnss.zip"
    if not radar_zip.is_file() or not gnss_zip.is_file():
      raise SystemExit(f"--skip-download but missing zips under {download_dir}")
  else:
    radar_zip = download_zenodo_file("Radar_dataset.zip", download_dir)
    gnss_zip = download_zenodo_file("gnss.zip", download_dir)

  extract_zip(
    radar_zip, radar_dir,
    members=[RADAR51_H5, RADAR52_H5], flatten=True)
  extract_zip(gnss_zip, gnss_dir, strip_prefix="gnss/")

  h51 = radar_dir / RADAR51_H5
  h52 = radar_dir / RADAR52_H5
  if not h51.is_file() or not h52.is_file():
    raise SystemExit(f"missing {h51.name} and/or {h52.name} under {radar_dir}")

  py = _ensure_venv(root)
  _convert_unit(py, h51, root / "converted", RADAR1_CHECK_INDEX, args.force)
  _convert_unit(py, h52, root / "converted_r52", RADAR2_CHECK_INDEX, args.force)
  _write_ready(root)
  print("[videtec-prep] done — next: make prepare-radar-camera (or make demo-radar)", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
