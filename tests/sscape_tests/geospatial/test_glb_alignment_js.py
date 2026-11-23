# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent.parent.parent
_HARNESS = _TESTS_DIR / "align_harness.js"
_SCENE_UPDATE_TEMPLATE = (
  _REPO_ROOT / "manager" / "src" / "manager" / "templates" / "scene" / "scene_update.html"
)
FRAME_APPLIED = "#2e7d32"
FRAME_UNAPPLIED = "#c62828"
MOVING_OPACITY = 0.3
STAGED_OPACITY = 0.7
SAVED_OPACITY = 0.7
_NO_SAVED = {"status": 200, "body": {"max_layers": 1, "layers": []}}

SCENE_FIELDS_APPLIED = {
  "scale": 2.5,
  "rotation_x": 90.0,
  "rotation_y": 0.0,
  "rotation_z": 0.0,
  "translation_x": 12.5,
  "translation_y": -4.0,
  "translation_z": 0.0,
  "map_corners_lla": [[37.1, -122.1, 0.0], [37.1, -122.0, 0.0], [37.0, -122.0, 0.0], [37.0, -122.1, 0.0]],
}
SCENE_FIELDS_BASE = {
  "scale": None,
  "rotation_x": 0.0,
  "rotation_y": 0.0,
  "rotation_z": 0.0,
  "translation_x": 0.0,
  "translation_y": 0.0,
  "translation_z": 0.0,
  "map_corners_lla": None,
}


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


def _align(responses, steps, **extra):
  """Run the align scenario on a geospatial scene whose map centre is set."""
  args = {"mapType": "geospatial_map", "center": ["37", "-122"], "responses": responses, "steps": steps}
  return run_js("align", {**args, **extra})


def _saved_model_get(**overrides):
  """GLB list response with one saved layer at the default test anchor."""
  layer = {
    "id": "layer-1",
    "order": 0,
    "enabled": False,
    "filename": "model.glb",
    "download_url": "/media/model.glb",
    "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
    "footprint_m": {"width": 100, "height": 60},
    "preview_url": "/saved.png",
  }
  if "use_glb_map" in overrides:
    overrides["enabled"] = overrides.pop("use_glb_map")
  return {"status": 200, "body": {"max_layers": 1, "layers": [{**layer, **overrides}]}}


def _preview_resp(token):
  """Successful GLB preview response for a staged token."""
  return {
    "status": 200,
    "body": {
      "token": token,
      "preview_url": "/img.png",
      "footprint_m": {"width": 100, "height": 60},
      "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
    },
  }


def _last_opacity(res):
  """Opacity most recently set on the map overlay."""
  return [c[1] for c in res["calls"] if c[0] == "setOverlayOpacity"][-1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestGlbAlignment:
  """Test GLB alignment UI behaviour through the node harness."""

  def test_visibility_non_geospatial(self):
    """Row hidden when not geospatial_map type."""
    res = run_js("align", {"mapType": "image_map", "center": ["37", "-122"], "steps": []})
    assert res["rowDisplay"] == "none"

  @pytest.mark.parametrize("center, disabled", [(["", ""], True), (["37", "-122"], False)])
  def test_file_input_needs_map_centre(self, center, disabled):
    """File input is disabled, with a hint, until the map centre is set."""
    res = run_js("align", {"mapType": "geospatial_map", "center": center, "steps": []})
    assert res["fileDisabled"] is disabled
    assert ("map location" in res["hint"].lower()) is disabled

  def test_upload_success(self):
    """A successful upload shows the controls, draws the overlay and leaves the form unlocked."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"]])
    assert res["cancelDisplay"] == ""
    assert len(res["fetches"]) == 2
    preview = res["fetches"][1]
    assert preview["url"].endswith("geospatial-glb-preview")
    assert preview["method"] == "POST"
    assert preview["headers"]["X-CSRFToken"] == "tok"
    assert preview["body"]["formData"][0][0] == "file"
    assert [c[3] for c in res["calls"] if c[0] == "setOverlay"] == [STAGED_OPACITY]
    assert not any("fitToCorners" in str(c) for c in res["calls"])
    assert res["statusList"] is None
    assert (res["fileDisabled"], res["filePointerEvents"], res["fileTitle"]) == (False, "", "")

  def test_upload_locks_file_input_while_in_flight(self):
    """Upload is disabled with a loading hint until the preview request settles."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"]])
    assert res["fetches"][1]["ui"] == {
      "fileDisabled": True,
      "filePointerEvents": "none",
      "fileWrapTitle": "loading glb...",
    }
    assert res["fetches"][0]["ui"]["fileDisabled"] is False

  def test_upload_error_is_shown_as_errorlist_and_unlocks(self):
    """A rejected file shows its message in an errorlist box, like the scene upload form."""
    res = _align([_NO_SAVED, {"status": 400, "body": {"error": "Invalid GLB"}}], [["upload"]])
    assert res["statusList"] == {"tagName": "UL", "className": "errorlist", "items": ["Invalid GLB"]}
    assert res["cancelDisplay"] == "none"
    assert (res["fileDisabled"], res["filePointerEvents"], res["fileTitle"]) == (False, "", "")

  def test_upload_non_json_error_shows_status_code(self):
    """A non-JSON error body (e.g. a proxy 413 page) still shows a readable message."""
    res = _align([_NO_SAVED, {"status": 413, "nonJson": True}], [["upload"]])
    assert res["statusList"]["items"] == ["Request failed (413)"]

  @pytest.mark.parametrize("limit_bytes, shown", [(132 * 1024 * 1024, "132 MB"), (1536 * 1024, "1.5 MB")])
  def test_upload_413_shows_configured_size_limit(self, limit_bytes, shown):
    """A 413 without a JSON body names the limit the template passed from the server setting."""
    res = _align([_NO_SAVED, {"status": 413, "nonJson": True}], [["upload"]], maxUploadBytes=limit_bytes)
    (message,) = res["statusList"]["items"]
    assert shown in message

  def test_upload_413_without_configured_limit_keeps_generic_message(self):
    """Without the limit attribute the error falls back to the request status."""
    res = _align([_NO_SAVED, {"status": 413, "nonJson": True}], [["upload"]])
    assert res["statusList"]["items"] == ["Request failed (413)"]

  def test_load_saved_alignment_failure_is_shown(self):
    """A failed load of the saved model shows an error instead of silently leaving the form empty."""
    res = _align([{"status": 500, "body": {"error": "boom"}}], [])
    assert res["statusList"] == {
      "tagName": "UL",
      "className": "errorlist",
      "items": ["Could not load the saved 3D model: boom"],
    }
    assert res["savedBlockDisplay"] != ""

  def test_load_saved_alignment_success_shows_no_error(self):
    """Loading a saved model, or none, leaves the status empty."""
    for response in (_saved_model_get(), _NO_SAVED):
      assert _align([response], [])["statusList"] is None

  def test_toggle_apply_sends_put_without_confirm(self):
    """Applying a saved model goes straight to the PUT with no confirm dialog."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True]], confirm=False)
    assert res["confirms"] == []
    assert [f["method"] for f in res["fetches"]] == ["GET", "PUT"]

  def test_save_scene_with_staged_model_posts_token_and_anchor(self):
    """A staged model is saved only by Save Scene Updates, which carries its token and anchor."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["submit"]])
    (submit,) = res["submits"]
    assert submit["prevented"] is False
    assert res["glbChanges"] == [
      {"token": "tok1", "anchor": {"lat": 37, "lng": -122, "heading_deg": 0}, "enabled": True}
    ]
    assert [f["method"] for f in res["fetches"]] == ["GET", "POST"]

  def test_upload_without_map_location_is_refused(self):
    """Upload is rejected without a map location and the control stays disabled and unlabelled."""
    res = run_js("align", {"mapType": "geospatial_map", "center": ["", ""], "steps": [["upload"]]})
    assert "map location" in res["status"].lower()
    assert res["fileDisabled"] is True
    assert res["fileTitle"] == ""

  def test_drag_inside_prevents_pan(self):
    """Drag inside the footprint prevents map pan and moves the anchor."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["drag", [0, 0], [100, 100]]])
    assert res["events"][0]["prevented"] is True
    assert res["anchor"]["lat"] < 37
    assert res["anchor"]["lng"] > -122
    assert res["dirty"] is True

  def test_drag_outside_not_prevented(self):
    """Drag far outside the footprint leaves the map pan alone."""
    steps = [["upload"], ["drag", [100000, 100000], [100100, 100100]]]
    res = _align([_NO_SAVED, _preview_resp("tok1")], steps)
    assert res["events"][0]["prevented"] is False

  def test_drag_beyond_50_km_of_map_centre_is_ignored(self):
    """Boundary: a drag that would put the anchor over 50 km from the map centre leaves it in place."""
    steps = [["upload"], ["drag", [0, 0], [100000, 0]]]  # about 89 km east
    res = _align([_NO_SAVED, _preview_resp("tok1")], steps)
    assert res["anchor"]["lng"] == -122
    assert res["dirty"] is False

  def test_drag_within_50_km_of_map_centre_is_applied(self):
    """Boundary: a drag that keeps the anchor under 50 km from the map centre moves it."""
    steps = [["upload"], ["drag", [0, 0], [40000, 0]]]  # about 36 km east
    res = _align([_NO_SAVED, _preview_resp("tok1")], steps)
    assert res["anchor"]["lng"] == pytest.approx(-121.6)
    assert res["dirty"] is True

  @pytest.mark.parametrize("responses, steps, resting", [
    ([_NO_SAVED, _preview_resp("tok1")], [["upload"]], STAGED_OPACITY),
    ([_saved_model_get()], [], SAVED_OPACITY),
  ])
  def test_hold_without_drag_fades_overlay_and_release_restores_it(self, responses, steps, resting):
    """A press on the model fades it so the map shows through, even without dragging, and release restores it."""
    pressed = _align(responses, steps + [["press", [0, 0]]])
    assert _last_opacity(pressed) == MOVING_OPACITY
    assert pressed["dirty"] is False
    released = _align(responses, steps + [["press", [0, 0]], ["release"]])
    assert _last_opacity(released) == resting
    assert released["dirty"] is False

  def test_drag_fades_overlay_until_release(self):
    """The overlay stays faded for the whole drag and returns to its resting opacity on release."""
    responses = [_NO_SAVED, _preview_resp("tok1")]
    dragging = _align(responses, [["upload"], ["press", [0, 0]]])
    assert _last_opacity(dragging) == MOVING_OPACITY
    res = _align(responses, [["upload"], ["drag", [0, 0], [100, 100]]])
    assert _last_opacity(res) == STAGED_OPACITY
    assert res["dirty"] is True

  def test_cancel_removes_overlay(self):
    """Cancel removes the overlay and hides the Cancel button and the footprint."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["cancel"]])
    assert res["cancelDisplay"] == "none"
    assert res["footprintText"] == ""
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_cancel_button_is_for_a_staged_model_only(self):
    """The Cancel button, next to the file input, shows for a staged model and not for a saved one."""
    assert _align(_STAGED, [["upload"]])["cancelDisplay"] == ""
    assert _align([_saved_model_get()], [])["cancelDisplay"] == "none"
    assert _align(_STAGED, [])["cancelDisplay"] == "none"

  def test_footprint_is_shown_for_a_staged_model(self):
    """The staged model's footprint is listed under the file input and cleared on cancel."""
    staged = _align(_STAGED, [["upload"]])
    assert staged["footprintText"] == "Footprint: 100.0 \u00d7 60.0 m"
    assert _align(_STAGED, [["upload"], ["cancel"]])["footprintText"] == ""

  def test_cancel_button_discards_the_staged_model(self):
    """Clicking Cancel removes the staged overlay, hides itself and the dial, and keeps nothing staged."""
    res = _align(_STAGED, [["upload"], ["cancelClick"]])
    assert res["staged"] is None
    assert res["cancelDisplay"] == "none"
    assert res["dialTrail"][-1] == "none"
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_saved_only_model_shows_dial_at_saved_heading(self):
    """A saved GLB with no staged replacement shows the dial with the knob at the saved heading."""
    anchor = {"lat": 37, "lng": -122, "heading_deg": 45}
    res = _align([_saved_model_get(anchor=anchor)], [])
    assert res["dial"]["attrs"]["aria-valuenow"] == "45.0"

  def test_cancel_with_saved_model_returns_to_saved_heading(self):
    """Cancelling a replacement returns to the saved model and its heading, and hides the Cancel button."""
    anchor = {"lat": 37, "lng": -122, "heading_deg": 45}
    res = _align([_saved_model_get(anchor=anchor), _preview_resp("tok1")], [["upload"], ["heading", "90"], ["cancel"]])
    assert res["cancelDisplay"] == "none"
    assert res["dial"]["attrs"]["aria-valuenow"] == "45.0"
    assert res["anchor"]["heading_deg"] == 45

  def test_choose_file_with_staged_model_confirms_then_replaces(self):
    """Choosing a file while a model is staged asks to discard it, then uploads the new one."""
    responses = [_NO_SAVED, _preview_resp("tok1"), _preview_resp("tok2")]
    res = _align(responses, [["upload"], ["click"], ["upload"]])
    assert len(res["confirms"]) == 1
    assert "discard" in res["confirms"][0].lower()
    assert res["clicks"] == [{"prevented": False}]
    assert any("removeOverlay" in str(c) for c in res["calls"])
    assert res["staged"] == "tok2"
    assert res["fetches"][2]["url"].endswith("geospatial-glb-preview")

  def test_choose_file_with_saved_model_confirms_and_keeps_it(self):
    """Choosing a file while a model is saved asks to replace it; the saved model stays until you save the new one."""
    res = _align([_saved_model_get()], [["click"]], geomapReady=True)
    assert len(res["confirms"]) == 1
    assert "replace" in res["confirms"][0].lower()
    assert res["clicks"] == [{"prevented": False}]
    assert res["savedBlockDisplay"] == ""
    assert res["mapFrame"] == FRAME_UNAPPLIED

  @pytest.mark.parametrize("responses, steps, staged", [
    ([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["click"]], "tok1"),
    ([_saved_model_get()], [["click"]], None),
  ])
  def test_choose_file_declined_blocks_picker_and_keeps_model(self, responses, steps, staged):
    """Declining the prompt blocks the file picker and leaves the staged or saved model alone."""
    res = _align(responses, steps, confirm=False)
    assert len(res["confirms"]) == 1
    assert res["clicks"] == [{"prevented": True}]
    assert res["staged"] == staged
    assert not any("removeOverlay" in str(c) for c in res["calls"])

  def test_choose_file_without_model_skips_prompt(self):
    """Choosing a file with nothing staged or saved opens the picker without asking."""
    res = _align([_NO_SAVED], [["click"]])
    assert res["confirms"] == []
    assert res["clicks"] == [{"prevented": False}]

  @pytest.mark.parametrize("order", ["mapFirst", "fetchFirst"])
  def test_saved_overlay_drawn_see_through_once_map_ready(self, order):
    """A saved model draws after both map ready and saved fetch, in either order, without covering the map."""
    res = run_js(
      "savedOverlay",
      {
        "mapType": "geospatial_map",
        "center": ["37", "-122"],
        "order": order,
        "responses": [_saved_model_get()],
      },
    )
    overlays = [c for c in res["calls"] if c[0] == "setOverlay"]
    assert len(overlays) == 1
    assert overlays[0][1] == "/saved.png"
    assert overlays[0][3] == SAVED_OPACITY
    assert res["calls"][-1] == ["setOverlayOpacity", SAVED_OPACITY, "glb-overlay"]

  def test_save_position_shown_after_shift_and_hidden_after_save(self):
    """Save position appears once a saved model is shifted and hides after saving."""
    res = _align([_saved_model_get(), {"status": 200, "body": {}}], [["drag", [0, 0], [100, 100]], ["save"]])
    assert res["savePosTrail"] == ["none", "", "none"]
    put = res["fetches"][-1]
    assert put["method"] == "PUT"
    assert put["body"] == {"anchor": res["anchor"]}
    assert res["status"] == "Position saved"
    assert res["dirty"] is False

  def test_save_position_failure_keeps_button_visible(self):
    """A failed save keeps the shift unsaved and the button available to retry."""
    responses = [_saved_model_get(), {"status": 500, "body": {"error": "boom"}}]
    res = _align(responses, [["drag", [0, 0], [100, 100]], ["save"]])
    assert res["savePosTrail"] == ["none", "", ""]
    assert res["status"] == "boom"
    assert res["dirty"] is True

  def test_drag_during_save_stays_unsaved(self):
    """A shift made while a save is in flight is not recorded as saved."""
    res = _align([_saved_model_get(), {"status": 200, "body": {}}], [["saveAndDrag", [0, 0], [100, 100]]])
    sent = res["fetches"][-1]["body"]["anchor"]
    assert res["savedAnchor"] == sent
    assert res["anchor"] != sent
    assert res["dirty"] is True
    assert res["savePosTrail"][-1] == ""

  def test_save_position_hidden_while_staging_replacement(self):
    """Staging a replacement hides Save position even after a shift."""
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["drag", [0, 0], [100, 100]], ["upload"]])
    assert res["savePosTrail"] == ["none", "", "none"]
    assert res["cancelDisplay"] == ""

  def test_remove_after_shift_clears_unsaved_state(self):
    """Removing a shifted model hides Save position and clears the unsaved flag."""
    res = _align([_saved_model_get(), {"status": 204, "body": {}}], [["drag", [0, 0], [100, 100]], ["remove"]])
    assert res["savePosTrail"] == ["none", "", "none"]
    assert res["dirty"] is False

  def test_save_scene_posts_shifted_anchor(self):
    """Save Scene Updates carries a shifted saved anchor and clears the unsaved prompt."""
    res = _align([_saved_model_get()], [["drag", [0, 0], [100, 100]], ["submit"]])
    assert res["glbChanges"] == [{"layer_id": "layer-1", "anchor": res["anchor"]}]
    assert res["dirty"] is False

  def test_save_scene_without_shift_posts_nothing(self):
    """An unshifted saved model adds nothing to Save Scene Updates."""
    res = _align([_saved_model_get()], [["submit"]])
    assert res["formInputs"] == []

  def test_save_scene_non_geospatial_posts_nothing(self):
    """Switching the scene away from a geospatial map drops the moved GLB from the save."""
    res = _align([_saved_model_get()], [["drag", [0, 0], [100, 100]], ["submit"]], mapType="map_upload")
    assert res["formInputs"] == []

  def test_save_scene_posts_staged_token_and_staged_anchor(self):
    """A staged GLB is posted with its token and staged anchor (not the saved one), even if never dragged."""
    steps = [["drag", [0, 0], [100, 100]], ["upload"], ["drag", [0, 0], [100, 100]], ["submit"]]
    res = _align([_saved_model_get(), _preview_resp("tok1")], steps)
    assert res["glbChanges"] == [
      {"token": "tok1", "anchor": res["anchor"], "layer_id": "layer-1", "enabled": False}
    ]
    assert res["dirty"] is False

    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["submit"]])
    assert res["glbChanges"] == [
      {"token": "tok1", "anchor": {"lat": 37, "lng": -122, "heading_deg": 0}, "layer_id": "layer-1", "enabled": False}
    ]

  def test_save_scene_replaces_stale_inputs(self):
    """A second submit replaces the earlier token and anchor inputs instead of posting duplicates."""
    steps = [["upload"], ["submit"], ["drag", [0, 0], [100, 100]], ["submit"]]
    res = _align([_saved_model_get(), _preview_resp("tok1")], steps)
    assert len(res["glbChanges"]) == 1
    assert res["glbChanges"][0]["anchor"] == res["anchor"]

  @pytest.mark.parametrize("use_glb_map, color", [(False, FRAME_UNAPPLIED), (True, FRAME_APPLIED)])
  def test_overlay_frame_color_follows_applied_state(self, use_glb_map, color):
    """The saved overlay is outlined red when not applied and green when applied."""
    res = _align([_saved_model_get(use_glb_map=use_glb_map)], [], geomapReady=True)
    assert res["mapFrame"] == color

  def test_overlay_frame_absent_without_saved_model(self):
    """No frame is drawn when the scene has no saved 3D model."""
    res = _align([_NO_SAVED], [], geomapReady=True)
    assert res["mapFrame"] is None

  def test_overlay_frame_follows_apply_toggle(self):
    """The frame turns green when the model is applied and red again when it is unapplied."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/applied.png"}},
      {"status": 200, "body": {"enabled": False, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True], ["toggleUse", False]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_UNAPPLIED, FRAME_APPLIED, FRAME_UNAPPLIED]

  def test_toggle_use_redraws_overlay_with_response_preview(self):
    """Toggling the GLB redraws the overlay from the response; the preview is the same in both states."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/saved.png"}},
      {"status": 200, "body": {"enabled": False, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True], ["toggleUse", False]], geomapReady=True)
    urls = [c[1] for c in res["calls"] if c[0] == "setOverlay"]
    assert urls == ["/saved.png", "/saved.png", "/saved.png"]

  def test_saved_model_without_preview_shows_a_message(self):
    """A saved model whose preview is missing says so instead of drawing nothing silently."""
    res = _align([_saved_model_get(preview_url=None)], [], geomapReady=True)
    assert "preview" in res["status"]
    assert not [c for c in res["calls"] if c[0] == "setOverlay"]

  def test_toggle_use_writes_state_token_to_form(self):
    """Applying the GLB writes the server's state token into the form, so the next save is not stale."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/saved.png", "state_token": "tok-applied"}},
    ]
    res = _align(responses, [["toggleUse", True]])
    assert res["stateToken"] == "tok-applied"

  def test_remove_writes_state_token_to_form(self):
    """Removing the GLB writes the server's state token into the form."""
    responses = [_saved_model_get(), {"status": 200, "body": {"success": True, "state_token": "tok-removed"}}]
    res = _align(responses, [["remove"]])
    assert res["stateToken"] == "tok-removed"

  def test_overlay_frame_unchanged_when_apply_fails(self):
    """A failed apply request leaves the frame in its previous state."""
    responses = [_saved_model_get(), {"status": 500, "body": {"error": "boom"}}]
    res = _align(responses, [["toggleUse", True]], geomapReady=True)
    assert res["status"] == "boom"
    assert res["frameTrail"] == [FRAME_UNAPPLIED, FRAME_UNAPPLIED]

  def test_overlay_frame_cleared_after_remove(self):
    """Removing the saved model clears the frame."""
    responses = [_saved_model_get(use_glb_map=True), {"status": 204, "body": {}}]
    res = _align(responses, [["remove"]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_APPLIED, None]

  def test_staging_over_saved_model_hides_saved_block_and_frame(self):
    """Uploading a replacement returns to the proposal state: no saved block, no frame."""
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_UNAPPLIED, None]
    assert res["savedBlockDisplay"] == "none"
    assert res["cancelDisplay"] == ""

  def test_cancel_staging_restores_saved_block_and_frame(self):
    """Cancelling the proposal brings back the saved block and its frame."""
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["cancel"]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_UNAPPLIED, None, FRAME_UNAPPLIED]
    assert res["savedBlockDisplay"] == ""
    assert res["cancelDisplay"] == "none"

  def test_toggle_use_writes_applied_scene_fields_to_form(self):
    """Applying the GLB writes the server pose, scale and corners into the scene-edit form."""
    res = _align(
      [_saved_model_get(), {"status": 200, "body": {"enabled": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}}],
      [["toggleUse", True]],
    )
    _assert_form_matches(res["sceneForm"], SCENE_FIELDS_APPLIED)

  def test_toggle_use_round_trip_follows_server_scene_fields(self):
    """Toggling the GLB on then off moves the scene-edit form from the applied to the base values."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
      {"status": 200, "body": {"enabled": False, "preview_url": "/saved.png", "scene_fields": SCENE_FIELDS_BASE}},
    ]
    res = _align(responses, [["toggleUse", True], ["toggleUse", False]])
    _assert_form_matches(res["sceneFormTrail"][1], SCENE_FIELDS_APPLIED)
    assert res["sceneFormTrail"][2] == {
      "id_scale": "",
      "id_rotation_x": 0,
      "id_rotation_y": 0,
      "id_rotation_z": 0,
      "id_translation_x": 0,
      "id_translation_y": 0,
      "id_translation_z": 0,
      "id_map_corners_lla": "",
    }

  def test_remove_applied_glb_writes_base_scene_fields_to_form(self):
    """Removing an applied GLB writes the server's unapplied scene fields into the form."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
      {"status": 200, "body": {"success": True, "scene_fields": SCENE_FIELDS_BASE}},
    ]
    res = _align(responses, [["toggleUse", True], ["remove"]])
    _assert_form_matches(res["sceneFormTrail"][1], SCENE_FIELDS_APPLIED)
    _assert_form_matches(res["sceneForm"], SCENE_FIELDS_BASE)
    assert res["status"] == "3D model removed"

  def test_remove_without_scene_fields_leaves_form_unchanged(self):
    """A DELETE response without scene_fields keeps the form as it was and still clears the saved model."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"enabled": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
      {"status": 204, "body": {}},
    ]
    res = _align(responses, [["toggleUse", True], ["remove"]])
    assert res["sceneFormTrail"][2] == res["sceneFormTrail"][1]
    _assert_form_matches(res["sceneForm"], SCENE_FIELDS_APPLIED)
    assert res["savedAnchor"] is None
    assert res["status"] == "3D model removed"

  def test_save_position_writes_moved_scene_fields_to_form(self):
    """Saving a moved anchor writes the server's recomputed scene fields into the form."""
    moved = {**SCENE_FIELDS_APPLIED, "translation_x": 20.0, "map_corners_lla": [[37.2, -122.2, 0.0]]}
    responses = [_saved_model_get(use_glb_map=True), {"status": 200, "body": {"scene_fields": moved}}]
    res = _align(responses, [["drag", [0, 0], [100, 100]], ["save"]])
    _assert_form_matches(res["sceneForm"], moved)
    assert res["status"] == "Position saved"

  def test_submit_when_idle_is_not_prevented(self):
    """Save Scene Updates submits normally when no position save is in flight."""
    res = _align([_saved_model_get()], [["drag", [0, 0], [100, 100]], ["submit"]])
    (submit,) = res["submits"]
    assert submit["prevented"] is False

  def test_submit_during_position_save_is_prevented_and_posts_nothing(self):
    """Save Scene Updates is blocked while a position save is in flight and adds no form inputs."""
    res = _align(
      [_saved_model_get(), {"status": 200, "body": {}}],
      [["drag", [0, 0], [100, 100]], ["saveAndSubmit"]],
    )
    (submit,) = res["submits"]
    assert submit["prevented"] is True
    assert submit["status"] == "Wait for the 3D model change to finish, then save."
    assert res["formInputs"] == []
    assert [f["method"] for f in res["fetches"]] == ["GET", "PUT"]

  @pytest.mark.parametrize("deg, expected", [(-180.001, 179.999), (180, -180), (0, 0), (359, -1)])
  def test_wrap_degrees_180_normalizes_negative_remainders(self, deg, expected):
    """Longitudes wrap into [-180, 180) even when JS % keeps a negative sign."""
    res = run_js("helpers", {"fn": "wrapDegrees180", "args": [deg]})
    assert res["ok"] is True
    assert res["result"] == pytest.approx(expected, abs=1e-9)


def _px(value):
  """Numeric part of a CSS length such as '12.5px'."""
  return float(value.removesuffix("px"))


def _knob_xy(dial):
  """Knob position relative to the dial center in units of the ring radius, with y growing downward."""
  radius = _px(dial["width"]) / 2
  return (_px(dial["knobLeft"]) - radius) / radius, (_px(dial["knobTop"]) - radius) / radius


_STAGED = [_NO_SAVED, _preview_resp("tok1")]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestOverlayOpacity:
  """The overlay always lets the map show through; only the map layer carries the alpha."""

  def test_staged_is_not_more_opaque_than_saved(self):
    """A proposal is no more opaque than a saved model, and neither is fully opaque."""
    staged = _align(_STAGED, [["upload"]])
    saved = _align([_saved_model_get()], [], geomapReady=True)
    assert [c[3] for c in staged["calls"] if c[0] == "setOverlay"] == [STAGED_OPACITY]
    assert [c[3] for c in saved["calls"] if c[0] == "setOverlay"] == [SAVED_OPACITY]
    assert MOVING_OPACITY < STAGED_OPACITY <= SAVED_OPACITY < 1

  @pytest.mark.parametrize("use_glb_map", [False, True])
  def test_saved_overlay_redrawn_after_apply_toggle_keeps_opacity(self, use_glb_map):
    """Re-running setOverlay after the apply toggle passes the saved opacity, applied or not."""
    responses = [
      _saved_model_get(use_glb_map=not use_glb_map),
      {"status": 200, "body": {"enabled": use_glb_map, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", use_glb_map]], geomapReady=True)
    assert [c[3] for c in res["calls"] if c[0] == "setOverlay"] == [SAVED_OPACITY, SAVED_OPACITY]

  def test_cancel_redraws_saved_overlay_at_saved_opacity(self):
    """Cancelling a proposal brings the saved overlay back at its resting opacity."""
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["cancel"]], geomapReady=True)
    assert [c[3] for c in res["calls"] if c[0] == "setOverlay"] == [SAVED_OPACITY, STAGED_OPACITY, SAVED_OPACITY]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestRotationDial:
  """Rotation dial drawn over the overlay on the map."""

  def test_hidden_until_a_model_is_staged_then_shown(self):
    """No dial exists before a model is staged; staging shows it."""
    res = _align(_STAGED, [["upload"]])
    assert res["dialTrail"] == [None, ""]
    assert res["dial"]["attached"] is True

  def test_shown_for_saved_model(self):
    """A saved model has a dial as soon as it loads."""
    res = _align([_saved_model_get()], [])
    assert res["dialTrail"] == [""]

  def test_cancel_hides_dial_for_unsaved_model_but_keeps_it_for_saved_model(self):
    """Cancel hides the dial when nothing is saved and keeps it for the saved model."""
    assert _align(_STAGED, [["upload"], ["cancel"]])["dialTrail"] == [None, "", "none"]
    saved = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["cancel"]])
    assert saved["dialTrail"] == ["", "", ""]

  def test_remove_hides_dial(self):
    """Removing the saved model hides the dial."""
    res = _align([_saved_model_get(), {"status": 204, "body": {}}], [["remove"]])
    assert res["dialTrail"] == ["", "none"]

  def test_non_geospatial_scene_never_shows_dial(self):
    """A scene that is not a geospatial map has no dial."""
    res = _align([_saved_model_get()], [], mapType="map_upload")
    assert res["dial"] is None

  def test_switching_away_from_geospatial_hides_dial(self):
    """Changing the map type to something else hides a visible dial."""
    res = _align([_saved_model_get()], [["mapType", "map_upload"], ["mapType", "geospatial_map"]])
    assert res["dialTrail"] == ["", "none", ""]

  def test_not_shown_while_map_is_not_ready(self):
    """Without a map strategy there is nothing to project onto, so no dial is created."""
    res = _align([_saved_model_get()], [], mapReady=False)
    assert res["dial"] is None

  def test_hidden_while_projection_is_not_ready_and_shown_after_view_change(self):
    """A map whose projection is not ready hides the dial; the next map view change shows it."""
    steps = [["upload"], ["view", {"notReady": True}], ["view", {"notReady": False}]]
    res = _align(_STAGED, steps, geomapReady=True)
    assert res["dialTrail"] == [None, "", "none", ""]

  def test_positioned_at_overlay_center_and_capped_to_the_preview(self):
    """The dial is centered on the anchor; on a small preview the 75% cap beats the 30 px minimum radius."""
    dial = _align(_STAGED, [["upload"]])["dial"]
    radius = _px(dial["width"]) / 2
    assert (_px(dial["left"]), _px(dial["top"])) == pytest.approx((-radius, -radius))
    assert _px(dial["width"]) == _px(dial["height"])
    # the preview is about 54 px on its shorter side here, so the ring is 75% of that
    assert radius == pytest.approx(0.375 * 54.3, abs=0.5)
    assert radius < 30

  def test_follows_pan_and_zoom_and_clamps_radius(self):
    """Map view changes move and resize the dial; the radius stays between 30 and 70 px unless the preview is small."""
    base = _align(_STAGED, [["upload"]])["dial"]
    panned = _align(_STAGED, [["upload"], ["view", {"dx": 50, "dy": 20}]], geomapReady=True)["dial"]
    radius = _px(panned["width"]) / 2
    assert (_px(panned["left"]), _px(panned["top"])) == pytest.approx((50 - radius, 20 - radius))

    zoomed = _align(_STAGED, [["upload"], ["view", {"scale": 3}]], geomapReady=True)["dial"]
    assert 30 < _px(zoomed["width"]) / 2 < 70
    assert _px(zoomed["left"]) == pytest.approx(-_px(zoomed["width"]) / 2)

    far = _align(_STAGED, [["upload"], ["view", {"scale": 10, "dx": 300}]], geomapReady=True)["dial"]
    assert _px(far["width"]) == 140
    assert _px(far["left"]) == 230

    out = _align(_STAGED, [["upload"], ["view", {"scale": 0.5}]], geomapReady=True)["dial"]
    assert _px(out["width"]) == pytest.approx(_px(base["width"]) / 2)

  def test_dial_is_hidden_until_the_preview_is_hovered(self):
    """The dial is laid out but not shown until the pointer is over the preview, and fades out when it leaves."""
    assert _align(_STAGED, [["upload"]])["dial"]["active"] is False
    over = _align(_STAGED, [["upload"], ["hover", [0, 0]]])
    assert over["dial"]["active"] is True
    off = _align(_STAGED, [["upload"], ["hover", [0, 0]], ["hover", [100000, 100000]]])
    assert off["dial"]["active"] is False
    left = _align(_STAGED, [["upload"], ["hover", [0, 0]], ["leave"]])
    assert left["dial"]["active"] is False

  def test_dial_is_shown_for_a_saved_model_on_hover(self):
    """A saved model's dial also appears only on hover."""
    assert _align([_saved_model_get()], [])["dial"]["active"] is False
    assert _align([_saved_model_get()], [["hover", [0, 0]]])["dial"]["active"] is True

  def test_dial_stays_visible_while_rotating_even_if_the_pointer_leaves_the_preview(self):
    """Holding the knob keeps the dial shown wherever the pointer goes; it fades once released away from the preview."""
    held = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [4000, 0], {"hold": True}]])
    assert held["dial"]["active"] is True
    released = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [4000, 0]]])
    assert released["dial"]["active"] is False

  def test_dial_is_shown_while_the_knob_has_keyboard_focus(self):
    """Keyboard users can focus the hidden knob, which then shows the dial until focus leaves."""
    focused = _align(_STAGED, [["upload"], ["dialFocus"]])
    assert focused["dial"]["active"] is True
    blurred = _align(_STAGED, [["upload"], ["dialFocus"], ["dialBlur"]])
    assert blurred["dial"]["active"] is False

  def test_touch_press_on_the_preview_shows_the_dial_and_a_press_elsewhere_hides_it(self):
    """Without hover, pressing the preview counts as hovering it, and pressing outside it does not."""
    on = _align(_STAGED, [["upload"], ["press", [0, 0]], ["release"]])
    assert on["dial"]["active"] is True
    off = _align(_STAGED, [["upload"], ["press", [0, 0]], ["release"], ["press", [100000, 100000]], ["release"]])
    assert off["dial"]["active"] is False

  def test_subscribes_once_to_map_view_changes_even_after_provider_switch(self):
    """Each geomap-ready replaces the previous subscription instead of adding another."""
    res = _align(_STAGED, [["upload"], ["geomapReady"], ["geomapReady"]], geomapReady=True)
    assert res["viewSubscribers"] == 1

  def test_reattached_after_map_container_is_emptied(self):
    """Switching provider empties the map container; the dial is put back on the next geomap-ready."""
    res = _align(_STAGED, [["upload"], ["detachDial"], ["geomapReady"]])
    assert res["dial"]["attached"] is True

  @pytest.mark.parametrize("heading, expected_xy", [
    ("0", (0, -1)), ("90", (1, 0)), ("180", (0, 1)), ("270", (-1, 0)),
  ])
  def test_knob_sits_on_ring_at_heading(self, heading, expected_xy):
    """The knob is on the ring at the heading, measured clockwise from the north tick at the top."""
    res = _align(_STAGED, [["upload"], ["heading", heading]])
    x, y = _knob_xy(res["dial"])
    assert (x, y) == pytest.approx(expected_xy, abs=1e-6)
    assert res["dial"]["attrs"]["aria-valuenow"] == f"{float(heading):.1f}"

  def test_knob_is_an_accessible_slider(self):
    """The knob exposes slider semantics over 0 to 359.9."""
    attrs = _align(_STAGED, [["upload"]])["dial"]["attrs"]
    assert attrs["role"] == "slider"
    assert (attrs["aria-valuemin"], attrs["aria-valuemax"], attrs["aria-valuenow"]) == ("0", "359.9", "0.0")
    assert attrs["aria-label"]

  def test_drag_sets_heading_and_fades_overlay(self):
    """Dragging the knob from north to east gives heading 90, marks the model moved and fades the overlay while held."""
    res = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 0]]])
    assert res["anchor"]["heading_deg"] == pytest.approx(90)
    assert res["dirty"] is True
    (event,) = res["dialEvents"]
    assert event == {"prevented": True, "stopped": True, "opacityOnGrab": MOVING_OPACITY, "opacityOnMove": MOVING_OPACITY}
    assert res["dial"]["captured"] == 7
    assert _last_opacity(res) == STAGED_OPACITY

  def test_held_knob_keeps_overlay_faded_until_release(self):
    """The overlay stays faded while the knob is held and returns to its resting opacity on release."""
    held = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 0], {"hold": True}]])
    assert _last_opacity(held) == MOVING_OPACITY
    released = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 0], {"hold": True}], ["release"]])
    assert _last_opacity(released) == STAGED_OPACITY

  def test_grab_does_not_jump_the_heading(self):
    """Grabbing the ring away from the knob keeps the heading until the pointer moves, then rotates relative to the grab."""
    still = _align(_STAGED, [["upload"], ["heading", "45"], ["dialDrag", [40, 0], [40, 0]]])
    assert still["anchor"]["heading_deg"] == pytest.approx(45)
    moved = _align(_STAGED, [["upload"], ["heading", "45"], ["dialDrag", [40, 0], [0, 40]]])
    assert moved["anchor"]["heading_deg"] == pytest.approx(135)

  def test_drag_snaps_lightly_to_cardinals(self):
    """A drag within 5 degrees of east lands on 90; further away it is continuous."""
    near = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 3]]])
    far = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 10]]])
    assert near["anchor"]["heading_deg"] == pytest.approx(90)
    assert far["anchor"]["heading_deg"] == pytest.approx(104.04, abs=0.01)

  def test_shift_turns_snapping_off(self):
    """Without Shift 88 degrees snaps to 90 on the first move; with Shift it stays at 88."""
    steps = [["upload"], ["heading", "88"]]
    snapped = _align(_STAGED, steps + [["dialDrag", [40, 0], [40, 0]]])
    free = _align(_STAGED, steps + [["dialDrag", [40, 0], [40, 0], {"shift": True}]])
    assert snapped["anchor"]["heading_deg"] == pytest.approx(90)
    assert free["anchor"]["heading_deg"] == pytest.approx(88)

  def test_shift_rotates_a_quarter_as_fast(self):
    """Shift-dragging a quarter turn changes the heading by a quarter of that."""
    res = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 3], {"shift": True}]])
    assert res["anchor"]["heading_deg"] == pytest.approx(94.29 / 4, abs=0.01)

  def test_shift_can_be_pressed_and_released_mid_drag_without_a_jump(self):
    """Switching Shift during a drag continues from the current heading in both directions."""
    path = [[40, 0, False], [0, 40, True], [-40, 0, False]]
    res = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], path]])
    # 0 -> 90 (normal), 90 -> 112.5 (a quarter of the next 90), 112.5 -> 202.5 (normal)
    assert res["anchor"]["heading_deg"] == pytest.approx(202.5)

  def test_drag_through_north_wraps_and_fine_drag_clamps_to_359_9(self):
    """Dragging just left of north snaps to 0; the same move with Shift stays below 360 at 359.9."""
    snapped = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [-0.001, -40]]])
    fine = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [-0.001, -40], {"shift": True}]])
    assert snapped["anchor"]["heading_deg"] == 0
    assert fine["anchor"]["heading_deg"] == 359.9

  @pytest.mark.parametrize("responses, steps", [
    (_STAGED, [["upload"]]),
    ([_saved_model_get()], []),
  ])
  def test_dial_hides_while_overlay_is_held_or_dragged_and_returns_on_release(self, responses, steps):
    """Holding or dragging the overlay hides the dial so the map shows undisturbed; releasing brings it back."""
    held = _align(responses, steps + [["press", [0, 0]]])
    assert held["dialTrail"][-1] == "none"
    released = _align(responses, steps + [["press", [0, 0]], ["release"]])
    assert released["dialTrail"][-2:] == ["none", ""]
    dragged = _align(responses, steps + [["drag", [0, 0], [100, 100]]])
    assert dragged["dialTrail"][-1] == ""

  def test_dial_stays_visible_while_it_is_being_rotated(self):
    """Rotating with the dial fades the overlay but does not hide the dial itself."""
    res = _align(_STAGED, [["upload"], ["dialDrag", [0, -40], [40, 0], {"hold": True}]])
    assert res["dialTrail"][-1] == ""

  def test_press_outside_overlay_keeps_dial_visible(self):
    """A press that does not hit the overlay is a map pan and leaves the dial alone."""
    res = _align(_STAGED, [["upload"], ["press", [100000, 100000]]])
    assert res["dialTrail"][-1] == ""

  def test_dial_press_does_not_start_overlay_drag_or_pan(self):
    """A press on the dial is not claimed by the map handler that drags the overlay, even over the footprint."""
    res = _align(_STAGED, [["upload"], ["mapPressOnDial", [0, 0]]])
    assert res["dialEvents"] == [{"prevented": False, "stopped": False}]
    assert res["dirty"] is False

  @pytest.mark.parametrize("event", ["mousedown", "touchstart"])
  def test_dial_legacy_events_are_stopped_and_change_nothing(self, event):
    """Mouse and touch starts on the dial do not reach the map and do not rotate the model."""
    res = _align(_STAGED, [["upload"], ["dialLegacy", event]])
    assert res["dialEvents"] == [{"stopped": True, "prevented": False}]
    assert res["dirty"] is False

  def test_dial_drag_on_saved_model_offers_save_position(self):
    """Rotating a saved model marks it moved, so Save position appears."""
    res = _align([_saved_model_get()], [["dialDrag", [0, -40], [40, 0]]])
    assert res["savePosTrail"] == ["none", ""]
    assert res["anchor"]["heading_deg"] == pytest.approx(90)

  @pytest.mark.parametrize("key, shift, start, expected", [
    ("ArrowRight", False, "0", 1), ("ArrowUp", False, "10", 11),
    ("ArrowLeft", False, "10", 9), ("ArrowDown", False, "10", 9),
    ("ArrowRight", True, "0", 15), ("ArrowLeft", True, "10", 355),
    ("ArrowLeft", False, "0", 359),
    ("ArrowRight", False, "359.9", 0.9),
  ])
  def test_arrow_keys_step_heading_and_wrap(self, key, shift, start, expected):
    """Arrow keys step 1 degree (15 with Shift) and wrap around north."""
    res = _align(_STAGED, [["upload"], ["heading", start], ["dialKey", key, shift]])
    assert res["anchor"]["heading_deg"] == pytest.approx(expected)
    assert res["dialEvents"] == [{"prevented": True}]
    assert res["dial"]["attrs"]["aria-valuenow"] == f"{expected:.1f}"

  def test_other_keys_are_left_alone(self):
    """Keys other than the arrows are not captured by the dial."""
    res = _align(_STAGED, [["upload"], ["dialKey", "Tab"]])
    assert res["dialEvents"] == [{"prevented": False}]
    assert res["dirty"] is False

  def test_cancel_restores_knob_to_saved_heading(self):
    """Cancelling a replacement returns the knob to the saved heading."""
    anchor = {"lat": 37, "lng": -122, "heading_deg": 90}
    responses = [_saved_model_get(anchor=anchor), _preview_resp("tok1")]
    res = _align(responses, [["upload"], ["dialDrag", [40, 0], [0, 40]], ["cancel"]])
    assert res["anchor"]["heading_deg"] == 90
    assert _knob_xy(res["dial"]) == pytest.approx((1, 0), abs=1e-6)
    assert res["dialTrail"][-1] == ""


def _assert_form_matches(form, scene_fields):
  """Every scene field returned by the server is written to its scene-edit input."""
  for name, value in scene_fields.items():
    actual = form[f"id_{name}"]
    if name == "map_corners_lla":
      assert (json.loads(actual) if actual else None) == value, name
    else:
      assert actual == (value if value is not None else ""), name


def test_template_has_cancel_beside_file_input_and_no_heading_controls():
  """Cancel sits right after the file input; the heading slider, number input, Reset and the controls box are gone."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  for removed in ("glbFrameLegend", "glbOpacity", "glbAccept", "glbHeadingRange", "glbHeadingNumber", "glbReset", "glbAlignControls"):
    assert removed not in html
  assert html.index('id="glbFileInput"') < html.index('id="glbCancel"') < html.index('id="glbFootprint"')
  assert 'id="glbFootprint"' in html


def test_template_passes_upload_limit_to_row():
  """The GLB row carries the server upload limit for the client-side error message."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  row = re.search(r'<div\s[^>]*id="glbAlignRow"[^>]*>', html).group(0)
  assert "data-max-upload-bytes=" in row
  assert "data-max-layers=" in row


def _layer(layer_id, order, anchor=None):
  """One saved GLB layer as the list endpoint returns it."""
  return {
    "id": layer_id,
    "order": order,
    "enabled": False,
    "filename": f"{layer_id}.glb",
    "download_url": f"/media/{layer_id}.glb",
    "anchor": anchor or {"lat": 37, "lng": -122, "heading_deg": 0},
    "footprint_m": {"width": 100, "height": 60},
    "preview_url": f"/{layer_id}.png",
  }


def _layers_get(*layers, max_layers=2):
  """GLB list response holding the given layers under the given limit."""
  return {"status": 200, "body": {"max_layers": max_layers, "layers": list(layers)}}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestMultipleLayers:
  """Panels per saved layer: the Add button, per-panel dirty flags, one save payload, and hit-testing."""

  def test_add_button_hidden_under_single_layer_limit(self):
    """With a limit of one the Add button stays hidden and only panel 0 exists."""
    res = _align([_layers_get(max_layers=1)], [], maxLayers=1)
    assert res["panelCount"] == 1
    assert res["addDisplay"] == "none"

  def test_add_button_shown_under_higher_limit(self):
    """With room left under the limit the Add button is visible and enabled."""
    res = _align([_layers_get(max_layers=3)], [], maxLayers=3)
    assert res["addDisplay"] == ""
    assert res["addDisabled"] is False

  def test_add_button_disabled_at_the_limit(self):
    """Once every allowed layer has a panel the Add button is disabled."""
    res = _align([_layers_get(_layer("layer-1", 0), _layer("layer-2", 1), max_layers=2)], [])
    assert res["panelCount"] == 2
    assert res["addDisabled"] is True

  def test_dirty_flags_are_kept_per_panel(self):
    """Changing one layer marks only that layer's panel dirty."""
    res = _align([_layers_get(_layer("layer-1", 0), _layer("layer-2", 1))], [["markDirty", 1]])
    assert res["panelDirty"] == [False, True]

  def test_save_posts_one_payload_with_only_dirty_layers(self):
    """Save Scene Updates posts a single glb_changes array holding just the changed layer."""
    res = _align(
      [_layers_get(_layer("layer-1", 0), _layer("layer-2", 1))],
      [["markDirty", 1], ["submit"]],
    )
    assert res["submits"][0]["prevented"] is False
    assert res["glbChanges"] == [
      {"layer_id": "layer-2", "anchor": {"lat": 37, "lng": -122, "heading_deg": 0}},
    ]

  def test_submit_clears_the_dirty_flags_it_sent(self):
    """After the form posts the pending changes no panel is left dirty."""
    res = _align(
      [_layers_get(_layer("layer-1", 0), _layer("layer-2", 1))],
      [["markDirty", 1], ["submit"]],
    )
    assert res["panelDirty"] == [False, False]


def _two_saved_layers():
  """Two saved layers; the second footprint sits about 1 km north, so the two map badges are apart."""
  return _layers_get(
    _layer("layer-1", 0),
    _layer("layer-2", 1, {"lat": 37.009, "lng": -122, "heading_deg": 0}),
  )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
class TestLayerLabels:
  """The picker status line, and layer numbers on the panel and at the NW corner on the map."""

  def test_status_says_no_file_selected_when_empty(self):
    """A panel with no file says so in place of the native "No file chosen" text."""
    res = _align([_NO_SAVED], [])
    assert res["panelState"][0]["status"] == "No file selected"

  def test_status_names_the_staged_file(self):
    """A staged file is named in the status line until it is saved or cancelled."""
    res = _align(_STAGED, [["upload"]])
    assert res["panelState"][0]["status"] == "a.glb (not saved yet)"

  def test_status_is_empty_for_a_saved_layer(self):
    """A saved layer's name is already in the saved block, so the status line is empty."""
    res = _align([_layers_get(_layer("layer-1", 0), max_layers=1)], [])
    assert res["panelState"][0]["status"] == ""

  def test_cancel_returns_status_to_no_file_selected(self):
    """Cancelling a staged file removes its name from the status line."""
    res = _align(_STAGED, [["upload"], ["cancelClick"]])
    assert res["panelState"][0]["status"] == "No file selected"

  def test_saved_layer_shows_its_short_id_with_the_full_id_on_hover(self):
    """A saved layer shows the first 8 characters of its id; the full id is in the title."""
    full_id = "3f2a9c1e-7b4d-4e8a-9c1f-0a1b2c3d4e5f"
    res = _align([_layers_get(_layer(full_id, 0), max_layers=1)], [])
    panel = res["panelState"][0]
    assert panel["layerId"] == "ID: 3f2a9c1e"
    assert panel["layerIdTitle"] == full_id

  def test_staged_layer_has_no_id(self):
    """A staged file has no server id yet, so the id line stays empty."""
    res = _align(_STAGED, [["upload"]])
    panel = res["panelState"][0]
    assert panel["layerId"] == ""
    assert panel["layerIdTitle"] == ""

  def test_single_layer_is_not_numbered(self):
    """With one layer there is no number on the panel or on the map."""
    res = _align([_layers_get(_layer("layer-1", 0), max_layers=1)], [])
    panel = res["panelState"][0]
    assert panel["badge"] == ""
    assert panel["badgeDisplay"] == "none"
    assert not panel["numbered"]
    assert panel["mapBadge"] is None

  def test_two_layers_are_numbered_in_draw_order(self):
    """Each layer shows its position in draw order on its panel and as a map badge at its NW corner."""
    res = _align([_two_saved_layers()], [])
    first, second = res["panelState"]
    assert (first["badge"], second["badge"]) == ("1", "2")
    assert (first["badgeLabel"], second["badgeLabel"]) == ("Model 1", "Model 2")
    assert first["numbered"] and second["numbered"]
    assert first["badgeDisplay"] == "" and second["badgeDisplay"] == ""
    assert (first["mapBadge"]["text"], second["mapBadge"]["text"]) == ("1", "2")
    assert second["mapBadge"]["label"] == "Model 2"
    assert second["mapBadge"]["display"] == ""
    assert second["mapBadge"]["attached"] is True

  def test_map_badge_is_at_the_footprint_nw_corner(self):
    """The map badge is placed on the NW corner (corner index 3) of each layer's footprint."""
    res = _align([_two_saved_layers()], [])
    for panel in res["panelState"]:
      assert panel["mapBadge"]["left"] == panel["nwPoint"]["left"]
      assert panel["mapBadge"]["top"] == panel["nwPoint"]["top"]

  def test_map_badge_follows_the_view(self):
    """Panning or zooming the map moves the map badge with the NW corner."""
    before = _align([_two_saved_layers()], [], geomapReady=True)
    after = _align(
      [_two_saved_layers()],
      [["view", {"scale": 2, "dx": 10, "dy": 5}]],
      geomapReady=True,
    )
    for old, new in zip(before["panelState"], after["panelState"]):
      assert new["mapBadge"]["left"] == new["nwPoint"]["left"]
      assert new["mapBadge"]["top"] == new["nwPoint"]["top"]
      assert new["mapBadge"]["left"] != old["mapBadge"]["left"]

  def test_map_badge_hidden_when_map_is_not_geospatial(self):
    """Off a geospatial map the map badge is hidden; the layer number on the panel still applies."""
    res = _align([_two_saved_layers()], [["mapType", "image_map"]])
    first, second = res["panelState"]
    assert second["mapBadge"]["display"] == "none"
    assert second["badge"] == "2"
    assert second["badgeLabel"] == "Model 2"

  def test_removing_a_layer_leaves_the_other_unnumbered(self):
    """Removing the first layer leaves one layer, which is no longer numbered."""
    res = _align([_two_saved_layers(), {"status": 200, "body": {}}], [["remove"]])
    first, second = res["panelState"]
    assert res["status"] == "3D model removed"
    assert (first["badge"], second["badge"]) == ("", "")
    assert not first["numbered"]
    assert first["layerId"] == "" and first["layerIdTitle"] == ""
    assert second["mapBadge"]["display"] == "none"

  def test_staged_layer_gets_the_next_number(self):
    """A layer staged after a saved one is Model 2 while staged, and its status names the file."""
    res = _align(
      [_layers_get(_layer("layer-1", 0), max_layers=2), _preview_resp("tok2")],
      [["addPanel"], ["stagePanel", 1, "b.glb"]],
    )
    saved, staged = res["panelState"]
    assert saved["badge"] == "1"
    assert staged["badge"] == "2"
    assert staged["badgeLabel"] == "Model 2"
    assert staged["status"] == "b.glb (not saved yet)"
    assert staged["mapBadge"]["text"] == "2"


def test_file_picker_hides_native_input_behind_a_label():
  """Both panel markups show the file picker as a label, so the native "No file chosen" text never shows."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  assert html.count('id="glbFileLabel"') == 2
  assert html.count('class="glb-file-input"') == 2
  assert html.count('id="glbFileInput"') == 2

  def test_topmost_hit_is_the_later_overlapping_panel(self):
    """Layers draw in panel order, so where footprints overlap the later layer is hit."""
    same = {"lat": 37, "lng": -122, "heading_deg": 0}
    res = run_js(
      "panelHits",
      {
        "responses": [_layers_get(_layer("layer-1", 0, same), _layer("layer-2", 1, same))],
        "points": [[37, -122], [37.1, -122]],
      },
    )
    assert res["ok"]
    assert res["panelCount"] == 2
    assert res["hits"] == [1, -1]

  def test_hit_on_single_layer_returns_it(self):
    """A point inside the only layer hits panel 0; a point outside hits nothing."""
    res = run_js(
      "panelHits",
      {"responses": [_layers_get(_layer("layer-1", 0))], "points": [[37, -122], [37.1, -122]]},
    )
    assert res["hits"] == [0, -1]
