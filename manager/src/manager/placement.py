# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Planar placement of a child scene inside its parent's geospatial frame."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from manager.glb_state import footprint_to_lla
from scene_common.earth_lla import footprintAnchorFromCornersLLA, llaToFrameLocalXY
from scene_common.options import EULER

MAX_SCALE_ERROR = 0.01
MAX_RESIDUAL_M = 1.0
SOURCE_GEOREFERENCE = "georeference"
SOURCE_PLACED = "placed"


class PlacementError(ValueError):
  """A placement that cannot be computed or trusted; the message is safe to show."""


@dataclass(frozen=True)
class Placement:
  translation: tuple
  heading_deg: float
  provenance: dict


def frame_corners(scene):
  corners = scene.frameCornersLLA()
  if not corners:
    raise PlacementError(f"Scene '{scene.name}' has no geospatial frame")
  return np.asarray(corners, dtype=float)


def frame_hash(scene):
  """Hash of the scene's invariant frame, or None when it has no geospatial frame."""
  corners = scene.frameCornersLLA()
  if not corners:
    return None
  canonical = json.dumps(np.round(np.asarray(corners, dtype=float), 9).tolist())
  return hashlib.sha256(canonical.encode()).hexdigest()


def frame_extent(corners):
  """Width and height in metres of a frame, measured from its south-west corner."""
  _, _, _, width, height = footprintAnchorFromCornersLLA(corners)
  return width, height


def footprint_corners_lla(frame, x, y, width, height):
  """LLA corners of a rectangle given in the local metres of a frame."""
  footprint = np.array([
    [x, y, 0.0],
    [x + width, y, 0.0],
    [x + width, y + height, 0.0],
    [x, y + height, 0.0],
  ])
  return footprint_to_lla(frame, footprint)


def fit_planar_placement(child_xy, parent_xy):
  """Rigid 2D fit from child-frame points onto parent-frame points, with its quality checks.

  Returns (rotation, translation, scale_error, residual_m). Raises PlacementError when the
  two frames disagree on scale or on position.
  """
  src = np.asarray(child_xy, dtype=float)
  dst = np.asarray(parent_xy, dtype=float)
  src_c = src - src.mean(axis=0)
  dst_c = dst - dst.mean(axis=0)
  spread = float(np.sum(src_c ** 2))
  if spread < 1e-9:
    raise PlacementError("Child frame has no extent")

  U, S, Vt = np.linalg.svd(src_c.T @ dst_c)
  sign = 1.0 if np.linalg.det(Vt.T @ U.T) >= 0 else -1.0
  rotation = Vt.T @ np.diag([1.0, sign]) @ U.T
  translation = dst.mean(axis=0) - rotation @ src.mean(axis=0)

  scale_error = abs((S[0] + sign * S[1]) / spread - 1.0)
  residual_m = float(np.linalg.norm(src @ rotation.T + translation - dst, axis=1).max())
  if scale_error > MAX_SCALE_ERROR:
    raise PlacementError("Child and parent georeferences disagree on scale")
  if residual_m > MAX_RESIDUAL_M:
    raise PlacementError(
      f"Child and parent georeferences disagree by {residual_m:.2f} m; check the corner coordinates")
  return rotation, translation, scale_error, residual_m


def compute_placement(parent, child, source):
  """Place a child by matching the same geographic corners in both frames."""
  parent_frame = frame_corners(parent)
  child_frame = frame_corners(child)
  child_xy = [llaToFrameLocalXY(child_frame, lat, lng) for lat, lng, _ in child_frame]
  parent_xy = [llaToFrameLocalXY(parent_frame, lat, lng) for lat, lng, _ in child_frame]
  rotation, translation, scale_error, residual_m = fit_planar_placement(child_xy, parent_xy)
  return Placement(
    translation=(float(translation[0]), float(translation[1])),
    heading_deg=math.degrees(math.atan2(rotation[1, 0], rotation[0, 0])),
    provenance={
      "source": source,
      "parent_frame_hash": frame_hash(parent),
      "child_frame_hash": frame_hash(child),
      "scale_error": round(scale_error, 9),
      "residual_m": round(residual_m, 9),
      "computed_at": datetime.now(timezone.utc).isoformat(),
    },
  )


def apply_placement(link, placement):
  """Write a planar pose and its provenance onto a link; the caller saves it."""
  link.transform_type = EULER
  link.transform1, link.transform2, link.transform3 = placement.translation[0], placement.translation[1], 0.0
  link.transform4, link.transform5, link.transform6 = 0.0, 0.0, placement.heading_deg
  link.transform7, link.transform8, link.transform9 = 1.0, 1.0, 1.0
  link.placement = placement.provenance


def is_stale(link):
  """True when a georeference-placed link no longer matches either scene's current frame."""
  provenance = link.placement
  if not provenance or link.child is None:
    return False
  return (frame_hash(link.parent) != provenance.get("parent_frame_hash")
          or frame_hash(link.child) != provenance.get("child_frame_hash"))
