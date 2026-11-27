# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Planar child placement: fit accuracy, the pose convention used by the controller, and staleness."""

from types import SimpleNamespace

import numpy as np
import pytest

from manager import placement
from manager.glb_state import footprint_to_lla
from scene_common.transform import CameraPose, transform2DPoint
from tests.utils.geo_footprint import localFootprintCornersLLA

PARENT_CORNERS = localFootprintCornersLLA(
  center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0, width_m=100.0, height_m=80.0,
).tolist()
DEG_PER_M_LAT = 1.0 / 111320.0


class FakeScene:
  def __init__(self, name, corners):
    self.name = name
    self._corners = corners

  def frameCornersLLA(self):
    return self._corners


def _parent():
  return FakeScene("parent", PARENT_CORNERS)


def _rect_child(x, y, width, height):
  corners = placement.footprint_corners_lla(np.array(PARENT_CORNERS), x, y, width, height)
  return FakeScene("child", corners)


def _rotated_child(x0, y0, width, height, angle_deg):
  angle = np.deg2rad(angle_deg)
  c, s = np.cos(angle), np.sin(angle)
  footprint = np.array([
    [x0, y0, 0.0],
    [x0 + width * c, y0 + width * s, 0.0],
    [x0 + width * c - height * s, y0 + width * s + height * c, 0.0],
    [x0 - height * s, y0 + height * c, 0.0],
  ])
  return FakeScene("child", footprint_to_lla(np.array(PARENT_CORNERS), footprint))


def test_offset_child_recovers_translation_and_zero_heading():
  result = placement.compute_placement(_parent(), _rect_child(10.0, 20.0, 30.0, 40.0),
                                       placement.SOURCE_PLACED)

  assert result.translation == pytest.approx((10.0, 20.0), abs=0.05)
  assert result.heading_deg == pytest.approx(0.0, abs=0.05)
  assert result.provenance["residual_m"] < 0.05
  assert result.provenance["source"] == "placed"


def test_rotated_child_recovers_heading():
  child = _rotated_child(5.0, 10.0, 30.0, 20.0, 30.0)

  result = placement.compute_placement(_parent(), child, placement.SOURCE_GEOREFERENCE)

  assert result.heading_deg == pytest.approx(30.0, abs=0.05)
  assert result.translation == pytest.approx((5.0, 10.0), abs=0.05)


def test_planar_pose_maps_child_points_like_the_controller():
  """The stored EULER pose moves a child-local point to its parent-local position."""
  result = placement.compute_placement(_parent(), _rotated_child(5.0, 10.0, 30.0, 20.0, 30.0),
                                       placement.SOURCE_GEOREFERENCE)
  pose = CameraPose({
    "translation": [result.translation[0], result.translation[1], 0.0],
    "rotation": [0.0, 0.0, result.heading_deg],
    "scale": [1.0, 1.0, 1.0],
  }, None)

  mapped = transform2DPoint((15.0, 0.0), pose)

  radians = np.deg2rad(30.0)
  assert mapped[0] == pytest.approx(5.0 + 15.0 * np.cos(radians), abs=0.05)
  assert mapped[1] == pytest.approx(10.0 + 15.0 * np.sin(radians), abs=0.05)


def test_fit_rejects_scale_mismatch():
  src = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0]])

  with pytest.raises(placement.PlacementError, match="scale"):
    placement.fit_planar_placement(src, src * 1.2)


def test_fit_rejects_position_residual_above_limit():
  """A tangential outlier on a large frame leaves scale untouched, so only the residual guard fires."""
  src = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]])
  radius = src[2] - src.mean(axis=0)
  dst = src.copy()
  dst[2] += 3.0 * np.array([-radius[1], radius[0]]) / np.linalg.norm(radius)

  with pytest.raises(placement.PlacementError, match="disagree by"):
    placement.fit_planar_placement(src, dst)


def test_child_georeference_error_is_rejected():
  child = _rect_child(10.0, 20.0, 30.0, 40.0)
  corners = np.array(child.frameCornersLLA())
  corners[2, 0] += 25.0 * DEG_PER_M_LAT
  child = FakeScene("child", corners.tolist())

  with pytest.raises(placement.PlacementError, match="disagree"):
    placement.compute_placement(_parent(), child, placement.SOURCE_GEOREFERENCE)


def test_scene_without_frame_cannot_be_placed():
  with pytest.raises(placement.PlacementError, match="no geospatial frame"):
    placement.compute_placement(_parent(), FakeScene("bare", None), placement.SOURCE_GEOREFERENCE)


def test_frame_hash_is_none_without_frame_and_changes_with_corners():
  assert placement.frame_hash(FakeScene("bare", None)) is None
  moved = (np.array(PARENT_CORNERS) + [0.0, 1e-6, 0.0]).tolist()

  assert placement.frame_hash(_parent()) != placement.frame_hash(FakeScene("parent", moved))


def test_link_is_stale_only_after_a_frame_changes():
  parent = _parent()
  child = _rect_child(10.0, 20.0, 30.0, 40.0)
  result = placement.compute_placement(parent, child, placement.SOURCE_GEOREFERENCE)
  link = SimpleNamespace(placement=result.provenance, parent=parent, child=child)
  assert placement.is_stale(link) is False

  link.parent = FakeScene("parent", (np.array(PARENT_CORNERS) + [0.0, 1e-6, 0.0]).tolist())
  assert placement.is_stale(link) is True


def test_manual_link_is_never_stale():
  link = SimpleNamespace(placement=None, parent=_parent(), child=_rect_child(0.0, 0.0, 5.0, 5.0))

  assert placement.is_stale(link) is False


def test_apply_placement_writes_euler_fields_and_provenance():
  link = SimpleNamespace()
  result = placement.Placement(translation=(1.5, -2.0), heading_deg=30.0, provenance={"source": "placed"})

  placement.apply_placement(link, result)

  assert link.transform_type == "euler"
  assert (link.transform1, link.transform2, link.transform3) == (1.5, -2.0, 0.0)
  assert (link.transform4, link.transform5, link.transform6) == (0.0, 0.0, 30.0)
  assert (link.transform7, link.transform8, link.transform9) == (1.0, 1.0, 1.0)
  assert link.placement == {"source": "placed"}
