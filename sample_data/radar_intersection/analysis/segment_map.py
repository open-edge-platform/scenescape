#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Segment the radar-intersection satellite map into road/crosswalk/sidewalk/veg.

Evaluation-only tool. Map classes are priors for metrics; they are not applied
as product filters (road persons may be real events).

Writes ``--out-npy`` (H×H uint8 class raster) and optional overlay JPEG.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

_RI_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = _RI_ROOT / "RadarIntersection.png"
SCALE_PX_PER_M = 9.142857
MAP_H = 1280
CLASSES = {0: "other", 1: "road", 2: "crosswalk", 3: "sidewalk", 4: "vegetation"}

# Hand-defined polygons in scene metres (satellite read-off). Crosswalk is the
# double-dashed north arm of Zeppelinstrasse; FOOTPATH is the shaded north
# footpath where camera-confirmed pedestrians walk.
CROSSWALKS = [
  [(16.5, 72.3), (47.5, 72.3), (47.5, 79.7), (16.5, 79.7)],
]
FOOTPATH = [
  (52, 72.6), (60, 71.4), (70, 69.9), (80, 68.2),
  (90, 66.4), (100, 64.6), (112, 62.5),
]
ROAD_FIX = [[(44.0, 44.0), (57.0, 44.0), (57.0, 52.0), (44.0, 52.0)]]


def _scene_to_px(x: float, y: float) -> tuple[int, int]:
  return int(round(x * SCALE_PX_PER_M)), int(round(MAP_H - y * SCALE_PX_PER_M))


def segment_map(map_path: Path) -> np.ndarray:
  """Return HxW uint8 class raster for the given satellite map image."""
  im = cv2.imread(str(map_path))
  if im is None:
    raise FileNotFoundError(map_path)
  if im.shape[0] != MAP_H or im.shape[1] != MAP_H:
    raise ValueError(f"expected {MAP_H}x{MAP_H} map, got {im.shape[:2]}")

  lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
  hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.float32)
  b, g, r = [im[..., i].astype(np.float32) for i in (0, 1, 2)]
  a = lab[..., 1]
  exg = 2 * g - r - b
  veg = ((a < 126.5) | (exg > 14)) & (hsv[..., 1] > 25)
  veg = cv2.morphologyEx(veg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
  veg = cv2.morphologyEx(veg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
  gray = ~veg

  L = lab[..., 0]
  th = cv2.morphologyEx(
    cv2.GaussianBlur(L, (0, 0), 0.8), cv2.MORPH_TOPHAT,
    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
  mark = ((th > 22) & gray & (hsv[..., 1] < 45)).astype(np.uint8)
  mark = cv2.morphologyEx(mark, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
  k = int(3.0 * SCALE_PX_PER_M) | 1
  support = (cv2.boxFilter(mark.astype(np.float32), -1, (k, k)) > 0.012).astype(np.uint8)
  support = cv2.morphologyEx(
    support, cv2.MORPH_CLOSE,
    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(4.5 * SCALE_PX_PER_M) | 1,) * 2))
  support = cv2.morphologyEx(
    support, cv2.MORPH_OPEN,
    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(2.5 * SCALE_PX_PER_M) | 1,) * 2))
  road = cv2.dilate(
    support,
    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(1.4 * SCALE_PX_PER_M) | 1,) * 2)
  ).astype(bool) & gray

  side = (gray & ~road).astype(np.uint8)
  side = cv2.morphologyEx(side, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
  n, lbl, stats, _ = cv2.connectedComponentsWithStats(side, connectivity=8)
  keep = np.zeros_like(side, dtype=bool)
  for i in range(1, n):
    if stats[i, cv2.CC_STAT_AREA] / (SCALE_PX_PER_M * SCALE_PX_PER_M) >= 6.0:
      keep |= lbl == i
  veg_near = cv2.dilate(
    veg.astype(np.uint8),
    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(2.4 * SCALE_PX_PER_M) | 1,) * 2)
  ).astype(bool)
  n2, lbl2, _, _ = cv2.connectedComponentsWithStats(keep.astype(np.uint8), connectivity=8)
  keep2 = np.zeros_like(keep)
  for i in range(1, n2):
    comp = lbl2 == i
    if (comp & veg_near).sum() / max(comp.sum(), 1) >= 0.08:
      keep2 |= comp
  side = keep2
  road = road | (keep & ~keep2)

  cross_poly = np.zeros((MAP_H, MAP_H), np.uint8)
  for poly in CROSSWALKS:
    pts = np.array([_scene_to_px(x, y) for x, y in poly], np.int32)
    cv2.fillPoly(cross_poly, [pts], 1)
  cross = cross_poly.astype(bool) & ~veg

  cls = np.zeros((MAP_H, MAP_H), np.uint8)
  cls[veg] = 4
  cls[side] = 3
  cls[road] = 1
  cls[cross] = 2
  fp = np.zeros((MAP_H, MAP_H), np.uint8)
  cv2.polylines(
    fp,
    [np.array([_scene_to_px(x, y) for x, y in FOOTPATH], np.int32)],
    False, 1, int(3.2 * SCALE_PX_PER_M))
  cls[(fp > 0) & (cls != 2)] = 3
  for poly in ROAD_FIX:
    pts = np.array([_scene_to_px(x, y) for x, y in poly], np.int32)
    tmp = np.zeros((MAP_H, MAP_H), np.uint8)
    cv2.fillPoly(tmp, [pts], 1)
    cls[(tmp > 0) & (cls == 3)] = 1
  return cls


def class_at(cls: np.ndarray, x: float, y: float) -> int:
  """Look up map class id at scene metres (x, y). Returns -1 if out of bounds."""
  px, py = _scene_to_px(x, y)
  if 0 <= px < MAP_H and 0 <= py < MAP_H:
    return int(cls[py, px])
  return -1


def class_name(cid: int) -> str:
  return CLASSES.get(cid, "out")


def write_overlay(im_path: Path, cls: np.ndarray, out_jpg: Path) -> None:
  im = cv2.imread(str(im_path))
  ov = im.copy()
  cols = {1: (170, 70, 70), 2: (255, 0, 255), 3: (0, 200, 255), 4: (0, 160, 0)}
  for c, col in cols.items():
    m = cls == c
    ov[m] = (0.45 * ov[m] + 0.55 * np.array(col)).astype(np.uint8)
  x0, x1, y0, y1 = 15, 120, 20, 115
  crop = ov[
    int(MAP_H - y1 * SCALE_PX_PER_M):int(MAP_H - y0 * SCALE_PX_PER_M),
    int(x0 * SCALE_PX_PER_M):int(x1 * SCALE_PX_PER_M)]
  out_jpg.parent.mkdir(parents=True, exist_ok=True)
  cv2.imwrite(str(out_jpg), crop)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
  ap.add_argument("--out-npy", type=Path, required=True)
  ap.add_argument("--out-overlay", type=Path, default=None)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  cls = segment_map(args.map)
  args.out_npy.parent.mkdir(parents=True, exist_ok=True)
  np.save(args.out_npy, cls)
  if args.out_overlay:
    write_overlay(args.map, cls, args.out_overlay)
  for c, name in CLASSES.items():
    print(f"{name} {100 * (cls == c).mean():.1f}%")


if __name__ == "__main__":
  main()
