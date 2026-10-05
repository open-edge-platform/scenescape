#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Metrics for radar detections vs camera pseudo-GT and satellite class map.

Reads radarpillars/classical/roadside JSONL (frame_index + objects[] with
translation/category/confidence in radar-local metres) and reports:

- person recall@3m vs camera persons (conf ≥ --cam-thr)
- map-class split (road / crosswalk / sidewalk / vegetation)
- plausible-on-footpath share (sidewalk + in pedestrian time windows)
- boxes per confirmed-pedestrian frame
- vehicle count at conf ≥ --veh-thr
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from segment_map import CLASSES, SCALE_PX_PER_M, class_at, class_name, segment_map

_RI_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = _RI_ROOT / "RadarIntersection.png"
DEFAULT_SCENE = _RI_ROOT / "RadarIntersection.json"

# Pedestrian windows observed on radar-cam1 for the 3270–4100 loop
# (padded beyond camera-visible frames so radar-only far detections count).
PED_WINDOWS = [(3230, 3490), (3760, 4020)]
FOOT_BAND = (0.0, 45.0, -1.5, 4.5)  # radar-local x0,x1,y0,y1


def _radar_to_scene_fn(scene_json: Path):
  scene = json.loads(scene_json.read_text())
  radar = scene["radars"][0]
  t = np.asarray(radar["translation"][:2], dtype=np.float64)
  yaw = math.radians(float(radar["rotation"][2]))
  c, s = math.cos(yaw), math.sin(yaw)
  rm = np.array([[c, -s], [s, c]])

  def to_scene(p):
    return rm @ np.asarray(p[:2], dtype=np.float64) + t

  return to_scene


def load_detections(path: Path) -> dict[int, list]:
  out: dict[int, list] = {}
  for line in path.open():
    j = json.loads(line)
    out[int(j["frame_index"])] = j.get("objects", [])
  return out


def load_camera_gt(path: Path, label: str, conf_thr: float) -> dict[int, list[np.ndarray]]:
  rows = json.loads(path.read_text())
  by: dict[int, list[np.ndarray]] = defaultdict(list)
  for r in rows:
    if r.get("label", "person") != label:
      continue
    if float(r["conf"]) < conf_thr:
      continue
    by[int(r["frame_index"])].append(np.asarray(r["radar_local"][:2], dtype=np.float64))
  return by


def in_ped_window(frame: int) -> bool:
  return any(a <= frame <= b for a, b in PED_WINDOWS)


def in_foot_band(x: float, y: float) -> bool:
  x0, x1, y0, y1 = FOOT_BAND
  return x0 <= x <= x1 and y0 <= y <= y1


def evaluate(
    dets: dict[int, list],
    cam_persons: dict[int, list[np.ndarray]],
    cam_vehicles: dict[int, list[np.ndarray]],
    cls: np.ndarray,
    to_scene,
    person_thr: float,
    vehicle_thr: float,
    radius_m: float,
) -> dict:
  n_frames = max(len(dets), 1)
  cls_count = Counter()
  person_tot = 0
  plausible = 0
  veh_tot = 0
  boxes_per_hit: list[int] = []

  for f, objs in dets.items():
    for o in objs:
      cat = o.get("category") or o.get("label") or ""
      conf = float(o.get("confidence", o.get("conf", 0)))
      if cat == "vehicle" and conf >= vehicle_thr:
        veh_tot += 1
      if cat != "person" or conf < person_thr:
        continue
      p = o["translation"]
      s = to_scene(p)
      cname = class_name(class_at(cls, float(s[0]), float(s[1])))
      cls_count[cname] += 1
      person_tot += 1
      if cname == "sidewalk" and in_ped_window(f) and in_foot_band(p[0], p[1]):
        plausible += 1

  hits = 0
  cam_frames = sorted(cam_persons)
  for f in cam_frames:
    ps = [
      o for o in dets.get(f, [])
      if (o.get("category") or o.get("label")) == "person"
      and float(o.get("confidence", o.get("conf", 0))) >= person_thr
    ]
    got = False
    n_boxes = 0
    for gt in cam_persons[f]:
      for o in ps:
        dd = float(np.linalg.norm(np.asarray(o["translation"][:2]) - gt))
        if dd <= radius_m:
          got = True
          n_boxes += 1
    hits += int(got)
    if got:
      boxes_per_hit.append(n_boxes)

  veh_hits = 0
  veh_frames = sorted(cam_vehicles)
  for f in veh_frames:
    vs = [
      o for o in dets.get(f, [])
      if (o.get("category") or o.get("label")) == "vehicle"
      and float(o.get("confidence", o.get("conf", 0))) >= vehicle_thr
    ]
    for gt in cam_vehicles[f]:
      if any(float(np.linalg.norm(np.asarray(o["translation"][:2]) - gt)) <= radius_m
             for o in vs):
        veh_hits += 1
        break

  def pct(n, d):
    return 100.0 * n / d if d else 0.0

  return {
    "n_det_frames": len(dets),
    "person_total": person_tot,
    "person_per_frame": person_tot / n_frames,
    "road_pct": pct(cls_count["road"] + cls_count["crosswalk"], person_tot),
    "sidewalk_pct": pct(cls_count["sidewalk"], person_tot),
    "veg_pct": pct(cls_count["vegetation"], person_tot),
    "plausible_pct": pct(plausible, person_tot),
    "person_recall": f"{hits}/{len(cam_frames)}",
    "person_recall_pct": pct(hits, len(cam_frames)),
    "boxes_per_hit_mean": float(np.mean(boxes_per_hit)) if boxes_per_hit else 0.0,
    "vehicle_total": veh_tot,
    "vehicle_recall": f"{veh_hits}/{len(veh_frames)}",
    "vehicle_recall_pct": pct(veh_hits, len(veh_frames)),
    "class_counts": dict(cls_count),
  }


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--dets", type=Path, required=True, help="Radar detections JSONL")
  ap.add_argument("--camera-gt", type=Path, required=True,
                  help="Projected camera detections JSON from project_camera_detections.py")
  ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
  ap.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
  ap.add_argument("--seg-npy", type=Path, default=None,
                  help="Optional precomputed class raster; built from --map if omitted")
  ap.add_argument("--person-thr", type=float, default=0.1)
  ap.add_argument("--vehicle-thr", type=float, default=0.3)
  ap.add_argument("--cam-thr", type=float, default=0.5)
  ap.add_argument("--radius-m", type=float, default=3.0)
  ap.add_argument("--name", default="")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  if args.seg_npy and args.seg_npy.is_file():
    cls = np.load(args.seg_npy)
  else:
    cls = segment_map(args.map)
  to_scene = _radar_to_scene_fn(args.scene)
  dets = load_detections(args.dets)
  cam_p = load_camera_gt(args.camera_gt, "person", args.cam_thr)
  cam_v = load_camera_gt(args.camera_gt, "vehicle", args.cam_thr)
  m = evaluate(
    dets, cam_p, cam_v, cls, to_scene,
    args.person_thr, args.vehicle_thr, args.radius_m)
  name = args.name or args.dets.stem
  print(
    f"{name:24s} thr={args.person_thr:.2f} | "
    f"{m['person_per_frame']:5.2f}/fr  road {m['road_pct']:4.0f}%  "
    f"veg {m['veg_pct']:4.0f}%  plaus {m['plausible_pct']:4.0f}% | "
    f"recall {m['person_recall']} ({m['person_recall_pct']:.0f}%)  "
    f"boxes/hit {m['boxes_per_hit_mean']:.2f} | "
    f"veh {m['vehicle_total']} recall {m['vehicle_recall']}")
  return m


if __name__ == "__main__":
  main()
