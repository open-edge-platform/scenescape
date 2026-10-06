#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Parse OSM XML and project ways into scene metres via map_corners_lla."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np


def scene_extent_m(map_w_px, map_h_px, scale):
  return map_w_px / scale, map_h_px / scale


def lla_to_scene_homography(map_corners_lla, width_m, height_m):
  """Perspective map from (lon, lat) -> scene metres using four map corners.

  map_corners_lla order: bottom-left, bottom-right, top-right, top-left
  (counterclockwise from lower-left), matching SceneScape convention.
  Scene metres: BL=(0,0), BR=(W,0), TR=(W,H), TL=(0,H).
  """
  if len(map_corners_lla) != 4:
    raise ValueError("need four map corners")
  src = np.array([
    [map_corners_lla[0][1], map_corners_lla[0][0]],  # lon, lat
    [map_corners_lla[1][1], map_corners_lla[1][0]],
    [map_corners_lla[2][1], map_corners_lla[2][0]],
    [map_corners_lla[3][1], map_corners_lla[3][0]],
  ], dtype=np.float64)
  dst = np.array([
    [0.0, 0.0],
    [width_m, 0.0],
    [width_m, height_m],
    [0.0, height_m],
  ], dtype=np.float64)
  H = cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32))
  return H


def project_lonlat(H, lon, lat):
  p = H @ np.array([lon, lat, 1.0], dtype=np.float64)
  return p[0] / p[2], p[1] / p[2]


def parse_osm_xml(path: Path):
  root = ET.parse(path).getroot()
  nodes = {}
  for e in root:
    if e.tag == "node":
      nodes[e.attrib["id"]] = (
        float(e.attrib["lat"]), float(e.attrib["lon"]))
  ways = []
  for e in root:
    if e.tag != "way":
      continue
    tags = {t.attrib["k"]: t.attrib["v"] for t in e if t.tag == "tag"}
    refs = [n.attrib["ref"] for n in e if n.tag == "nd"]
    coords = [nodes[r] for r in refs if r in nodes]
    if len(coords) < 2:
      continue
    ways.append({"tags": tags, "lla": coords})
  return ways


def ways_to_scene(ways, H):
  out = []
  for w in ways:
    xy = [project_lonlat(H, lon, lat) for lat, lon in w["lla"]]
    out.append({"tags": w["tags"], "xy": np.asarray(xy, dtype=np.float64)})
  return out


def classify_way(tags):
  if "building" in tags:
    return "building"
  hw = tags.get("highway")
  if tags.get("footway") == "crossing" or tags.get("crossing"):
    return "crossing"
  if hw in ("footway", "path", "steps", "pedestrian"):
    return "path"
  if hw:
    return "road"
  return None


def road_headings_deg(scene_ways, bin_deg=5.0):
  """Dominant undirected road headings in [0, 180)."""
  hist = {}
  for w in scene_ways:
    if classify_way(w["tags"]) != "road":
      continue
    xy = w["xy"]
    for i in range(len(xy) - 1):
      d = xy[i + 1] - xy[i]
      length = float(np.linalg.norm(d))
      if length < 2.0:
        continue
      ang = math.degrees(math.atan2(d[1], d[0])) % 180.0
      key = bin_deg * round(ang / bin_deg) % 180.0
      hist[key] = hist.get(key, 0.0) + length
  ranked = sorted(hist.items(), key=lambda kv: -kv[1])
  return ranked


def yaw_candidates_from_roads(scene_ways, step=10.0):
  """Yaw list aligned with road axes (both directions)."""
  ranked = road_headings_deg(scene_ways)
  if not ranked:
    return list(np.arange(0.0, 360.0, step))
  # Keep headings that cover most road length.
  total = sum(v for _, v in ranked) or 1.0
  keep = []
  acc = 0.0
  for ang, length in ranked:
    keep.append(ang)
    acc += length
    if acc / total >= 0.85 or len(keep) >= 4:
      break
  yaws = []
  for ang in keep:
    for base in (ang, ang + 180.0):
      for d in (-step, 0.0, step):
        yaws.append((base + d) % 360.0)
  # unique rounded
  uniq = sorted({round(y / step) * step % 360.0 for y in yaws})
  return uniq


def rasterize_osm(scene_ways, width_m, height_m, res, road_width_m=6.0):
  """Metre-grid raster: roads + paths + buildings. Values in [0, 1]."""
  cols = int(math.ceil(width_m / res))
  rows = int(math.ceil(height_m / res))
  img = np.zeros((rows, cols), np.float32)

  def draw_polyline(xy, thickness_m, value):
    if len(xy) < 2:
      return
    pts = []
    for x, y in xy:
      u = int(round(x / res))
      v = int(round((height_m - y) / res))
      pts.append([u, v])
    thick = max(1, int(round(thickness_m / res)))
    cv2.polylines(img, [np.asarray(pts, np.int32)], False, float(value), thick, cv2.LINE_AA)

  def draw_polygon(xy, value):
    if len(xy) < 3:
      return
    pts = []
    for x, y in xy:
      u = int(round(x / res))
      v = int(round((height_m - y) / res))
      pts.append([u, v])
    cv2.fillPoly(img, [np.asarray(pts, np.int32)], float(value))

  for w in scene_ways:
    kind = classify_way(w["tags"])
    if kind == "road":
      lanes = w["tags"].get("lanes")
      try:
        width = max(road_width_m, 3.5 * float(lanes))
      except (TypeError, ValueError):
        width = road_width_m
      draw_polyline(w["xy"], width, 1.0)
    elif kind == "path":
      draw_polyline(w["xy"], 2.0, 0.55)
    elif kind == "crossing":
      draw_polyline(w["xy"], 4.0, 0.85)
    elif kind == "building":
      draw_polygon(w["xy"], 0.7)

  img = cv2.GaussianBlur(img, (5, 5), 0)
  peak = float(img.max())
  if peak > 0:
    img /= peak
  return img


def load_scene_osm(osm_path, map_corners_lla, map_w_px, map_h_px, scale, res=0.4):
  width_m, height_m = scene_extent_m(map_w_px, map_h_px, scale)
  H = lla_to_scene_homography(map_corners_lla, width_m, height_m)
  ways = ways_to_scene(parse_osm_xml(osm_path), H)
  grid = rasterize_osm(ways, width_m, height_m, res)
  return {
    "ways": ways,
    "grid": grid,
    "width_m": width_m,
    "height_m": height_m,
    "res": res,
    "yaw_candidates": yaw_candidates_from_roads(ways),
    "road_headings": road_headings_deg(ways),
  }
