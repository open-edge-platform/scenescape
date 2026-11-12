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
