#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Download VIDETEC-2 ``runs_vru`` (Zenodo) and stage time-aligned camera JPEGs.

Outputs under a **gitignored** staging tree (default ``camera_demo/``) for
``radar-data-init`` / ``multifilesrc``. No dataset bytes are stored in git —
only this tooling.

Typical use (from repo root, via ``make prepare-radar-camera``)::

  python3 sample_data/radar_intersection/stage_videtec_camera_demo.py \\
    --videtec-root sample_data/radar_intersection/VIDETEC-2 \\
    --out-dir sample_data/radar_intersection/camera_demo
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from videtec_zenodo import (  # noqa: E402
  download_zenodo_file,
  extract_tar_member,
)

# Oct-9 run_0 / densified pcd_bin_acc5 overlap (see ALIGN.json from prior runs).
DEFAULT_RADAR_START = 3270
DEFAULT_RADAR_STOP = 4100
DEFAULT_CAM = "s110_o_cam_8"
DEFAULT_RUN = "run_0"
# Scene sensor_id → VIDETEC camera archive name (s110 + s120 gantries).
DEFAULT_CAM_MAP = (
  "radar-cam1:s110_o_cam_8,"
  "radar-cam-n:s110_n_cam_8,"
  "radar-cam-w:s110_w_cam_8,"
  "radar-cam-s:s110_s_cam_8,"
  "radar-cam-s120-o:s120_o_cam_8,"
  "radar-cam-s120-n:s120_n_cam_8,"
  "radar-cam-s120-w:s120_w_cam_8,"
  "radar-cam-s120-s:s120_s_cam_8"
)


def _extract_member(outer: Path, member: str, dest_dir: Path) -> Path:
  return extract_tar_member(outer, member, dest_dir)


def _cam_timestamps(cam_tar: Path) -> list[int]:
  ts: list[int] = []
  with tarfile.open(cam_tar, "r:gz") as tf:
    for m in tf.getmembers():
      if not m.name.endswith(".jpg"):
        continue
      try:
        ts.append(int(Path(m.name).stem))
      except ValueError:
        continue
  ts.sort()
  if not ts:
    raise SystemExit(f"no jpg timestamps in {cam_tar}")
  return ts


def _extract_mp4(cam_tar: Path, work: Path) -> Path:
  work.mkdir(parents=True, exist_ok=True)
  with tarfile.open(cam_tar, "r:gz") as tf:
    for m in tf.getmembers():
      if m.isfile() and m.name.endswith(".mp4"):
        m.name = Path(m.name).name
        tf.extract(m, path=work)
        return work / Path(m.name).name
  raise SystemExit(f"no mp4 in {cam_tar}")


def _decode_mp4(mp4: Path, frames_dir: Path, ffmpeg_image: str) -> int:
  frames_dir.mkdir(parents=True, exist_ok=True)
  existing = sorted(frames_dir.glob("*.jpg"))
  if existing:
    print(f"[stage-cam] reusing {len(existing)} decoded frames in {frames_dir}", flush=True)
    return len(existing)
  # Prefer dockerized ffmpeg (same image as other Scenescape demos).
  cmd = [
    "docker", "run", "--rm",
    "-v", f"{mp4.parent.resolve()}:/in:ro",
    "-v", f"{frames_dir.resolve()}:/out",
    ffmpeg_image,
    "-y", "-i", f"/in/{mp4.name}",
    "-vsync", "0", "-q:v", "3",
    "/out/%06d.jpg",
  ]
  print(f"[stage-cam] decoding mp4 via {ffmpeg_image}", flush=True)
  subprocess.run(cmd, check=True)
  return len(list(frames_dir.glob("*.jpg")))


def _nearest(sorted_ts: list[int], t: int) -> int:
  lo, hi = 0, len(sorted_ts) - 1
  while lo < hi:
    mid = (lo + hi) // 2
    if sorted_ts[mid] < t:
      lo = mid + 1
    else:
      hi = mid
  cands = [sorted_ts[lo]]
  if lo > 0:
    cands.append(sorted_ts[lo - 1])
  return min(cands, key=lambda x: abs(x - t))


def _align(
  *,
  index_path: Path,
  cam_ts: list[int],
  mp4_frames: Path,
  out_image_dir: Path,
  radar_start: int,
  radar_stop: int,
) -> dict:
  index = json.loads(index_path.read_text(encoding="utf-8"))
  mp4_list = sorted(mp4_frames.glob("*.jpg"))
  if len(mp4_list) != len(cam_ts):
    raise SystemExit(
      f"mp4 frames ({len(mp4_list)}) != cam timestamps ({len(cam_ts)})")
  by_ts = {t: p for t, p in zip(cam_ts, mp4_list)}

  if out_image_dir.exists():
    for old in out_image_dir.glob("*.jpg"):
      old.unlink()
  out_image_dir.mkdir(parents=True, exist_ok=True)

  meta = []
  for e in index[radar_start:radar_stop + 1]:
    fi = int(e["frame_index"])
    t = int(e["timestamp"])
    cts = _nearest(cam_ts, t)
    shutil.copy2(by_ts[cts], out_image_dir / f"{fi:06d}.jpg")
    meta.append({"radar_frame": fi, "radar_ts": t, "cam_ts": cts, "dt_ms": abs(cts - t)})

  dts = [m["dt_ms"] for m in meta]
  cest = timezone(timedelta(hours=2))
  report = {
    "camera": DEFAULT_CAM,
    "run": DEFAULT_RUN,
    "source": "zenodo_runs_vru_mp4_paired_to_symlink_timestamps",
    "radar_start": radar_start,
    "radar_stop": radar_stop,
    "n": len(meta),
    "dt_ms_mean": round(statistics.mean(dts), 2) if dts else None,
    "dt_ms_p50": sorted(dts)[len(dts) // 2] if dts else None,
    "dt_ms_p95": sorted(dts)[int(0.95 * len(dts)) - 1] if dts else None,
    "dt_ms_max": max(dts) if dts else None,
    "cest_start": datetime.fromtimestamp(
      meta[0]["radar_ts"] / 1000, tz=cest).isoformat() if meta else None,
    "cest_stop": datetime.fromtimestamp(
      meta[-1]["radar_ts"] / 1000, tz=cest).isoformat() if meta else None,
    "license": "VIDETEC-2 CC BY 4.0 — https://zenodo.org/records/17799385",
  }
  return report


def _parse_cam_map(raw: str) -> list[tuple[str, str]]:
  """Parse ``sensor_id:videtec_id,...`` into ordered pairs."""
  pairs: list[tuple[str, str]] = []
  for part in raw.split(","):
    part = part.strip()
    if not part:
      continue
    if ":" not in part:
      raise SystemExit(f"bad --cameras entry {part!r}; want sensor_id:videtec_id")
    sensor_id, videtec_id = part.split(":", 1)
    pairs.append((sensor_id.strip(), videtec_id.strip()))
  if not pairs:
    raise SystemExit("empty --cameras map")
  return pairs


def _stage_one_camera(
  *,
  root: Path,
  download: Path,
  extract_dir: Path,
  index_path: Path,
  sensor_id: str,
  camera: str,
  run: str,
  out_image: Path,
  radar_start: int,
  radar_stop: int,
  ffmpeg_image: str,
  force: bool,
) -> dict:
  needed = radar_stop - radar_start + 1
  align_path = out_image.parent / f"ALIGN_{sensor_id}.json"
  if not force and align_path.is_file() and out_image.is_dir():
    n_jpg = sum(1 for _ in out_image.glob("*.jpg"))
    if n_jpg >= needed:
      print(
        f"[stage-cam] {sensor_id}: already staged ({n_jpg} JPEGs) — skip",
        flush=True,
      )
      return json.loads(align_path.read_text(encoding="utf-8"))

  member = f"runs_vru/{run}/{camera}.tar.gz"
  cam_tar = _extract_member(download, member, extract_dir / run)
  work = root / "camera_stage_work" / f"{run}_{camera}"
  cam_ts = _cam_timestamps(cam_tar)
  mp4 = _extract_mp4(cam_tar, work / "mp4")
  n_frames = _decode_mp4(mp4, work / "mp4frames", ffmpeg_image)
  if n_frames != len(cam_ts):
    raise SystemExit(
      f"{camera}: decoded {n_frames} frames but have {len(cam_ts)} timestamps")

  report = _align(
    index_path=index_path,
    cam_ts=cam_ts,
    mp4_frames=work / "mp4frames",
    out_image_dir=out_image,
    radar_start=radar_start,
    radar_stop=radar_stop,
  )
  report["camera"] = camera
  report["sensor_id"] = sensor_id
  report["run"] = run
  align_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
  print(
    f"[stage-cam] {sensor_id} ({camera}): wrote {report['n']} JPEGs → {out_image} "
    f"mean |dt|={report['dt_ms_mean']} ms",
    flush=True,
  )
  return report


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--videtec-root", type=Path,
    default=Path("sample_data/radar_intersection/VIDETEC-2"),
    help="Gitignored VIDETEC-2 root (download + converted frames)")
  ap.add_argument(
    "--out-dir", type=Path,
    default=Path("sample_data/radar_intersection/camera_demo"),
    help="Gitignored staging tree; JPEGs under <out-dir>/<sensor_id>/")
  ap.add_argument("--radar-start", type=int, default=DEFAULT_RADAR_START)
  ap.add_argument("--radar-stop", type=int, default=DEFAULT_RADAR_STOP)
  ap.add_argument("--run", default=DEFAULT_RUN)
  ap.add_argument(
    "--cameras", default=DEFAULT_CAM_MAP,
    help="Comma list sensor_id:videtec_cam (default: s110 o/n/w/s → radar-cam*)")
  ap.add_argument(
    "--camera", default="",
    help="Deprecated single VIDETEC cam; if set, stages as radar-cam1 only")
  ap.add_argument(
    "--ffmpeg-image",
    default="linuxserver/ffmpeg:version-8.1-cli")
  ap.add_argument(
    "--skip-download", action="store_true",
    help="Require existing runs_vru.tar.gz under videtec-root/download/")
  ap.add_argument(
    "--force", action="store_true",
    help="Re-stage even when camera_demo already has the JPEG slice")
  args = ap.parse_args()

  root: Path = args.videtec_root
  download = root / "download" / "runs_vru.tar.gz"
  index_path = root / "converted" / "frames" / "index.json"

  if args.camera:
    cam_map = [("radar-cam1", args.camera)]
  else:
    cam_map = _parse_cam_map(args.cameras)

  if not index_path.is_file():
    raise SystemExit(
      f"missing {index_path} — convert VIDETEC radar frames first "
      "(see run-radar-intersection-demo.md)")

  if args.skip_download:
    if not download.is_file():
      raise SystemExit(f"--skip-download but missing {download}")
  else:
    download_zenodo_file("runs_vru.tar.gz", download.parent, log_prefix="[stage-cam]")

  extract_dir = root / "runs_vru_extract"
  reports = []
  for sensor_id, camera in cam_map:
    out_image = args.out_dir / sensor_id
    reports.append(_stage_one_camera(
      root=root,
      download=download,
      extract_dir=extract_dir,
      index_path=index_path,
      sensor_id=sensor_id,
      camera=camera,
      run=args.run,
      out_image=out_image,
      radar_start=args.radar_start,
      radar_stop=args.radar_stop,
      ffmpeg_image=args.ffmpeg_image,
      force=args.force,
    ))

  # Legacy path used by older data-init mounts (single camera).
  legacy = args.out_dir / "infrastructure-side" / "image"
  primary = args.out_dir / cam_map[0][0]
  if primary.is_dir() and any(primary.glob("*.jpg")):
    legacy.mkdir(parents=True, exist_ok=True)
    # Refresh legacy symlink tree only when empty or forced.
    if args.force or not any(legacy.glob("*.jpg")):
      for old in legacy.glob("*.jpg"):
        old.unlink()
      for src in sorted(primary.glob("*.jpg")):
        dest = legacy / src.name
        if dest.exists() or dest.is_symlink():
          dest.unlink()
        dest.symlink_to(src.resolve())

  summary = {
    "cameras": [
      {"sensor_id": sid, "videtec_id": vid, "n": r.get("n")}
      for (sid, vid), r in zip(cam_map, reports)
    ],
    "radar_start": args.radar_start,
    "radar_stop": args.radar_stop,
    "run": args.run,
  }
  align_all = args.out_dir / "ALIGN.json"
  align_all.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  print(f"[stage-cam] summary → {align_all}", flush=True)
  print(
    f"[stage-cam] use RADAR_CAM_DATASET_DIR={args.out_dir} "
    f"CAM_START_INDEX={args.radar_start} CAM_STOP_INDEX={args.radar_stop} "
    f"CAM_SENSOR_IDS={','.join(s for s, _ in cam_map)}",
    flush=True,
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
