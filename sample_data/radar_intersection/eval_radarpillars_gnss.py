#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GNSS VRU accuracy gate for RadarPillars on real VIDETEC-2 frames.

Primary metrics (plan P0):
  - Time-align GNSS samples to each radar frame (report Δt histogram)
  - Recall @ distance (default 1 / 2 / 3 m): fraction of frames where a
    matching person/cyclist box exists near the GNSS position
  - Position error when matched: mean / median / P95 XY
  - Score distribution of matched vs unmatched detections

Inputs are offline artifacts (not live MQTT):
  - frames/index.json with per-frame ``timestamp`` (ms/us/ns; auto-scaled)
  - detections JSONL: one JSON object per frame with ``frame_index``,
    ``timestamp`` (optional), and ``objects`` list using radar-local
    ``translation`` [x,y,z] metres and ``confidence`` / ``category``
  - GNSS CSV (``vru-rtk-track.csv`` or per-run ``*_gps.csv``) with
    ``timestamp``, ``latitude``, ``longitude`` (plus optional altitude)

Pose: GNSS lat/lon → local ENU. Prefer the published VIDETEC UTM origin
(``--origin-utm-easting/northing`` or ``--videtec-origin``): UTM 32N
E=695310.500 m, N=5347376.094 m (X-east, Y-north). Fallback:
``--origin-lat/lon``, else the first GNSS sample. Optional ``--sensor``
(``frames/sensor.json``) maps ENU into radar-local XY before matching.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

_M_PER_DEG_LAT = 111_320.0

# Published VIDETEC-2 local Cartesian origin (Zenodo record description).
VIDETEC_UTM_ZONE = 32  # northern hemisphere → EPSG:32632
VIDETEC_UTM_EASTING_M = 695310.500
VIDETEC_UTM_NORTHING_M = 5347376.094


def _to_seconds(ts: np.ndarray) -> np.ndarray:
  ts = np.asarray(ts, dtype=np.float64)
  med = float(np.median(np.abs(ts))) if ts.size else 0.0
  if med > 1e17:  # ns
    return ts * 1e-9
  if med > 1e14:  # us
    return ts * 1e-6
  if med > 1e11:  # ms
    return ts * 1e-3
  return ts


def _utm_transformer(zone: int = VIDETEC_UTM_ZONE):
  try:
    from pyproj import Transformer
  except ImportError as exc:
    raise SystemExit("pyproj is required for UTM origin: pip install pyproj") from exc
  epsg = 32600 + int(zone)  # northern
  return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def load_gnss_csv(path: Path, origin_lat: float | None = None,
                  origin_lon: float | None = None,
                  origin_utm_easting: float | None = None,
                  origin_utm_northing: float | None = None,
                  utm_zone: int = VIDETEC_UTM_ZONE) -> np.ndarray:
  """Return structured array with t_s, x_m, y_m (local ENU / UTM-delta)."""
  raw = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="utf-8")
  if raw.dtype.names is None:
    raise SystemExit(f"GNSS CSV missing header: {path}")
  names = {n.lower(): n for n in raw.dtype.names}
  for need in ("timestamp", "latitude", "longitude"):
    if need not in names:
      raise SystemExit(f"GNSS CSV missing column {need}: {path}")
  t = _to_seconds(raw[names["timestamp"]].astype(np.float64))
  lat = raw[names["latitude"]].astype(np.float64)
  lon = raw[names["longitude"]].astype(np.float64)

  if origin_utm_easting is not None and origin_utm_northing is not None:
    to_utm = _utm_transformer(utm_zone)
    easting, northing = to_utm.transform(lon, lat)
    x = np.asarray(easting, dtype=np.float64) - float(origin_utm_easting)
    y = np.asarray(northing, dtype=np.float64) - float(origin_utm_northing)
  else:
    lat0 = float(origin_lat) if origin_lat is not None else float(lat[0])
    lon0 = float(origin_lon) if origin_lon is not None else float(lon[0])
    x = (lon - lon0) * _M_PER_DEG_LAT * math.cos(math.radians(lat0))
    y = (lat - lat0) * _M_PER_DEG_LAT

  out = np.zeros(len(t), dtype=[("t", "f8"), ("x", "f8"), ("y", "f8")])
  out["t"], out["x"], out["y"] = t, x, y
  return out


def world_to_radar_xy(x: np.ndarray, y: np.ndarray, sensor: dict) -> tuple[np.ndarray, np.ndarray]:
  """Map local ENU (x-east, y-north) into radar-local XY using /sensor attrs."""
  pos = sensor.get("position_xyz_m") or [0.0, 0.0, 0.0]
  yaw = math.radians(float(sensor.get("orientation_yaw_deg", 0.0)))
  dx = x - float(pos[0])
  dy = y - float(pos[1])
  c, s = math.cos(yaw), math.sin(yaw)
  rx = c * dx + s * dy
  ry = -s * dx + c * dy
  return rx, ry


def load_frame_index(path: Path) -> list[dict]:
  return json.loads(path.read_text())


def load_detections_jsonl(path: Path) -> dict[int, dict]:
  by_idx = {}
  with path.open() as fh:
    for line in fh:
      line = line.strip()
      if not line:
        continue
      obj = json.loads(line)
      by_idx[int(obj["frame_index"])] = obj
  return by_idx


def _xy_of_objects(objects: list, person_like: set[str]) -> tuple[np.ndarray, np.ndarray]:
  xs, scores = [], []
  for obj in objects:
    cat = str(obj.get("category", obj.get("label", ""))).lower()
    if person_like and cat and cat not in person_like:
      continue
    tr = obj.get("translation") or obj.get("center") or [None, None]
    if tr[0] is None:
      continue
    xs.append([float(tr[0]), float(tr[1])])
    scores.append(float(obj.get("confidence", obj.get("score", 0.0))))
  if not xs:
    return np.zeros((0, 2)), np.zeros((0,))
  return np.asarray(xs, dtype=np.float64), np.asarray(scores, dtype=np.float64)


def evaluate(index: list[dict], dets: dict[int, dict], gnss: np.ndarray,
             distances: list[float], person_like: set[str],
             max_dt_s: float, sensor: dict | None = None,
             pc_range: list[float] | None = None) -> dict:
  index_by = {int(e["frame_index"]): e for e in index if "timestamp" in e}
  # Only score frames that have inference output (subset JSONL is common).
  frame_ts = []
  for frame_index, det in sorted(dets.items()):
    entry = index_by.get(int(frame_index))
    if entry is None:
      # Fall back to timestamp embedded in the detection line.
      if "timestamp" not in det:
        continue
      frame_ts.append((int(frame_index), float(det["timestamp"])))
    else:
      frame_ts.append((int(frame_index), float(entry["timestamp"])))
  if not frame_ts:
    raise SystemExit("no overlapping frames between detections and index timestamps")

  idxs = np.array([i for i, _ in frame_ts], dtype=np.int64)
  ts = _to_seconds(np.array([t for _, t in frame_ts], dtype=np.float64))

  g_t = gnss["t"]
  dt = []
  matched_err = []
  matched_scores = []
  unmatched_scores = []
  recalls = {d: 0 for d in distances}
  usable = 0
  skipped_out_of_range = 0

  for frame_index, t in zip(idxs, ts):
    j = int(np.argmin(np.abs(g_t - t)))
    delta = float(g_t[j] - t)
    if abs(delta) > max_dt_s:
      continue
    gx, gy = float(gnss["x"][j]), float(gnss["y"][j])
    if sensor:
      rx, ry = world_to_radar_xy(np.array([gx]), np.array([gy]), sensor)
      gx, gy = float(rx[0]), float(ry[0])
    if pc_range is not None:
      x0, y0, _z0, x1, y1, _z1 = [float(v) for v in pc_range]
      if not (x0 <= gx <= x1 and y0 <= gy <= y1):
        skipped_out_of_range += 1
        continue
    usable += 1
    dt.append(delta)
    det = dets.get(int(frame_index), {})
    objs = det.get("objects", [])
    xy, scores = _xy_of_objects(objs, person_like)
    if xy.shape[0] == 0:
      continue
    dist = np.hypot(xy[:, 0] - gx, xy[:, 1] - gy)
    best = int(np.argmin(dist))
    best_d = float(dist[best])
    best_s = float(scores[best])
    hit_any = False
    for d in distances:
      if best_d <= d:
        recalls[d] += 1
        hit_any = True
    if hit_any:
      matched_err.append(best_d)
      matched_scores.append(best_s)
    else:
      unmatched_scores.append(best_s)

  def _pct(vals, q):
    if not vals:
      return None
    return float(np.percentile(vals, q))

  return {
    "frames_with_timestamp": len(frame_ts),
    "frames_within_max_dt": usable + skipped_out_of_range,
    "frames_gnss_in_pc_range": usable,
    "frames_skipped_out_of_pc_range": skipped_out_of_range,
    "pc_range_filter": pc_range,
    "max_dt_s": max_dt_s,
    "delta_t_s": {
      "mean": float(np.mean(dt)) if dt else None,
      "median": float(np.median(dt)) if dt else None,
      "p95_abs": _pct([abs(x) for x in dt], 95),
      "histogram_edges_s": [-1.0, -0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5, 1.0],
      "histogram_counts": (
        np.histogram(dt, bins=[-1.0, -0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5, 1.0])[0].tolist()
        if dt else []),
    },
    "recall_at_m": {str(d): (recalls[d] / usable if usable else None) for d in distances},
    "position_error_m_when_matched": {
      "count": len(matched_err),
      "mean": float(np.mean(matched_err)) if matched_err else None,
      "median": float(np.median(matched_err)) if matched_err else None,
      "p95": _pct(matched_err, 95),
    },
    "score_matched": {
      "mean": float(np.mean(matched_scores)) if matched_scores else None,
      "median": float(np.median(matched_scores)) if matched_scores else None,
    },
    "score_unmatched_best": {
      "mean": float(np.mean(unmatched_scores)) if unmatched_scores else None,
      "median": float(np.median(unmatched_scores)) if unmatched_scores else None,
    },
  }


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--index", type=Path, required=True, help="frames/index.json")
  ap.add_argument("--detections", type=Path, required=True, help="JSONL detections")
  ap.add_argument("--gnss", type=Path, required=True, help="vru-rtk-track.csv or per-run GPS CSV")
  ap.add_argument("--sensor", type=Path, default=None,
                  help="Optional frames/sensor.json to map GNSS ENU → radar-local")
  ap.add_argument("--videtec-origin", action="store_true",
                  help="Use published VIDETEC-2 UTM origin (E=695310.500, N=5347376.094)")
  ap.add_argument("--origin-utm-easting", type=float, default=None,
                  help="Local-frame origin UTM easting (metres)")
  ap.add_argument("--origin-utm-northing", type=float, default=None,
                  help="Local-frame origin UTM northing (metres)")
  ap.add_argument("--utm-zone", type=int, default=VIDETEC_UTM_ZONE,
                  help="UTM zone for GNSS→local (default 32N / EPSG:32632)")
  ap.add_argument("--origin-lat", type=float, default=None,
                  help="Local-frame origin latitude (approx; prefer UTM flags)")
  ap.add_argument("--origin-lon", type=float, default=None,
                  help="Local-frame origin longitude (approx; prefer UTM flags)")
  ap.add_argument("--distances", type=float, nargs="+", default=[1.0, 2.0, 3.0])
  ap.add_argument("--max-dt", type=float, default=0.15,
                  help="Max |Δt| seconds to associate GNSS↔radar frame")
  ap.add_argument("--categories", default="person,pedestrian,cyclist,bicycle",
                  help="Comma-separated category filter (empty = all)")
  ap.add_argument("--pc-range", type=float, nargs=6, default=None,
                  metavar=("X0", "Y0", "Z0", "X1", "Y1", "Z1"),
                  help="Only score frames whose GNSS (radar-local) lies in this box "
                       "(default VoD: 0 -25.6 -3 51.2 25.6 2 via --vod-pc-range)")
  ap.add_argument("--vod-pc-range", action="store_true",
                  help="Shortcut for VoD point_cloud_range filter")
  ap.add_argument("-o", "--output", type=Path, default=None, help="Write JSON report")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  cats = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
  index = load_frame_index(args.index)
  dets = load_detections_jsonl(args.detections)

  utm_e = args.origin_utm_easting
  utm_n = args.origin_utm_northing
  if args.videtec_origin:
    utm_e = VIDETEC_UTM_EASTING_M if utm_e is None else utm_e
    utm_n = VIDETEC_UTM_NORTHING_M if utm_n is None else utm_n

  gnss = load_gnss_csv(
    args.gnss,
    origin_lat=args.origin_lat,
    origin_lon=args.origin_lon,
    origin_utm_easting=utm_e,
    origin_utm_northing=utm_n,
    utm_zone=args.utm_zone,
  )
  sensor = json.loads(args.sensor.read_text()) if args.sensor else None
  pc_range = args.pc_range
  if args.vod_pc_range and pc_range is None:
    pc_range = [0.0, -25.6, -3.0, 51.2, 25.6, 2.0]
  report = evaluate(
    index, dets, gnss, args.distances, cats, args.max_dt,
    sensor=sensor, pc_range=pc_range)
  if utm_e is not None and utm_n is not None:
    report["origin_utm_easting_m"] = utm_e
    report["origin_utm_northing_m"] = utm_n
    report["utm_zone"] = args.utm_zone
  if args.origin_lat is not None:
    report["origin_lat"] = args.origin_lat
    report["origin_lon"] = args.origin_lon
  report["sensor_frame"] = bool(sensor)
  text = json.dumps(report, indent=2) + "\n"
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
  print(text)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
