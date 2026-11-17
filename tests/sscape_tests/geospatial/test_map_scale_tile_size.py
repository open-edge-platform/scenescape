# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from scene_common.earth_lla import footprintAnchorFromCornersLLA

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent.parent.parent
_MAP_INTERFACE = (
  _REPO_ROOT / "manager" / "src" / "manager" / "static" / "js" / "geospatial" / "map-interface.js"
)
# Edge of the static snapshot requested by the map plugins (generateSnapshot).
_SNAPSHOT_PX = 1280
_NODE_SCALE = """
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync(input.path, 'utf8') + ';this.MapInterface = MapInterface;', ctx);
const calc = ctx.MapInterface.prototype.calculateScale;
const out = input.cases.map(([lat, zoom, tile]) =>
  tile === undefined ? calc.call({}, lat, zoom) : calc.call({}, lat, zoom, tile));
console.log(JSON.stringify(out));
"""


def _js_scales(cases):
  """Evaluate MapInterface.calculateScale from map-interface.js for [lat, zoom(, tileSize)] cases."""
  proc = subprocess.run(
    ["node", "-e", _NODE_SCALE],
    input=json.dumps({"path": str(_MAP_INTERFACE), "cases": cases}),
    capture_output=True,
    text=True,
    timeout=30,
  )
  if proc.returncode != 0:
    raise RuntimeError(f"node exit {proc.returncode}: {proc.stderr}")
  return json.loads(proc.stdout.strip())


def _viewport_corners(lat, lng, zoom, tile_size):
  """Corners (SW, SE, NE, NW) of a square _SNAPSHOT_PX viewport in Web Mercator at tile_size."""
  world = tile_size * 2**zoom

  def world_y(lat_deg):
    lat_rad = math.radians(lat_deg)
    return (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * world

  def px_to_lat(py):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / world))))

  def px_to_lng(px):
    return px / world * 360 - 180

  cx = (lng + 180) / 360 * world
  cy = world_y(lat)
  half = _SNAPSHOT_PX / 2
  left, right = cx - half, cx + half
  top, bottom = cy - half, cy + half
  return [
    [px_to_lat(bottom), px_to_lng(left), 0.0],
    [px_to_lat(bottom), px_to_lng(right), 0.0],
    [px_to_lat(top), px_to_lng(right), 0.0],
    [px_to_lat(top), px_to_lng(left), 0.0],
  ]


def _extent_ratios(lat, zoom, tile_size, scale):
  """Corner extent in metres times scale, divided by the snapshot edge in px. 1.0 is consistent."""
  _, _, _, width_m, height_m = footprintAnchorFromCornersLLA(
    _viewport_corners(lat, -122.0, zoom, tile_size)
  )
  return width_m * scale / _SNAPSHOT_PX, height_m * scale / _SNAPSHOT_PX


_LAT_ZOOM = [(0.0, 16), (37.38, 16), (60.0, 12), (37.38, 19)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestMapScaleTileSize:
  def test_tile_size_scales_pixels_per_metre_linearly(self):
    default_scale, scale_256, scale_512 = _js_scales(
      [[37.38, 16], [37.38, 16, 256], [37.38, 16, 512]]
    )
    assert default_scale == pytest.approx(scale_256)
    assert scale_512 == pytest.approx(2 * scale_256)

  @pytest.mark.parametrize("lat, zoom", _LAT_ZOOM)
  def test_mapbox_512_scale_matches_snapshot_extent(self, lat, zoom):
    (scale,) = _js_scales([[lat, zoom, 512]])
    width_ratio, height_ratio = _extent_ratios(lat, zoom, 512, scale)
    assert width_ratio == pytest.approx(1.0, rel=0.02)
    assert height_ratio == pytest.approx(1.0, rel=0.02)

  @pytest.mark.parametrize("lat, zoom", _LAT_ZOOM)
  def test_google_default_256_scale_matches_snapshot_extent(self, lat, zoom):
    (scale,) = _js_scales([[lat, zoom]])
    width_ratio, height_ratio = _extent_ratios(lat, zoom, 256, scale)
    assert width_ratio == pytest.approx(1.0, rel=0.02)
    assert height_ratio == pytest.approx(1.0, rel=0.02)

  @pytest.mark.parametrize("lat, zoom", _LAT_ZOOM)
  def test_mapbox_with_256_scale_is_half_the_snapshot_extent(self, lat, zoom):
    # Negative control: the pre-fix Mapbox scale (256 px world) is off by 2x.
    (scale,) = _js_scales([[lat, zoom, 256]])
    width_ratio, height_ratio = _extent_ratios(lat, zoom, 512, scale)
    assert width_ratio == pytest.approx(0.5, rel=0.02)
    assert height_ratio == pytest.approx(0.5, rel=0.02)
