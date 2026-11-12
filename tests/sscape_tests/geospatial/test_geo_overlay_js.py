# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scene_common.earth_lla import localFootprintCornersLLA

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent.parent.parent
_HARNESS = _TESTS_DIR / "overlay_harness.js"


def run_js(scenario, args):
  """Run harness via stdin/stdout JSON; return parsed result dict."""
  proc = subprocess.run(
    ["node", str(_HARNESS)],
    input=json.dumps({"scenario": scenario, "args": args}),
    capture_output=True,
    text=True,
    timeout=30,
  )
  if proc.returncode != 0:
    raise RuntimeError(f"Harness exit {proc.returncode}: {proc.stderr}")
  return json.loads(proc.stdout.strip())


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestCorners:
  """Test footprintCornersLLA parity with Python."""

  @pytest.mark.parametrize("lat,lng,h,w,ht", [
    (0, 0, 0, 100, 100),
    (37, -122, 90, 100, 50),
    (60, 0, 45, 200, 100),
    (-45, 150, 180, 75, 75),
    (45, 179.99, 33, 100, 150),
    (0, 0, 271, 100, 100),
    (37, -122, 359.9, 100, 100),
  ])
  def test_parity(self, lat, lng, h, w, ht):
    """JS footprintCornersLLA matches Python."""
    py = localFootprintCornersLLA(lat, lng, h, w, ht)
    res = run_js("corners", [lat, lng, h, w, ht])
    assert res["ok"], f"JS call failed: {res.get('error')}"
    js = res["result"]
    for i in range(4):
      assert abs(js[i]["lat"] - py[i][0]) < 1e-9
      assert abs(js[i]["lng"] - py[i][1]) < 1e-9

  @pytest.mark.parametrize("lat,lng,h,w,ht,case", [
    ("NaN", 0, 0, 100, 100, "NaN lat"),
    (0, "NaN", 0, 100, 100, "NaN lng"),
    (0, 0, "NaN", 100, 100, "NaN h"),
    (0, 0, 0, "NaN", 100, "NaN w"),
    (0, 0, 0, 100, "NaN", "NaN ht"),
    (91, 0, 0, 100, 100, "lat > 90"),
    (-91, 0, 0, 100, 100, "lat < -90"),
    (0, 181, 0, 100, 100, "lng > 180"),
    (0, -181, 0, 100, 100, "lng < -180"),
    (0, 0, 0, 0, 100, "w <= 0"),
    (0, 0, 0, -50, 100, "w < 0"),
    (0, 0, 0, 100, 0, "ht <= 0"),
    (0, 0, 0, 100, -50, "ht < 0"),
  ])
  def test_invalid(self, lat, lng, h, w, ht, case):
    """JS throws RangeError for invalid inputs."""
    res = run_js("corners", [lat, lng, h, w, ht])
    assert not res["ok"], f"Should have failed for {case}"
    assert res["error"].startswith("RangeError"), f"Expected RangeError for {case}, got {res['error']}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestMatrix:
  """Test overlayCssMatrix."""

  def test_axis_aligned(self):
    """NW=(10,20), NE=(110,20), SW=(10,70) -> [1,0,0,1,10,20]."""
    res = run_js("matrix", [{"x": 10, "y": 20}, {"x": 110, "y": 20}, {"x": 10, "y": 70}])
    assert res["ok"]
    m = res["result"]
    assert m["width"] == 100
    assert m["height"] == 50
    assert m["matrix"] == [1, 0, 0, 1, 10, 20]

  def test_rotated_90(self):
    """90° rotation: verify width/height and corner mapping."""
    res = run_js("matrix", [{"x": 50, "y": 10}, {"x": 50, "y": 110}, {"x": 0, "y": 10}])
    assert res["ok"]
    m = res["result"]
    assert abs(m["width"] - 100) < 1e-6
    assert abs(m["height"] - 50) < 1e-6

  def test_transformed(self):
    """Arbitrary rotated case; matrix maps unit corners to screen."""
    res = run_js("matrix", [{"x": 100, "y": 50}, {"x": 180, "y": 80}, {"x": 70, "y": 120}])
    assert res["ok"]
    m = res["result"]
    [a, b, c, d, e, f] = m["matrix"]
    w, h = m["width"], m["height"]
    assert abs(e - 100) < 1e-9 and abs(f - 50) < 1e-9  # nw
    assert abs(a * w + e - 180) < 1e-9 and abs(b * w + f - 80) < 1e-9  # ne
    assert abs(c * h + e - 70) < 1e-9 and abs(d * h + f - 120) < 1e-9  # sw

  def test_zero_width(self):
    """Zero width returns width=0 without NaN."""
    res = run_js("matrix", [{"x": 50, "y": 50}, {"x": 50, "y": 50}, {"x": 50, "y": 100}])
    assert res["ok"]
    m = res["result"]
    assert m["width"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestAbstract:
  """Test MapInterface abstract methods throw."""

  @pytest.mark.parametrize("method", ["setOverlay", "updateOverlay", "setOverlayOpacity", "removeOverlay", "pointToLatLng"])
  def test_throws(self, method):
    """Unimplemented abstract method throws."""
    res = run_js("abstract", method)
    assert res["ok"]
    assert res["threw"] == "Error"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestMapbox:
  """Test MapboxPlugin."""

  def test_set_overlay(self):
    """setOverlay creates source and layer."""
    corners = [
      {"lat": 10, "lng": 20}, {"lat": 10, "lng": 30},
      {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}
    ]
    res = run_js("mapbox", [["setOverlay", "test.jpg", corners, 0.5]])
    assert res["ok"]
    assert "addSource" in res["calls"]
    assert "addLayer" in res["calls"]
    assert "glb-overlay" in res["sources"]
    assert "glb-overlay" in res["layers"]

  def test_update_overlay(self):
    """updateOverlay calls setCoordinates."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    new = [{"lat": 15, "lng": 25}, {"lat": 15, "lng": 35}, {"lat": 25, "lng": 35}, {"lat": 25, "lng": 25}]
    res = run_js("mapbox", [["setOverlay", "test.jpg", corners, 0.5], ["updateOverlay", new]])
    assert res["ok"]

  def test_remove_overlay(self):
    """removeOverlay removes layer/source."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    res = run_js("mapbox", [["setOverlay", "test.jpg", corners, 0.5], ["removeOverlay"]])
    assert res["ok"]
    assert "glb-overlay" not in res["layers"]
    assert "glb-overlay" not in res["sources"]

  def test_remove_twice_safe(self):
    """removeOverlay twice is safe."""
    res = run_js("mapbox", [["removeOverlay"]])
    assert res["ok"]

  def test_set_twice_no_leak(self):
    """setOverlay twice leaves exactly one source/layer."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    res = run_js("mapbox", [["setOverlay", "test1.jpg", corners, 0.5], ["setOverlay", "test2.jpg", corners, 0.7]])
    assert res["ok"]
    r = res
    assert len(r["sources"]) == 1
    assert len(r["layers"]) == 1

  def test_point_to_lat_lng(self):
    """pointToLatLng converts pixel to lat/lng."""
    res = run_js("mapboxPointToLatLng", [[100, 200], [0, 0], [-50, 150]])
    assert res["ok"]
    assert len(res["points"]) == 3
    p0 = res["points"][0]
    assert abs(p0["lat"] - (40 - 200 * 0.001)) < 1e-9
    assert abs(p0["lng"] - (-100 + 100 * 0.001)) < 1e-9


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestGoogle:
  """Test GoogleMapsPlugin."""

  def test_set_overlay(self):
    """setOverlay creates overlay."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    res = run_js("google", {"steps": [["setOverlay", "test.jpg", corners, 0.5]]})
    assert res["ok"]
    assert res["hasOverlay"]

  def test_update_overlay(self):
    """updateOverlay redraws."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    new = [{"lat": 15, "lng": 25}, {"lat": 15, "lng": 35}, {"lat": 25, "lng": 35}, {"lat": 25, "lng": 25}]
    res = run_js("google", {"steps": [["setOverlay", "test.jpg", corners, 0.5], ["updateOverlay", new]]})
    assert res["ok"]

  def test_set_opacity(self):
    """setOverlayOpacity changes opacity."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    res = run_js("google", {"steps": [["setOverlay", "test.jpg", corners, 0.5], ["setOverlayOpacity", 0.8]]})
    assert res["ok"]

  def test_remove_overlay(self):
    """removeOverlay removes overlay."""
    corners = [{"lat": 10, "lng": 20}, {"lat": 10, "lng": 30}, {"lat": 20, "lng": 30}, {"lat": 20, "lng": 20}]
    res = run_js("google", {"steps": [["setOverlay", "test.jpg", corners, 0.5], ["removeOverlay"]]})
    assert res["ok"]
    assert not res["hasOverlay"]

  def test_remove_twice_safe(self):
    """removeOverlay twice is safe."""
    res = run_js("google", {"steps": [["removeOverlay"]]})
    assert res["ok"]
    assert not res["hasOverlay"]

  def test_point_to_lat_lng(self):
    """pointToLatLng converts pixel to lat/lng using projection."""
    res = run_js("googlePointToLatLng", {"steps": [[100, 200], [0, 0], [-50, 150]]})
    assert res["ok"]
    assert len(res["points"]) == 3
    p0 = res["points"][0]
    assert abs(p0["lat"] - (40 - 200 * 0.001)) < 1e-9
    assert abs(p0["lng"] - (-100 + 100 * 0.001)) < 1e-9

  def test_point_to_lat_lng_no_google(self):
    """pointToLatLng throws when no google.maps."""
    res = run_js("googlePointToLatLng", {"noGoogle": True, "steps": [[100, 200]]})
    assert not res["ok"] or len(res["points"]) == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_mapbox_dragrotate_false():
  """mapbox-plugin.js has dragRotate: false."""
  src = (_REPO_ROOT / "manager/src/manager/static/js/geospatial/mapbox-plugin.js").read_text()
  assert "dragRotate: false" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_google_heading_0():
  """google-maps-plugin.js has heading: 0."""
  src = (_REPO_ROOT / "manager/src/manager/static/js/geospatial/google-maps-plugin.js").read_text()
  assert "heading: 0" in src
