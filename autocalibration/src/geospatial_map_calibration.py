# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera calibration against a metric top-down (geospatial / ortho) map.

Productized from the RGB forward-BEV spike (tools/map_autocalib_spike/p2_rich_yaw.py):

  1. Estimate camera pitch from a ground-plane vanishing point.
  2. Build yaw hypotheses from the map's dominant (Manhattan) edge directions,
     or from an operator heading prior when one is given.
  3. For each (yaw, pitch, height) hypothesis, warp the camera frame into a
     forward bird's-eye view (BEV) and correlate it (Lab NCC) against the map
     sampled in the same frame over a grid of camera XY positions.
  4. Gate: if the best heading has a near-tied rival ~90 degrees away, report
     that a prior (map click and/or heading) is needed instead of guessing.

World frame follows SceneScape 2D maps: x = px / scale, y = (H - py) / scale,
z up. Poses are world-from-camera with an OpenCV camera (x right, y down,
z forward).
"""

import math
import os
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

RASTER_MAP_EXTENSIONS = (".png", ".jpg", ".jpeg")

DEFAULT_HEIGHTS_M = (5.0, 6.5, 8.0)
MAX_HEIGHT_M = 500.0
PITCH_FALLBACK_DEG = 10.0
PITCH_OFFSETS_DEG = (-2.0, 2.0)
PITCH_SEARCH_RANGE_DEG = (4.0, 20.0)
PITCH_VP_RANGE_DEG = (3.0, 25.0)

BEV_RES_M = 0.5
BEV_NEAR_M = 6.0
BEV_AHEAD_M = 55.0
BEV_HALF_LAT_M = 28.0
MIN_BEV_COVERAGE = 0.05
MIN_MAP_COVERAGE = 0.2
MIN_MASK_FRACTION = 0.1
MIN_MASK_PIXELS = 80
VALID_PIXEL_LEVEL = 8

SEARCH_STEP_M = 6.0
MAX_SEARCH_POINTS = 600
REFINE_STEP_M = 2.0
PRIOR_RADIUS_M = 12.0
HEADING_WINDOW_DEG = 20.0
HEADING_STEP_DEG = 5.0
MAX_YAW_CANDIDATES = 8

DISTINCT_YAW_DEG = 10.0
ORTHO_GAP_DEG = 70.0
AMBIGUITY_SCORE_RATIO = 0.9
MIN_CONFIDENT_SCORE = 0.1
NUM_TOP_CANDIDATES = 6

CORRESPONDENCE_COLS = (0.2, 0.5, 0.8)
CORRESPONDENCE_ROWS = (0.6, 0.75, 0.9)
MAX_CORRESPONDENCE_RANGE_M = 150.0


@dataclass
class GeoMapPrior:
  """Optional operator hints. Any subset may be provided."""
  map_point: tuple = None   # camera ground position (x, y) in scene metres
  heading_deg: float = None  # optical-axis heading, 0 along +X, CCW
  height_m: float = None    # camera height above ground

  @classmethod
  def from_request(cls, prior):
    """Build from the REST payload ({mapPoint, heading, height}); None if empty."""
    if not prior:
      return None
    map_point = prior.get("mapPoint")
    return cls(
      map_point=None if map_point is None else (float(map_point[0]), float(map_point[1])),
      heading_deg=None if prior.get("heading") is None else float(prior["heading"]),
      height_m=None if prior.get("height") is None else float(prior["height"]),
    )


def is_raster_map(map_path):
  return bool(map_path) and os.path.splitext(str(map_path))[1].lower() in RASTER_MAP_EXTENSIONS


def angle_diff_deg(a, b):
  return abs(((a - b + 180.0) % 360.0) - 180.0)


def pose_from_look(cx, cy, height, yaw_deg, pitch_deg):
  """World-from-camera pose for a camera at (cx, cy, height) looking along yaw, tilted down by pitch."""
  if height <= 0:
    raise ValueError("camera height must be above ground (z > 0)")
  yaw = math.radians(yaw_deg)
  pitch = math.radians(pitch_deg)
  look = np.array([
    math.cos(pitch) * math.cos(yaw),
    math.cos(pitch) * math.sin(yaw),
    -math.sin(pitch),
  ])
  right = np.cross(look, np.array([0.0, 0.0, 1.0]))
  norm = np.linalg.norm(right)
  if norm < 1e-8:
    right = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    norm = 1.0
  right = right / norm
  down = np.cross(look, right)
  down = down / np.linalg.norm(down)
  pose = np.eye(4)
  pose[:3, :3] = np.column_stack([right, down, look])
  pose[:3, 3] = [cx, cy, height]
  return pose


def image_from_ground_homography(pose, K):
  """3x3 homography mapping ground metres [x, y, 1] to image pixels."""
  cam_from_world = np.linalg.inv(pose)
  r_cw = cam_from_world[:3, :3]
  t_cw = cam_from_world[:3, 3]
  return K @ np.column_stack([r_cw[:, 0], r_cw[:, 1], t_cw])


def _lab_float(bgr):
  lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
  lab[:, :, 0] /= 255.0
  lab[:, :, 1:] = (lab[:, :, 1:] - 128.0) / 128.0
  return lab


def _valid_pixels(bgr):
  return (cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) > VALID_PIXEL_LEVEL).astype(np.float32)


def _masked_ncc(a, b, mask):
  """Mean per-channel NCC over a shared mask; None when support is too small."""
  if int(mask.sum()) < MIN_MASK_PIXELS:
    return None
  aa = a[mask]
  bb = b[mask]
  aa = aa - aa.mean(axis=0)
  bb = bb - bb.mean(axis=0)
  num = (aa * bb).sum(axis=0)
  den = np.sqrt((aa * aa).sum(axis=0) * (bb * bb).sum(axis=0)) + 1e-6
  return float(np.mean(num / den))


def _structure_image(bgr):
  L = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0]
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
  tophat = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, kernel)
  marking = cv2.normalize(tophat, None, 0, 1, cv2.NORM_MINMAX, dtype=cv2.CV_32F)
  edges = cv2.Canny(cv2.GaussianBlur(L, (5, 5), 0), 50, 130).astype(np.float32) / 255.0
  return cv2.GaussianBlur(np.clip(0.7 * marking + 0.3 * edges, 0, 1), (5, 5), 0)


def map_manhattan_angles(map_bgr, scale, n_peaks=2):
  """Dominant edge orientations (deg in [0, 180)) of the map at BEV resolution."""
  struct = _structure_image(map_bgr)
  cols = max(8, int(np.ceil(struct.shape[1] / scale / BEV_RES_M)))
  rows = max(8, int(np.ceil(struct.shape[0] / scale / BEV_RES_M)))
  grid = cv2.resize(struct, (cols, rows), interpolation=cv2.INTER_AREA)
  gx = cv2.Sobel(grid, cv2.CV_32F, 1, 0, ksize=3)
  gy = cv2.Sobel(grid, cv2.CV_32F, 0, 1, ksize=3)
  mag = np.sqrt(gx * gx + gy * gy)
  edge = ((np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0 + 90.0) % 180.0
  strong = mag > np.percentile(mag, 70)
  if strong.sum() < 100:
    return [0.0, 90.0]
  hist, bins = np.histogram(edge[strong], bins=36, range=(0, 180), weights=mag[strong])
  hist = hist.astype(np.float64)
  hist = (hist + np.roll(hist, 1) + np.roll(hist, -1)) / 3.0
  peaks = []
  for _ in range(n_peaks):
    i = int(np.argmax(hist))
    peaks.append(float(bins[i] + 2.5))
    for k in range(-2, 3):
      hist[(i + k) % len(hist)] = 0.0
  return peaks


def yaw_candidates_from_manhattan(map_angles):
  """Absolute headings along / against / across each dominant map direction."""
  bases = []
  for a in map_angles:
    bases.extend([a % 360.0, (a + 180.0) % 360.0])
  for a in list(bases):
    bases.append((a + 90.0) % 360.0)
  uniq = []
  for a in bases:
    if not any(angle_diff_deg(a, u) < 5.0 for u in uniq):
      uniq.append(a % 360.0)
  return uniq[:MAX_YAW_CANDIDATES] or [0.0, 90.0, 180.0, 270.0]


def _detect_lines(gray):
  """Line segments as (x1, y1, x2, y2). Prefer LSD; fall back to Hough."""
  if hasattr(cv2, "createLineSegmentDetector"):
    try:
      segs, *_ = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)
      if segs is not None and len(segs):
        return segs.reshape(-1, 4).astype(np.float64)
    except cv2.error:
      pass
  edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
  lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=40, maxLineGap=10)
  if lines is None:
    return np.zeros((0, 4), np.float64)
  return lines.reshape(-1, 4).astype(np.float64)


def estimate_vanishing_point(frame, max_segs=250):
  """RANSAC vanishing point from line segments in the lower (ground) part of the frame."""
  h = frame.shape[0]
  y_off = int(0.25 * h)
  segs = _detect_lines(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[y_off:, :])
  if len(segs) < 4:
    return None
  segs = segs.copy()
  segs[:, [1, 3]] += y_off
  d = segs[:, 2:] - segs[:, :2]
  lengths = np.linalg.norm(d, axis=1)
  ok = lengths > 1e-3
  segs, d, lengths = segs[ok], d[ok], lengths[ok]
  dirs = d / lengths[:, None]
  dirs[dirs[:, 0] < 0] *= -1
  mids = 0.5 * (segs[:, :2] + segs[:, 2:])
  ang = np.degrees(np.arctan2(np.abs(dirs[:, 1]), np.abs(dirs[:, 0]) + 1e-9))
  keep = (ang > 15.0) & (ang < 75.0) & (lengths > 30.0)
  mids, dirs, lengths = mids[keep], dirs[keep], lengths[keep]
  if len(mids) < 4:
    return None
  order = np.argsort(-lengths)[:max_segs]
  mids, dirs, lengths = mids[order], dirs[order], lengths[order]
  rng = np.random.default_rng(0)
  best_vp, best_score = None, -1.0
  for _ in range(400):
    i, j = rng.choice(len(mids), size=2, replace=False)
    mat = np.array([dirs[i], -dirs[j]]).T
    if abs(np.linalg.det(mat)) < 1e-6:
      continue
    t = np.linalg.solve(mat, mids[j] - mids[i])
    vp = mids[i] + t[0] * dirs[i]
    to_vp = vp[None, :] - mids
    to_n = np.linalg.norm(to_vp, axis=1)
    near = to_n > 20.0
    if near.sum() < 3:
      continue
    align = np.abs(((to_vp[near] / to_n[near, None]) * dirs[near]).sum(axis=1))
    score = float((align * lengths[near]).sum())
    if score > best_score:
      best_score, best_vp = score, vp
  return best_vp


def pitch_from_vp(vp, K):
  """Downward pitch (deg) from the VP's vertical offset; (pitch, from_vp)."""
  if vp is None:
    return PITCH_FALLBACK_DEG, False
  pitch = math.degrees(math.atan2(float(vp[1] - K[1, 2]), float(K[1, 1])))
  if not PITCH_VP_RANGE_DEG[0] <= pitch <= PITCH_VP_RANGE_DEG[1]:
    return PITCH_FALLBACK_DEG, False
  return float(pitch), True


class GeospatialMapCalibration:
  """Estimates camera pose from a single frame against a metric top-down map."""

  def __init__(self, map_bgr, scale):
    if map_bgr is None or map_bgr.ndim != 3 or map_bgr.shape[2] != 3:
      raise ValueError("Scene map must be a 3-channel image")
    if not scale or not math.isfinite(float(scale)) or float(scale) <= 0:
      raise ValueError("Scene map scale (pixels per meter) must be positive")
    self.scale = float(scale)
    self.map_h, self.map_w = map_bgr.shape[:2]
    self.extent_m = (self.map_w / self.scale, self.map_h / self.scale)
    self.map_lab = _lab_float(map_bgr)
    self.map_valid = _valid_pixels(map_bgr)
    self.map_angles = map_manhattan_angles(map_bgr, self.scale)
    us = np.arange(BEV_NEAR_M, BEV_AHEAD_M, BEV_RES_M)
    vs = np.arange(-BEV_HALF_LAT_M, BEV_HALF_LAT_M, BEV_RES_M)
    self._bev_u, self._bev_v = np.meshgrid(us, vs)

  @classmethod
  def from_file(cls, map_path, scale):
    if not is_raster_map(map_path):
      raise ValueError(f"Scene map must be one of {', '.join(RASTER_MAP_EXTENSIONS)}")
    if not os.path.isfile(map_path):
      raise FileNotFoundError(f"Scene map not found: {map_path}")
    map_bgr = cv2.imread(str(map_path), cv2.IMREAD_COLOR)
    if map_bgr is None:
      raise ValueError(f"Unable to read scene map: {map_path}")
    return cls(map_bgr, scale)

  def _bev_offsets(self, yaw_deg):
    """Ground offsets (metres) of every BEV cell from a camera at the origin."""
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    ox = self._bev_u * c - self._bev_v * s
    oy = self._bev_u * s + self._bev_v * c
    return ox, oy

  def _paint_bev(self, frame_lab, frame_valid, K, yaw, pitch, height, offsets):
    pose0 = pose_from_look(0.0, 0.0, height, yaw, pitch)
    H = image_from_ground_homography(pose0, K)
    ox, oy = offsets
    pts = np.stack([ox.ravel(), oy.ravel(), np.ones(ox.size)])
    proj = H @ pts
    depth = proj[2].reshape(ox.shape)
    with np.errstate(divide="ignore", invalid="ignore"):
      u = (proj[0] / proj[2]).reshape(ox.shape).astype(np.float32)
      v = (proj[1] / proj[2]).reshape(ox.shape).astype(np.float32)
    u[~np.isfinite(u)] = -1
    v[~np.isfinite(v)] = -1
    bev = cv2.remap(frame_lab, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    valid = cv2.remap(frame_valid, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    valid = (valid > 0.5) & (depth > 0.1)
    if valid.mean() < MIN_BEV_COVERAGE:
      return None
    return bev, valid

  def _score_at(self, bev, bev_valid, offsets_px, cx, cy):
    oxs, oys = offsets_px
    u = (cx * self.scale + oxs).astype(np.float32)
    v = (self.map_h - cy * self.scale + oys).astype(np.float32)
    crop_valid = cv2.remap(self.map_valid, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT) > 0.5
    if crop_valid.mean() < MIN_MAP_COVERAGE:
      return None
    mask = bev_valid & crop_valid
    if mask.mean() < MIN_MASK_FRACTION:
      return None
    crop = cv2.remap(self.map_lab, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return _masked_ncc(bev, crop, mask)

  def _search_xy(self, bev, bev_valid, offsets_px, centers):
    best = None
    for cx, cy in centers:
      score = self._score_at(bev, bev_valid, offsets_px, cx, cy)
      if score is not None and (best is None or score > best[0]):
        best = (score, (float(cx), float(cy)))
    return best

  def _grid(self, x0, x1, y0, y1, step):
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(self.extent_m[0], x1), min(self.extent_m[1], y1)
    if x1 < x0 or y1 < y0:
      return []
    xs = np.arange(x0, x1 + 1e-6, step)
    ys = np.arange(y0, y1 + 1e-6, step)
    return [(x, y) for x in xs for y in ys]

  def _coarse_centers(self, prior):
    if prior is not None and prior.map_point is not None:
      px, py = prior.map_point
      return self._grid(px - PRIOR_RADIUS_M, px + PRIOR_RADIUS_M,
                        py - PRIOR_RADIUS_M, py + PRIOR_RADIUS_M, REFINE_STEP_M), None
    area = self.extent_m[0] * self.extent_m[1]
    step = max(SEARCH_STEP_M, math.sqrt(area / MAX_SEARCH_POINTS))
    half = step / 2.0
    return self._grid(half, self.extent_m[0] - half, half, self.extent_m[1] - half, step), step

  def _hypotheses(self, frame, K, prior):
    pitch_est, pitch_from_vp_ok = pitch_from_vp(estimate_vanishing_point(frame), K)
    pitches = [pitch_est] + [pitch_est + d for d in PITCH_OFFSETS_DEG
                             if PITCH_SEARCH_RANGE_DEG[0] <= pitch_est + d <= PITCH_SEARCH_RANGE_DEG[1]]
    if prior is not None and prior.height_m is not None:
      heights = [prior.height_m]
    else:
      heights = list(DEFAULT_HEIGHTS_M)
    if prior is not None and prior.heading_deg is not None:
      offsets = np.arange(-HEADING_WINDOW_DEG, HEADING_WINDOW_DEG + 1e-6, HEADING_STEP_DEG)
      yaws = [float((prior.heading_deg + d) % 360.0) for d in offsets]
    else:
      yaws = yaw_candidates_from_manhattan(self.map_angles)
    return yaws, pitches, heights, pitch_est, pitch_from_vp_ok

  def calibrate(self, frame_bgr, intrinsics, prior=None):
    """Estimate the camera pose.

    @param   frame_bgr    Camera frame (BGR)
    @param   intrinsics   3x3 camera matrix
    @param   prior        Optional GeoMapPrior

    @return  dict with keys: needs_prior, reason, pose (4x4 or None), quaternion,
             translation, yaw_deg, pitch_deg, height_m, score, candidates,
             calibration_points_2d, calibration_points_3d
    """
    if frame_bgr is None or frame_bgr.ndim != 3:
      raise ValueError("Camera frame must be a 3-channel image")
    K = np.asarray(intrinsics, dtype=np.float64).reshape(3, 3)
    if not np.isfinite(K).all() or K[0, 0] <= 0 or K[1, 1] <= 0:
      raise ValueError("Camera intrinsics must have positive focal lengths")
    if prior is not None and prior.height_m is not None and not 0 < prior.height_m <= MAX_HEIGHT_M:
      raise ValueError(f"Prior height must be in (0, {MAX_HEIGHT_M}] metres")

    centers, coarse_step = self._coarse_centers(prior)
    if not centers:
      raise ValueError("Prior map point is outside the scene map")

    frame_lab = _lab_float(frame_bgr)
    frame_valid = _valid_pixels(frame_bgr)
    yaws, pitches, heights, pitch_est, pitch_ok = self._hypotheses(frame_bgr, K, prior)

    ranked = []
    for yaw in yaws:
      offsets = self._bev_offsets(yaw)
      offsets_px = (offsets[0] * self.scale, -offsets[1] * self.scale)
      for pitch in pitches:
        for height in heights:
          painted = self._paint_bev(frame_lab, frame_valid, K, yaw, pitch, height, offsets)
          if painted is None:
            continue
          bev, bev_valid = painted
          best = self._search_xy(bev, bev_valid, offsets_px, centers)
          if best is None:
            continue
          if coarse_step is not None:
            cx, cy = best[1]
            local = self._grid(cx - coarse_step, cx + coarse_step,
                               cy - coarse_step, cy + coarse_step, REFINE_STEP_M)
            fine = self._search_xy(bev, bev_valid, offsets_px, local)
            if fine is not None and fine[0] > best[0]:
              best = fine
          ranked.append({"score": best[0], "xy": best[1], "yaw": float(yaw),
                         "pitch": float(pitch), "height": float(height)})

    ranked.sort(key=lambda c: c["score"], reverse=True)
    top = []
    for cand in ranked:
      if not any(angle_diff_deg(cand["yaw"], t["yaw"]) < DISTINCT_YAW_DEG for t in top):
        top.append(cand)
      if len(top) >= NUM_TOP_CANDIDATES:
        break

    result = {
      "pitch_estimate_deg": pitch_est,
      "pitch_from_vanishing_point": pitch_ok,
      "candidates": [{"yaw_deg": t["yaw"], "score": t["score"], "map_point": list(t["xy"])} for t in top],
    }
    if not top:
      return {**result, "needs_prior": True, "pose": None,
              "reason": "No map region matched the camera view"}

    best = top[0]
    needs_prior, reason = self._confidence_gate(top, prior)
    pose = pose_from_look(best["xy"][0], best["xy"][1], best["height"], best["yaw"], best["pitch"])
    points_3d, points_2d = self._ground_correspondences(pose, K, frame_bgr.shape[1], frame_bgr.shape[0])
    return {
      **result,
      "needs_prior": needs_prior,
      "reason": reason,
      "pose": pose,
      "quaternion": Rotation.from_matrix(pose[:3, :3]).as_quat().tolist(),
      "translation": pose[:3, 3].tolist(),
      "yaw_deg": best["yaw"],
      "pitch_deg": best["pitch"],
      "height_m": best["height"],
      "score": best["score"],
      "calibration_points_3d": points_3d,
      "calibration_points_2d": points_2d,
    }

  def _confidence_gate(self, top, prior):
    best = top[0]
    if best["score"] < MIN_CONFIDENT_SCORE:
      return True, f"Weak correlation between camera view and map (score {best['score']:.2f})"
    if prior is not None and prior.heading_deg is not None:
      return False, "Heading prior provided"
    rival = next((c for c in top[1:] if angle_diff_deg(c["yaw"], best["yaw"]) >= ORTHO_GAP_DEG), None)
    if rival is None:
      return False, "Unique heading"
    ratio = rival["score"] / max(best["score"], 1e-6)
    if ratio >= AMBIGUITY_SCORE_RATIO:
      return True, f"Ambiguous heading: rival {rival['yaw']:.0f} deg scores {ratio:.2f} of best"
    return False, f"Best heading beats rival (score ratio {ratio:.2f})"

  @staticmethod
  def _ground_correspondences(pose, K, width, height):
    """Image grid points and their ground intersections under the solved pose."""
    K_inv = np.linalg.inv(K)
    origin = pose[:3, 3]
    points_3d, points_2d = [], []
    for fy in CORRESPONDENCE_ROWS:
      for fx in CORRESPONDENCE_COLS:
        u, v = fx * width, fy * height
        ray = pose[:3, :3] @ (K_inv @ np.array([u, v, 1.0]))
        if ray[2] >= -1e-6:
          continue
        ground = origin + (-origin[2] / ray[2]) * ray
        if np.linalg.norm(ground[:2] - origin[:2]) > MAX_CORRESPONDENCE_RANGE_M:
          continue
        points_3d.append([float(ground[0]), float(ground[1]), 0.0])
        points_2d.append([float(u), float(v)])
    return points_3d, points_2d
