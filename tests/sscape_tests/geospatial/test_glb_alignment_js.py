# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scene_common.earth_lla import localFootprintCornersLLA

_TESTS_DIR = Path(__file__).resolve().parent
_HARNESS = _TESTS_DIR / "align_harness.js"


def run_js(scenario, args):
  """Run harness via stdin/stdout JSON."""
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
class TestGlbAlignment:
  """Test GLB alignment UI and helpers."""

  def test_visibility_non_geospatial(self):
    """Row hidden when not geospatial_map type."""
    res = run_js("align", {"mapType": "image_map", "center": ["37", "-122"], "steps": []})
    assert res["ok"]
    assert res["rowDisplay"] == "none"

  def test_file_disabled_empty_center(self):
    """File input disabled when center lat/lng empty."""
    res = run_js("align", {"mapType": "geospatial_map", "center": ["", ""], "steps": []})
    assert res["ok"]
    assert res["fileDisabled"] is True
    assert "map location" in res["hint"].lower()

  def test_file_enabled_with_center(self):
    """File input enabled when center set."""
    res = run_js("align", {"mapType": "geospatial_map", "center": ["37", "-122"], "steps": []})
    assert res["ok"]
    assert res["fileDisabled"] is False
    assert res["hint"] == ""

  def test_upload_success(self):
    """Successful GLB preview upload."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"]],
      },
    )
    assert res["ok"]
    assert res["controlsDisplay"] == ""
    assert len(res["fetches"]) == 2
    assert res["fetches"][1]["url"].endswith("geospatial-glb-preview")
    assert res["fetches"][1]["method"] == "POST"
    assert res["fetches"][1]["headers"]["X-CSRFToken"] == "tok"
    assert res["fetches"][1]["body"]["formData"][0][0] == "file"
    assert any("setOverlay" in str(c) for c in res["calls"])

  def test_upload_error(self):
    """Failed GLB preview upload displays error."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, {"status": 400, "body": {"error": "Invalid GLB"}}],
        "steps": [["upload"]],
      },
    )
    assert res["ok"]
    assert res["status"] == "Invalid GLB"
    assert res["controlsDisplay"] == "none"

  def test_drag_inside_prevents_pan(self):
    """Drag inside footprint prevents map pan and updates anchor."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["drag", [0, 0], [100, 100]]],
      },
    )
    assert res["ok"]
    assert res["events"][0]["prevented"] is True
    assert res["anchor"]["lat"] < 37
    assert res["anchor"]["lng"] > -122
    assert res["dirty"] is True

  def test_drag_outside_not_prevented(self):
    """Drag far outside footprint does not prevent pan."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["drag", [100000, 100000], [100100, 100100]]],
      },
    )
    assert res["ok"]
    assert res["events"][0]["prevented"] is False

  def test_heading_update(self):
    """Heading update changes anchor rotation."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["heading", "90"]],
      },
    )
    assert res["ok"]
    assert res["anchor"]["heading_deg"] == 90.0
    assert res["dirty"] is True

  def test_accept_saves_and_reloads(self):
    """Accept saves anchor and triggers reload."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    accept_resp = {
      "status": 200,
      "body": {"anchor": {"lat": 37, "lng": -122, "heading_deg": 0}, "footprint_m": {"width": 100, "height": 60}},
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp, accept_resp],
        "steps": [["upload"], ["accept"]],
      },
    )
    assert res["ok"]
    assert len(res["fetches"]) == 3
    assert res["fetches"][2]["url"].endswith("geospatial-glb")
    assert res["fetches"][2]["method"] == "POST"
    body = res["fetches"][2]["body"]
    assert body["token"] == "tok1"
    assert body["anchor"]["lat"] == 37
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_accept_with_confirm_required(self):
    """Accept with existing content requires confirmation."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {"cameras": 2, "regions": 0, "sensors": 0},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "confirm": False,
        "steps": [["upload"], ["accept"]],
      },
    )
    assert res["ok"]
    assert len(res["fetches"]) == 2

  def test_reset_restores_original(self):
    """Reset restores anchor to original state."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["heading", "90"], ["reset"]],
      },
    )
    assert res["ok"]
    assert res["anchor"]["heading_deg"] == 0.0
    assert res["dirty"] is False

  def test_cancel_removes_overlay(self):
    """Cancel removes overlay and hides controls."""
    preview_resp = {
      "status": 200,
      "body": {
        "token": "tok1",
        "preview_url": "/img.png",
        "footprint_m": {"width": 100, "height": 60},
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "existing_content": {},
      },
    }
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["cancel"]],
      },
    )
    assert res["ok"]
    assert res["controlsDisplay"] == "none"
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_helpers_normalize_heading(self):
    """normalizeHeading wraps angles correctly."""
    res = run_js("helpers", {"fn": "normalizeHeading", "args": [-10]})
    assert res["ok"]
    assert res["result"] == 350

  def test_helpers_drag_anchor_clamp(self):
    """dragAnchor clamps latitude to [-85, 85]."""
    anchor = {"lat": 0, "lng": -122, "heading_deg": 0}
    grab = {"lat": 0, "lng": 0}
    cur = {"lat": 90, "lng": 0}
    res = run_js("helpers", {"fn": "dragAnchor", "args": [anchor, grab, cur]})
    assert res["ok"]
    assert res["result"]["lat"] == 85
