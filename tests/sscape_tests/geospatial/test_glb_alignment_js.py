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
    assert any("fitToCorners" in str(c) for c in res["calls"])

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

  def test_upload_locks_file_input_while_in_flight(self):
    """Upload control is disabled with a loading hint until the preview request settles."""
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
    assert res["fetches"][1]["ui"] == {
      "fileDisabled": True,
      "filePointerEvents": "none",
      "fileWrapTitle": "loading glb...",
      "acceptDisabled": True,
      "acceptPointerEvents": "none",
      "acceptTitle": "loading glb...",
    }
    assert res["fetches"][0]["ui"]["fileDisabled"] is False
    assert res["fetches"][0]["ui"]["fileWrapTitle"] != "loading glb..."

  def test_upload_unlocks_after_success(self):
    """Upload control is re-enabled and the loading hint cleared after success."""
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
    assert res["fileDisabled"] is False
    assert res["filePointerEvents"] == ""
    assert res["fileTitle"] == ""

  def test_upload_unlocks_after_error(self):
    """Upload control is re-enabled and the loading hint cleared after a failed upload."""
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
    assert res["fileDisabled"] is False
    assert res["filePointerEvents"] == ""
    assert res["fileTitle"] == ""

  def test_upload_without_map_location_keeps_file_locked_off(self):
    """Upload rejected for missing map location leaves the control disabled and unlabelled."""
    res = run_js(
      "align",
      {"mapType": "geospatial_map", "center": ["", ""], "steps": [["upload"]]},
    )
    assert res["ok"]
    assert "map location" in res["status"].lower()
    assert res["fileDisabled"] is True
    assert res["fileTitle"] == ""

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

  def test_heading_update_clamps_out_of_range(self):
    """Heading above 359.9 or below 0 is clamped, not wrapped."""
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
        "steps": [["upload"], ["heading", "360"]],
      },
    )
    assert res["ok"]
    assert res["anchor"]["heading_deg"] == 359.9

    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, preview_resp],
        "steps": [["upload"], ["heading", "-5"]],
      },
    )
    assert res["ok"]
    assert res["anchor"]["heading_deg"] == 0

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

  def test_accept_locked_while_commit_in_flight(self):
    """Accept and upload controls are disabled while the commit request is in flight."""
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
    assert res["fetches"][0]["ui"]["acceptDisabled"] is False
    assert res["fetches"][2]["ui"] == {
      "fileDisabled": True,
      "filePointerEvents": "none",
      "fileWrapTitle": "saving glb...",
      "acceptDisabled": True,
      "acceptPointerEvents": "none",
      "acceptTitle": "saving glb...",
    }

  def test_accept_unlocks_after_error(self):
    """Accept is re-enabled with the error shown when the commit fails, so the user can retry."""
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
        "responses": [{"status": 404, "body": {}}, preview_resp, {"status": 400, "body": {"error": "Token expired"}}],
        "steps": [["upload"], ["accept"]],
      },
    )
    assert res["ok"]
    assert res["status"] == "Token expired"
    assert res["acceptDisabled"] is False
    assert res["acceptPointerEvents"] == ""
    assert res["acceptTitle"] == ""

  def test_accept_stays_locked_after_success(self):
    """Accept stays disabled after a successful commit while the page reloads."""
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
    assert res["acceptDisabled"] is True
    assert res["acceptTitle"] == "saving glb..."

  def test_replacement_upload_locks_accept_until_done(self):
    """Accept is locked during a replacement upload so it cannot commit the previous token."""
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
        "responses": [{"status": 404, "body": {}}, preview_resp, preview_resp],
        "steps": [["upload"], ["upload"]],
      },
    )
    assert res["ok"]
    assert res["fetches"][2]["ui"]["acceptDisabled"] is True
    assert res["fetches"][2]["ui"]["acceptTitle"] == "loading glb..."
    assert res["acceptDisabled"] is False
    assert res["acceptTitle"] == ""

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

  def test_helpers_clamp_heading(self):
    """clampHeading clamps to [0, 359.9] instead of wrapping."""
    cases = {-10: 0, 360: 359.9, 400: 359.9, 90: 90, 359.9: 359.9, "abc": None}
    for value, expected in cases.items():
      res = run_js("helpers", {"fn": "clampHeading", "args": [value]})
      assert res["ok"]
      assert res["result"] == expected

  def test_helpers_drag_anchor_clamp(self):
    """dragAnchor clamps latitude to [-85, 85]."""
    anchor = {"lat": 0, "lng": -122, "heading_deg": 0}
    grab = {"lat": 0, "lng": 0}
    cur = {"lat": 90, "lng": 0}
    res = run_js("helpers", {"fn": "dragAnchor", "args": [anchor, grab, cur]})
    assert res["ok"]
    assert res["result"]["lat"] == 85
