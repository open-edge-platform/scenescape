# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scene_common.earth_lla import localFootprintCornersLLA

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent.parent.parent
_HARNESS = _TESTS_DIR / "align_harness.js"
FRAME_APPLIED = "#2e7d32"
FRAME_UNAPPLIED = "#c62828"
_SCENE_UPDATE_TEMPLATE = (
  _REPO_ROOT / "manager" / "src" / "manager" / "templates" / "scene" / "scene_update.html"
)


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


def _saved_model_get():
  """Saved GLB response at the default test anchor."""
  return {
    "status": 200,
    "body": {
      "exists": True,
      "filename": "model.glb",
      "download_url": "/media/model.glb",
      "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
      "footprint_m": {"width": 100, "height": 60},
      "use_glb_map": False,
      "preview_url": "/saved.png",
    },
  }


def _preview_resp(token):
  """Successful GLB preview response for a staged token."""
  return {
    "status": 200,
    "body": {
      "token": token,
      "preview_url": "/img.png",
      "footprint_m": {"width": 100, "height": 60},
      "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
      "existing_content": {},
    },
  }


def _accept_args(steps):
  """Harness args for an upload-then-accept flow, plus any trailing steps."""
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
  return {
    "mapType": "geospatial_map",
    "center": ["37", "-122"],
    "responses": [{"status": 404, "body": {}}, preview_resp, accept_resp],
    "steps": steps,
  }


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
    assert not any("fitToCorners" in str(c) for c in res["calls"])
    assert [c[3] for c in res["calls"] if c[0] == "setOverlay"] == [0.6]

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

  def test_upload_error_is_shown_as_errorlist(self):
    """Failed upload renders the message in an errorlist box, like the scene upload form."""
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
    assert res["statusList"] == {"tagName": "UL", "className": "errorlist", "items": ["Invalid GLB"]}

  def test_upload_success_shows_no_errorlist(self):
    """Successful upload leaves no error box in the status area."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, _preview_resp("tok1")],
        "steps": [["upload"]],
      },
    )
    assert res["ok"]
    assert res["statusList"] is None

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

  def test_accept_stashes_live_view_before_reload(self):
    """Accept stores the live map view so the reload keeps it instead of the DB view."""
    res = run_js("align", _accept_args([["upload"], ["accept"]]))
    assert res["ok"]
    assert res["mapCalls"] == ["save", "load"]
    assert res["stored"] == {
      "path": "/scene/s1/update/",
      "provider": "google",
      "settings": {"lat": 37.5, "lng": -121.5, "zoom": 17.5, "rotation": 12},
    }

  def test_take_restores_stashed_view_once(self):
    """The stashed view is returned for the same page and provider, then consumed."""
    res = run_js(
      "align",
      _accept_args([["upload"], ["accept"], ["take", "google"], ["take", "google"]]),
    )
    assert res["ok"]
    assert res["takes"][0] == {"lat": 37.5, "lng": -121.5, "zoom": 17.5, "rotation": 12}
    assert res["takes"][1] == {}
    assert res["stored"] is None

  def test_take_ignores_stash_from_other_provider(self):
    """A view captured on one map provider is not restored on another (zoom scales differ)."""
    res = run_js("align", _accept_args([["upload"], ["accept"], ["take", "mapbox"]]))
    assert res["ok"]
    assert res["takes"] == [{}]
    assert res["stored"] is None

  def test_take_ignores_stash_from_other_page(self):
    """A view captured on one scene page is not restored on a different page."""
    res = run_js(
      "align",
      _accept_args([["upload"], ["accept"], ["take", "google", "/scene/s2/update/"]]),
    )
    assert res["ok"]
    assert res["takes"] == [{}]
    assert res["stored"] is None

  def test_choose_file_with_staged_model_confirms_then_replaces(self):
    """Choosing a file while a model is staged asks to discard it, then uploads the new one."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, _preview_resp("tok1"), _preview_resp("tok2")],
        "steps": [["upload"], ["click"], ["upload"]],
      },
    )
    assert res["ok"]
    assert len(res["confirms"]) == 1
    assert "discard" in res["confirms"][0].lower()
    assert res["clicks"] == [{"prevented": False}]
    assert any("removeOverlay" in str(c) for c in res["calls"])
    assert res["staged"] == "tok2"
    assert len(res["fetches"]) == 3
    assert res["fetches"][2]["url"].endswith("geospatial-glb-preview")

  def test_choose_file_declined_keeps_staged_model(self):
    """Declining the discard prompt keeps the staged model and blocks the file picker."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, _preview_resp("tok1")],
        "confirm": False,
        "steps": [["upload"], ["click"]],
      },
    )
    assert res["ok"]
    assert len(res["confirms"]) == 1
    assert res["clicks"] == [{"prevented": True}]
    assert res["staged"] == "tok1"
    assert res["controlsDisplay"] == ""
    assert not any("removeOverlay" in str(c) for c in res["calls"])
    assert len(res["fetches"]) == 2

  def test_choose_file_with_saved_model_confirms_and_keeps_it(self):
    """Choosing a file while a model is saved asks to replace it; the saved model stays until accept."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [_saved_model_get()],
        "steps": [["click"]],
      },
    )
    assert res["ok"]
    assert len(res["confirms"]) == 1
    assert "replace" in res["confirms"][0].lower()
    assert res["clicks"] == [{"prevented": False}]
    assert res["savedBlockDisplay"] == ""
    assert res["mapFrame"] == FRAME_UNAPPLIED

  def test_choose_file_declined_with_saved_model_blocks_picker(self):
    """Declining the replace prompt blocks the file picker."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get()],
        "confirm": False,
        "steps": [["click"]],
      },
    )
    assert res["ok"]
    assert len(res["confirms"]) == 1
    assert res["clicks"] == [{"prevented": True}]

  def test_choose_file_without_staged_model_skips_prompt(self):
    """Choosing a file with nothing staged or saved opens the picker without asking."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}],
        "steps": [["click"]],
      },
    )
    assert res["ok"]
    assert res["confirms"] == []
    assert res["clicks"] == [{"prevented": False}]

  def test_accept_with_existing_content_commits_without_confirm(self):
    """Accept with existing content commits directly; no confirmation is requested."""
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
        "confirm": False,
        "steps": [["upload"], ["accept"]],
      },
    )
    assert res["ok"]
    assert len(res["fetches"]) == 3
    assert res["fetches"][2]["method"] == "POST"

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

  @pytest.mark.parametrize("order", ["mapFirst", "fetchFirst"])
  def test_saved_overlay_drawn_at_full_opacity_once_map_ready(self, order):
    """Accepted model draws after both map ready and saved fetch, in either order."""
    saved = {
      "status": 200,
      "body": {
        "exists": True,
        "filename": "model.glb",
        "download_url": "/media/model.glb",
        "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
        "footprint_m": {"width": 100, "height": 60},
        "use_glb_map": False,
        "preview_url": "/saved.png",
      },
    }
    res = run_js(
      "savedOverlay",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "order": order,
        "responses": [saved],
      },
    )
    assert res["ok"]
    overlays = [c for c in res["calls"] if c[0] == "setOverlay"]
    assert len(overlays) == 1
    assert overlays[0][1] == "/saved.png"
    assert overlays[0][3] == 1
    assert res["calls"][-1] == ["setOverlayOpacity", 1]

  def test_save_position_shown_after_shift_and_hidden_after_save(self):
    """Save position appears once a saved model is shifted and hides after saving."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get(), {"status": 200, "body": {}}],
        "steps": [["drag", [0, 0], [100, 100]], ["save"]],
      },
    )
    assert res["ok"]
    assert res["savePosTrail"] == ["none", "", "none"]
    put = res["fetches"][-1]
    assert put["method"] == "PUT"
    assert put["body"] == {"anchor": res["anchor"]}
    assert res["status"] == "Position saved"
    assert res["dirty"] is False

  def test_save_position_failure_keeps_button_visible(self):
    """A failed save keeps the shift unsaved and the button available to retry."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get(), {"status": 500, "body": {"error": "boom"}}],
        "steps": [["drag", [0, 0], [100, 100]], ["save"]],
      },
    )
    assert res["ok"]
    assert res["savePosTrail"] == ["none", "", ""]
    assert res["status"] == "boom"
    assert res["dirty"] is True

  def test_drag_during_save_stays_unsaved(self):
    """A shift made while a save is in flight is not recorded as saved."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get(), {"status": 200, "body": {}}],
        "steps": [["saveAndDrag", [0, 0], [100, 100]]],
      },
    )
    assert res["ok"]
    sent = res["fetches"][-1]["body"]["anchor"]
    assert res["savedAnchor"] == sent
    assert res["anchor"] != sent
    assert res["dirty"] is True
    assert res["savePosTrail"][-1] == ""

  def test_save_position_hidden_while_staging_replacement(self):
    """Staging a replacement hides Save position even after a shift."""
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
        "responses": [_saved_model_get(), preview_resp],
        "steps": [["drag", [0, 0], [100, 100]], ["upload"]],
      },
    )
    assert res["ok"]
    assert res["savePosTrail"] == ["none", "", "none"]
    assert res["controlsDisplay"] == ""

  def test_remove_after_shift_clears_unsaved_state(self):
    """Removing a shifted model hides Save position and clears the unsaved flag."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get(), {"status": 204, "body": {}}],
        "steps": [["drag", [0, 0], [100, 100]], ["remove"]],
      },
    )
    assert res["ok"]
    assert res["savePosTrail"] == ["none", "", "none"]
    assert res["dirty"] is False

  def test_save_scene_posts_shifted_anchor(self):
    """Save Scene Updates carries a shifted saved anchor and clears the unsaved prompt."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get()],
        "steps": [["drag", [0, 0], [100, 100]], ["submit"]],
      },
    )
    assert res["ok"]
    (glb_anchor,) = res["formInputs"]
    assert glb_anchor["name"] == "glb_anchor"
    assert glb_anchor["type"] == "hidden"
    assert json.loads(glb_anchor["value"]) == res["anchor"]
    assert res["dirty"] is False

  def test_save_scene_without_shift_posts_no_anchor(self):
    """An unshifted saved model adds nothing to Save Scene Updates."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get()],
        "steps": [["submit"]],
      },
    )
    assert res["ok"]
    assert res["formInputs"] == []

  def test_save_scene_posts_staged_token_and_anchor(self):
    """Save Scene Updates with a staged GLB posts its token and the staged anchor, not the saved one."""
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
        "responses": [_saved_model_get(), preview_resp],
        "steps": [
          ["drag", [0, 0], [100, 100]],
          ["upload"],
          ["drag", [0, 0], [100, 100]],
          ["submit"],
        ],
      },
    )
    assert res["ok"]
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert set(inputs) == {"glb_token", "glb_anchor"}
    assert inputs["glb_token"]["type"] == "hidden"
    assert inputs["glb_token"]["value"] == "tok1"
    assert json.loads(inputs["glb_anchor"]["value"]) == res["anchor"]
    assert res["dirty"] is False

  def test_save_scene_staged_without_shift_posts_token_and_anchor(self):
    """A staged GLB is accepted on Save Scene Updates even when it was never dragged."""
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
        "responses": [_saved_model_get(), preview_resp],
        "steps": [["upload"], ["submit"]],
      },
    )
    assert res["ok"]
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert inputs["glb_token"]["value"] == "tok1"
    assert json.loads(inputs["glb_anchor"]["value"]) == {"lat": 37, "lng": -122, "heading_deg": 0}

  def test_save_scene_replaces_stale_token_input(self):
    """A second submit replaces the earlier staged token and anchor instead of posting duplicates."""
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
        "responses": [_saved_model_get(), preview_resp],
        "steps": [["upload"], ["submit"], ["drag", [0, 0], [100, 100]], ["submit"]],
      },
    )
    assert res["ok"]
    assert sorted(i["name"] for i in res["formInputs"]) == ["glb_anchor", "glb_token"]
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert inputs["glb_token"]["value"] == "tok1"
    assert json.loads(inputs["glb_anchor"]["value"]) == res["anchor"]

  def test_save_scene_non_geospatial_posts_no_glb_fields(self):
    """Switching the scene away from a geospatial map drops the staged/moved GLB from the save."""
    res = run_js(
      "align",
      {
        "mapType": "map_upload",
        "center": ["37", "-122"],
        "responses": [_saved_model_get()],
        "steps": [["drag", [0, 0], [100, 100]], ["submit"]],
      },
    )
    assert res["ok"]
    assert res["formInputs"] == []

  def test_upload_non_json_error_shows_status_code(self):
    """A non-JSON error body (e.g. a proxy 413 page) still shows a readable message."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [{"status": 404, "body": {}}, {"status": 413, "nonJson": True}],
        "steps": [["upload"]],
      },
    )
    assert res["ok"]
    assert res["statusList"]["items"] == ["Request failed (413)"]

  def test_save_scene_replaces_stale_anchor_input(self):
    """A second submit replaces the earlier anchor instead of posting two."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "responses": [_saved_model_get()],
        "steps": [
          ["drag", [0, 0], [100, 100]],
          ["submit"],
          ["drag", [100, 100], [200, 200]],
          ["submit"],
        ],
      },
    )
    assert res["ok"]
    (glb_anchor,) = res["formInputs"]
    assert json.loads(glb_anchor["value"]) == res["anchor"]

  def test_map_frame_unapplied_for_saved_model_not_applied(self):
    """A saved model that is not applied gets the red overlay frame."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [_saved_model_get()],
        "steps": [],
      },
    )
    assert res["ok"]
    assert res["mapFrame"] == FRAME_UNAPPLIED

  def test_map_frame_applied_for_saved_model_applied(self):
    """A saved model that is applied gets the green overlay frame."""
    applied = {**_saved_model_get()["body"], "use_glb_map": True}
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [{"status": 200, "body": applied}],
        "steps": [],
      },
    )
    assert res["ok"]
    assert res["mapFrame"] == FRAME_APPLIED

  def test_map_frame_absent_without_saved_model(self):
    """No frame is drawn when the scene has no saved 3D model."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [{"status": 404, "body": {}}],
        "steps": [],
      },
    )
    assert res["ok"]
    assert res["mapFrame"] is None

  def test_map_frame_follows_apply_toggle(self):
    """The frame turns green when the model is applied and red again when it is unapplied."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [
          _saved_model_get(),
          {"status": 200, "body": {"use_glb_map": True}},
          {"status": 200, "body": {"use_glb_map": False}},
        ],
        "steps": [["toggleUse", True], ["toggleUse", False]],
      },
    )
    assert res["ok"]
    assert res["frameTrail"] == [FRAME_UNAPPLIED, FRAME_APPLIED, FRAME_UNAPPLIED]

  def test_map_frame_unchanged_when_apply_fails(self):
    """A failed apply request leaves the frame in its previous state."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [_saved_model_get(), {"status": 500, "body": {"error": "boom"}}],
        "steps": [["toggleUse", True]],
      },
    )
    assert res["ok"]
    assert res["status"] == "boom"
    assert res["frameTrail"] == [FRAME_UNAPPLIED, FRAME_UNAPPLIED]

  def test_map_frame_cleared_after_remove(self):
    """Removing the saved model clears the frame."""
    applied = {**_saved_model_get()["body"], "use_glb_map": True}
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [{"status": 200, "body": applied}, {"status": 204, "body": {}}],
        "steps": [["remove"]],
      },
    )
    assert res["ok"]
    assert res["frameTrail"] == [FRAME_APPLIED, None]
    assert res["mapFrame"] is None

  def test_staging_over_saved_model_hides_saved_block_and_frame(self):
    """Uploading a replacement returns to the proposal state: no saved block, no frame."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [_saved_model_get(), _preview_resp("tok1")],
        "steps": [["upload"]],
      },
    )
    assert res["ok"]
    assert res["frameTrail"] == [FRAME_UNAPPLIED, None]
    assert res["savedBlockDisplay"] == "none"
    assert res["controlsDisplay"] == ""

  def test_cancel_staging_restores_saved_block_and_frame(self):
    """Cancelling the proposal brings back the saved block and its frame."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [_saved_model_get(), _preview_resp("tok1")],
        "steps": [["upload"], ["cancel"]],
      },
    )
    assert res["ok"]
    assert res["frameTrail"] == [FRAME_UNAPPLIED, None, FRAME_UNAPPLIED]
    assert res["savedBlockDisplay"] == ""
    assert res["controlsDisplay"] == "none"

  def test_staging_without_saved_model_keeps_saved_block_hidden(self):
    """A first upload shows no saved block and cancelling does not reveal one."""
    res = run_js(
      "align",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "geomapReady": True,
        "responses": [{"status": 404, "body": {}}, _preview_resp("tok1")],
        "steps": [["upload"], ["cancel"]],
      },
    )
    assert res["ok"]
    assert res["savedBlockDisplay"] == "none"
    assert res["mapFrame"] is None

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


def _element_classes(html, element_id):
  """Return the class tokens of the element with the given id in the template."""
  match = re.search(rf'<div\s[^>]*id="{element_id}"[^>]*>', html)
  if match is None:
    raise ValueError(f"element #{element_id} not found")
  cls = re.search(r'class="([^"]*)"', match.group(0))
  return set(cls.group(1).split()) if cls else set()


class TestGlbAlignmentTemplate:
  """Proposed and saved GLB panels share the same tinted panel styling."""

  def test_proposed_and_saved_panels_share_styling(self):
    """Proposed-state controls use the same panel classes as the saved block."""
    html = _SCENE_UPDATE_TEMPLATE.read_text()
    saved = _element_classes(html, "glbSavedBlock")
    proposed = _element_classes(html, "glbAlignControls")
    assert {"p-3", "border", "rounded", "bg-light"} <= saved
    assert {"p-3", "border", "rounded", "bg-light"} <= proposed

  def test_missing_panel_id_fails(self):
    """A missing panel id raises instead of passing with empty classes."""
    html = _SCENE_UPDATE_TEMPLATE.read_text()
    with pytest.raises(ValueError):
      _element_classes(html, "glbNoSuchPanel")
