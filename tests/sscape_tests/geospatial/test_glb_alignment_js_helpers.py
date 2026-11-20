# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pure helpers exported by glb-alignment.js."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_HARNESS = _TESTS_DIR / "glb_align_pure_helpers_harness.js"


def run_js_helpers(test_name, args):
  """Run pure helpers harness via stdin/stdout JSON."""
  proc = subprocess.run(
    ["node", str(_HARNESS)],
    input=json.dumps({"test": test_name, "args": args}),
    capture_output=True,
    text=True,
    timeout=30,
  )
  if proc.returncode != 0:
    raise RuntimeError(f"Harness exit {proc.returncode}: {proc.stderr}")
  return json.loads(proc.stdout.strip())["result"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestGlbAlignmentPureHelpers:
  """Test pure helper functions from glb-alignment.js."""

  # JSON has no NaN/Infinity literals; the harness maps these sentinels to real values
  @pytest.mark.parametrize("value, expected", [
    (0.0, 0.0), (45.0, 45.0), (360.0, 359.9), (720.0, 359.9), (-10.0, 0.0),
    ("NaN", None), ("Infinity", None),
  ])
  def test_clamp_heading(self, value, expected):
    """Heading is clamped to [0, 359.9] (never wrapped to 0); non-finite values give null."""
    assert run_js_helpers("clampHeading", {"value": value}) == expected

  @pytest.mark.parametrize("start_lat, cur_lat, expected_lat", [
    (37.0, 37.1, 37.1),
    (80.0, 100.0, 85.0),
    (-80.0, -100.0, -85.0),
  ])
  def test_drag_anchor(self, start_lat, cur_lat, expected_lat):
    """Dragging applies the pointer delta, keeps the heading and clamps latitude to +/-85."""
    anchor = {"lat": start_lat, "lng": -121.0, "heading_deg": 45.0}
    grab = {"lat": start_lat, "lng": -121.0}
    cur = {"lat": cur_lat, "lng": -120.9}
    res = run_js_helpers("dragAnchor", {"anchor": anchor, "grab": grab, "cur": cur})
    assert res["lat"] == pytest.approx(expected_lat, abs=1e-6)
    assert res["lng"] == pytest.approx(-120.9, abs=1e-6)
    assert res["heading_deg"] == 45.0

  @pytest.mark.parametrize("anchor_lng, grab_lng, cur_lng, expected_lng", [
    (179.0, 179.0, 180.0, -180.0),   # sum lands exactly on +180, wraps to -180
    (179.5, 179.0, 180.0, -179.5),   # sum crosses +180 and wraps
    (-180.0, 0.0, 0.0, -180.0),      # lower bound stays at -180
    (179.9, 179.9, -179.9, -179.9),  # antimeridian drag: shortest delta is +0.2
    (-179.9, 179.9, -179.9, -179.7),  # antimeridian drag from the western side
    (0.0, 179.9, -179.9, 0.2),       # antimeridian drag away from the seam
  ])
  def test_drag_anchor_wraps_longitude(self, anchor_lng, grab_lng, cur_lng, expected_lng):
    """Longitude is wrapped into [-180, 180) and the drag uses the shortest signed delta."""
    anchor = {"lat": 37.0, "lng": anchor_lng, "heading_deg": 45.0}
    grab = {"lat": 37.0, "lng": grab_lng}
    cur = {"lat": 37.0, "lng": cur_lng}
    res = run_js_helpers("dragAnchor", {"anchor": anchor, "grab": grab, "cur": cur})
    assert -180.0 <= res["lng"] < 180.0
    assert res["lng"] == pytest.approx(expected_lng, abs=1e-9)

  @pytest.mark.parametrize("a, b, expected_km", [
    ({"lat": 37.0, "lng": -121.0}, {"lat": 37.0, "lng": -121.0}, 0.0),
    ({"lat": 0.0, "lng": 0.0}, {"lat": 1.0, "lng": 0.0}, 111.195),
    ({"lat": 0.0, "lng": 0.0}, {"lat": 0.0, "lng": 1.0}, 111.195),
    ({"lat": 60.0, "lng": 0.0}, {"lat": 60.0, "lng": 1.0}, 55.598),
    ({"lat": 0.0, "lng": 179.5}, {"lat": 0.0, "lng": -179.5}, 111.195),
  ])
  def test_distance_km(self, a, b, expected_km):
    """Great-circle distance is zero for equal points and crosses the antimeridian the short way."""
    assert run_js_helpers("distanceKm", {"a": a, "b": b}) == pytest.approx(expected_km, rel=1e-4, abs=1e-6)

  def test_overlay_opacity_constants_are_ordered_and_see_through(self):
    """The map shows through at rest (below 1) and fades further while moving."""
    op = run_js_helpers("opacityConstants", {})
    assert op == {"moving": 0.3, "staged": 0.7, "saved": 0.7}
    assert 0 < op["moving"] < op["staged"] <= op["saved"] < 1

  @pytest.mark.parametrize("pt, expected", [
    ((100, 50), 0),       # straight up on screen is north
    ((150, 100), 90),     # right is east
    ((100, 150), 180),    # down is south
    ((50, 100), 270),     # left is west
    ((150, 50), 45),
    ((50, 50), 315),      # wraps into [0, 360) instead of going negative
    ((100, 100), 0),      # pointer on the center
  ])
  def test_angle_from_pointer_is_clockwise_from_north(self, pt, expected):
    """Screen y grows downward, so 0 is up and the angle grows clockwise."""
    res = run_js_helpers("angleFromPointer", {"center": {"x": 100, "y": 100}, "pt": {"x": pt[0], "y": pt[1]}})
    assert res == pytest.approx(expected, abs=1e-9)

  @pytest.mark.parametrize("a, b, expected", [
    (350, 10, 20), (10, 350, -20), (0, 180, 180), (90, 90, 0), (0, 270, -90),
  ])
  def test_angle_delta_is_shortest_signed_rotation(self, a, b, expected):
    """The rotation between two angles goes the short way around north."""
    assert run_js_helpers("angleDelta", {"a": a, "b": b}) == pytest.approx(expected)

  @pytest.mark.parametrize("heading, expected", [
    (0, 0), (3, 0), (5, 0), (5.1, 5.1),      # light snap radius is 5 degrees
    (87, 90), (95, 90), (185, 180), (264, 264),
    (355, 0), (359.9, 0), (45, 45),          # snapping through north gives 0, not 360
  ])
  def test_snap_to_cardinal_is_light(self, heading, expected):
    """Headings within 5 degrees of 0, 90, 180 or 270 snap to it; others are left alone."""
    assert run_js_helpers("snapToCardinal", {"heading": heading}) == pytest.approx(expected)

  @pytest.mark.parametrize("raw, delta, fine, exp_raw, exp_heading", [
    (80, 10, False, 90, 90),
    (80, 7, False, 87, 90),            # shown snapped, but the raw heading keeps the 87
    (45, 40, True, 55, 55),            # fine rotation is a quarter of the pointer's rotation
    (88, 1, True, 88.25, 88.25),       # and never snaps
    (350, 20, False, 10, 10),          # wraps past north
    (5, -20, False, 345, 345),         # and below it
    (359.5, 1.8, True, 359.95, 359.9),  # clamped to 359.9 like the numeric input
  ])
  def test_drag_heading(self, raw, delta, fine, exp_raw, exp_heading):
    """A drag rotates by the pointer's rotation (a quarter of it with fine), snapping only when not fine."""
    res = run_js_helpers("dragHeading", {"raw": raw, "delta": delta, "fine": fine})
    assert res["raw"] == pytest.approx(exp_raw)
    assert res["heading"] == pytest.approx(exp_heading)

  @pytest.mark.parametrize("width, height, expected", [
    (10, 500, 3.75),      # tiny preview: 75% of the box beats the 30 px minimum
    (60, 100, 22.5),      # 30 px minimum would exceed 75% of the 60 px side
    (150, 400, 45),       # 30 percent of the shorter side
    (5000, 5000, 70),     # large preview: maximum radius
    ("NaN", 100, 30),
    ("Infinity", "Infinity", 30),
  ])
  def test_dial_radius_is_clamped(self, width, height, expected):
    """The ring radius follows the preview's pixel size within 30 to 70 px, and its diameter never exceeds 75% of the box."""
    assert run_js_helpers("dialRadius", {"width": width, "height": height}) == pytest.approx(expected)

  def test_build_overlay_corners_matches_footprint_size(self):
    """An unrotated 30 x 20 m footprint spans about 30 m east-west and 20 m north-south."""
    anchor = {"lat": 0.0, "lng": 0.0, "heading_deg": 0.0}
    corners = run_js_helpers(
      "buildOverlayCorners", {"anchor": anchor, "footprint": {"width": 30.0, "height": 20.0}}
    )
    assert len(corners) == 4
    lngs = [c["lng"] for c in corners]
    lats = [c["lat"] for c in corners]
    metres_per_degree = 111320.0
    assert (max(lngs) - min(lngs)) * metres_per_degree == pytest.approx(30.0, rel=0.02)
    assert (max(lats) - min(lats)) * metres_per_degree == pytest.approx(20.0, rel=0.02)
