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
_NO_SAVED = {"status": 200, "body": {"exists": False}}
_CONTENT = {"cameras": 2, "regions": 1, "sensors": 0}

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
      **overrides,
    },
  }


def _preview_resp(token, existing_content=None):
  """Successful GLB preview response for a staged token."""
  return {
    "status": 200,
    "body": {
      "token": token,
      "preview_url": "/img.png",
      "footprint_m": {"width": 100, "height": 60},
      "anchor": {"lat": 37, "lng": -122, "heading_deg": 0},
      "existing_content": existing_content or {},
    },
  }


def _accept_resp():
  """Successful commit response."""
  return {
    "status": 200,
    "body": {"anchor": {"lat": 37, "lng": -122, "heading_deg": 0}, "footprint_m": {"width": 100, "height": 60}},
  }


def _accept_flow(steps, **extra):
  """Upload tok1 with no saved model, then run the given steps (typically starting with accept)."""
  return _align([_NO_SAVED, _preview_resp("tok1"), _accept_resp()], [["upload"], *steps], **extra)


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
    assert res["controlsDisplay"] == ""
    assert len(res["fetches"]) == 2
    preview = res["fetches"][1]
    assert preview["url"].endswith("geospatial-glb-preview")
    assert preview["method"] == "POST"
    assert preview["headers"]["X-CSRFToken"] == "tok"
    assert preview["body"]["formData"][0][0] == "file"
    assert [c[3] for c in res["calls"] if c[0] == "setOverlay"] == [0.6]
    assert not any("fitToCorners" in str(c) for c in res["calls"])
    assert res["statusList"] is None
    assert (res["fileDisabled"], res["filePointerEvents"], res["fileTitle"]) == (False, "", "")

  def test_upload_locks_file_input_while_in_flight(self):
    """Upload and accept are disabled with a loading hint until the preview request settles."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"]])
    assert res["fetches"][1]["ui"] == {
      "fileDisabled": True,
      "filePointerEvents": "none",
      "fileWrapTitle": "loading glb...",
      "acceptDisabled": True,
      "acceptPointerEvents": "none",
      "acceptTitle": "loading glb...",
    }
    assert res["fetches"][0]["ui"]["fileDisabled"] is False

  def test_upload_error_is_shown_as_errorlist_and_unlocks(self):
    """A rejected file shows its message in an errorlist box, like the scene upload form."""
    res = _align([_NO_SAVED, {"status": 400, "body": {"error": "Invalid GLB"}}], [["upload"]])
    assert res["statusList"] == {"tagName": "UL", "className": "errorlist", "items": ["Invalid GLB"]}
    assert res["controlsDisplay"] == "none"
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

  def test_toggle_apply_confirms_existing_content_and_proceeds(self):
    """Applying over cameras and regions lists them in a confirm; accepting sends the apply."""
    responses = [
      _saved_model_get(existing_content=_CONTENT),
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True]])
    (msg,) = res["confirms"]
    assert "2 cameras" in msg and "1 region" in msg and "sensor" not in msg
    assert [f["method"] for f in res["fetches"]] == ["GET", "PUT"]

  def test_toggle_apply_declined_sends_nothing_and_reverts_checkbox(self):
    """Declining the apply confirm sends no request and unticks the checkbox."""
    res = _align([_saved_model_get(existing_content=_CONTENT)], [["toggleUse", True]], confirm=False)
    assert len(res["confirms"]) == 1
    assert [f["method"] for f in res["fetches"]] == ["GET"]
    assert res["useChecked"] is False

  @pytest.mark.parametrize("content", [{}, {"cameras": 0, "regions": 0, "sensors": 0}])
  def test_toggle_apply_without_existing_content_skips_confirm(self, content):
    """There is nothing to warn about when the scene has no cameras, regions or sensors."""
    responses = [
      _saved_model_get(existing_content=content),
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True]], confirm=False)
    assert res["confirms"] == []
    assert [f["method"] for f in res["fetches"]] == ["GET", "PUT"]

  def test_toggle_unapply_does_not_confirm(self):
    """Unapplying is not an overwrite, so it never asks."""
    responses = [
      _saved_model_get(use_glb_map=True, existing_content=_CONTENT),
      {"status": 200, "body": {"use_glb_map": False, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", False]], confirm=False)
    assert res["confirms"] == []
    assert [f["method"] for f in res["fetches"]] == ["GET", "PUT"]

  @pytest.mark.parametrize("answer, methods", [(True, ["GET", "POST", "POST"]), (False, ["GET", "POST"])])
  def test_accept_over_applied_model_confirms_existing_content(self, answer, methods):
    """Accepting a replacement re-applies it when the saved model is applied, so it asks first."""
    responses = [_saved_model_get(use_glb_map=True), _preview_resp("tok1", _CONTENT), _accept_resp()]
    res = _align(responses, [["upload"], ["accept"]], confirm=answer)
    assert len(res["confirms"]) == 1 and "2 cameras" in res["confirms"][0]
    assert [f["method"] for f in res["fetches"]] == methods

  def test_accept_over_unapplied_model_does_not_confirm(self):
    """A replacement over a saved model that is not applied is only stored, so it does not ask."""
    responses = [_saved_model_get(), _preview_resp("tok1", _CONTENT), _accept_resp()]
    res = _align(responses, [["upload"], ["accept"]], confirm=False)
    assert res["confirms"] == []
    assert len(res["fetches"]) == 3

  def test_save_scene_over_applied_model_declined_is_prevented(self):
    """Save Scene Updates with a staged replacement of an applied model is blocked when declined."""
    responses = [_saved_model_get(use_glb_map=True), _preview_resp("tok1", _CONTENT)]
    res = _align(responses, [["upload"], ["submit"]], confirm=False)
    (submit,) = res["submits"]
    assert submit["prevented"] is True
    assert res["formInputs"] == []

  def test_legend_swatches_use_overlay_frame_colors(self):
    """The legend swatches take their colors from the frame colors drawn on the map."""
    res = _align([_NO_SAVED], [])
    assert res["legendColors"] == [FRAME_APPLIED, FRAME_UNAPPLIED]

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

  @pytest.mark.parametrize("typed, expected", [("90", 90.0), ("360", 359.9), ("-5", 0)])
  def test_heading_update_is_clamped_not_wrapped(self, typed, expected):
    """Typing a heading updates the anchor; out-of-range values clamp instead of wrapping."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["heading", typed]])
    assert res["anchor"]["heading_deg"] == expected
    assert res["dirty"] is True

  def test_typed_heading_is_not_rewritten_until_blur(self):
    """The number field keeps what the user typed while typing and is normalized on change."""
    steps = [["upload"], ["heading", "4"]]
    res = _align([_NO_SAVED, _preview_resp("tok1")], steps)
    assert res["headingValue"] == "4"
    assert float(res["headingRangeValue"]) == 4
    res = _align([_NO_SAVED, _preview_resp("tok1")], steps + [["headingBlur"]])
    assert res["headingValue"] == "4.0"

  def test_empty_heading_input_is_ignored(self):
    """Clearing the field to retype does not reset the heading to 0."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["heading", "90"], ["heading", ""]])
    assert res["anchor"]["heading_deg"] == 90

  def test_saved_only_model_hides_staged_only_controls(self):
    """Opacity and Accept apply to a staged model only; a saved model shows heading, Reset and Cancel."""
    res = _align([_saved_model_get()], [])
    assert res["acceptDisplay"] == "none"
    assert res["opacityDisplay"] == "none"
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"]])
    assert res["acceptDisplay"] == ""
    assert res["opacityDisplay"] == ""

  def test_reset_restores_original(self):
    """Reset restores the staged anchor and clears the unsaved flag."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["heading", "90"], ["reset"]])
    assert res["anchor"]["heading_deg"] == 0.0
    assert res["dirty"] is False

  def test_cancel_removes_overlay(self):
    """Cancel removes the overlay and hides the controls."""
    res = _align([_NO_SAVED, _preview_resp("tok1")], [["upload"], ["cancel"]])
    assert res["controlsDisplay"] == "none"
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_saved_only_model_shows_heading_controls_with_saved_heading(self):
    """A saved GLB with no staged replacement still shows the heading control, set to the saved heading."""
    anchor = {"lat": 37, "lng": -122, "heading_deg": 45}
    res = _align([_saved_model_get(anchor=anchor)], [])
    assert res["controlsDisplay"] == ""
    assert res["headingValue"] == "45.0"

  def test_cancel_with_saved_model_keeps_heading_controls(self):
    """Cancelling a replacement returns to the saved model, so its heading control stays visible and shows the saved heading."""
    anchor = {"lat": 37, "lng": -122, "heading_deg": 45}
    res = _align([_saved_model_get(anchor=anchor), _preview_resp("tok1")], [["upload"], ["heading", "90"], ["cancel"]])
    assert res["controlsDisplay"] == ""
    assert res["headingValue"] == "45.0"
    assert res["anchor"]["heading_deg"] == 45

  def test_accept_saves_and_reloads_without_confirm(self):
    """Accept posts the token and anchor and removes the overlay, even over existing content."""
    responses = [_NO_SAVED, _preview_resp("tok1", {"cameras": 2, "regions": 0, "sensors": 0}), _accept_resp()]
    res = _align(responses, [["upload"], ["accept"]], confirm=False)
    assert len(res["fetches"]) == 3
    commit = res["fetches"][2]
    assert commit["url"].endswith("geospatial-glb")
    assert commit["method"] == "POST"
    assert commit["body"]["token"] == "tok1"
    assert commit["body"]["anchor"]["lat"] == 37
    assert res["confirms"] == []
    assert any("removeOverlay" in str(c) for c in res["calls"])

  def test_accept_locks_controls_while_committing_and_after_success(self):
    """Accept and upload are disabled during the commit and stay disabled while the page reloads."""
    res = _accept_flow([["accept"]])
    assert res["fetches"][2]["ui"] == {
      "fileDisabled": True,
      "filePointerEvents": "none",
      "fileWrapTitle": "saving glb...",
      "acceptDisabled": True,
      "acceptPointerEvents": "none",
      "acceptTitle": "saving glb...",
    }
    assert res["acceptDisabled"] is True
    assert res["acceptTitle"] == "saving glb..."

  def test_accept_unlocks_after_error(self):
    """Accept is re-enabled with the error shown when the commit fails, so the user can retry."""
    responses = [_NO_SAVED, _preview_resp("tok1"), {"status": 400, "body": {"error": "Token expired"}}]
    res = _align(responses, [["upload"], ["accept"]])
    assert res["status"] == "Token expired"
    assert (res["acceptDisabled"], res["acceptPointerEvents"], res["acceptTitle"]) == (False, "", "")

  def test_replacement_upload_locks_accept_until_done(self):
    """Accept is locked during a replacement upload so it cannot commit the previous token."""
    res = _align([_NO_SAVED, _preview_resp("tok1"), _preview_resp("tok2")], [["upload"], ["upload"]])
    assert res["fetches"][2]["ui"]["acceptDisabled"] is True
    assert res["fetches"][2]["ui"]["acceptTitle"] == "loading glb..."
    assert res["acceptDisabled"] is False

  def test_accept_stashes_live_view_before_reload(self):
    """Accept stores the live map view so the reload keeps it instead of the DB view."""
    res = _accept_flow([["accept"]])
    assert res["mapCalls"] == ["save", "load"]
    assert res["stored"] == {
      "path": "/scene/s1/update/",
      "provider": "google",
      "settings": {"lat": 37.5, "lng": -121.5, "zoom": 17.5, "rotation": 12},
    }

  def test_take_restores_stashed_view_once(self):
    """The stashed view is returned for the same page and provider, then consumed."""
    res = _accept_flow([["accept"], ["take", "google"], ["take", "google"]])
    assert res["takes"] == [{"lat": 37.5, "lng": -121.5, "zoom": 17.5, "rotation": 12}, {}]
    assert res["stored"] is None

  @pytest.mark.parametrize("take_step", [["take", "mapbox"], ["take", "google", "/scene/s2/update/"]])
  def test_take_ignores_stash_from_other_provider_or_page(self, take_step):
    """A view captured on another map provider (zoom scales differ) or scene page is not restored."""
    res = _accept_flow([["accept"], take_step])
    assert res["takes"] == [{}]
    assert res["stored"] is None

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
    """Choosing a file while a model is saved asks to replace it; the saved model stays until accept."""
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
  def test_saved_overlay_drawn_at_full_opacity_once_map_ready(self, order):
    """A saved model draws after both map ready and saved fetch, in either order."""
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
    assert overlays[0][3] == 1
    assert res["calls"][-1] == ["setOverlayOpacity", 1]

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
    assert res["controlsDisplay"] == ""

  def test_remove_after_shift_clears_unsaved_state(self):
    """Removing a shifted model hides Save position and clears the unsaved flag."""
    res = _align([_saved_model_get(), {"status": 204, "body": {}}], [["drag", [0, 0], [100, 100]], ["remove"]])
    assert res["savePosTrail"] == ["none", "", "none"]
    assert res["dirty"] is False

  def test_save_scene_posts_shifted_anchor(self):
    """Save Scene Updates carries a shifted saved anchor and clears the unsaved prompt."""
    res = _align([_saved_model_get()], [["drag", [0, 0], [100, 100]], ["submit"]])
    (glb_anchor,) = res["formInputs"]
    assert glb_anchor["name"] == "glb_anchor"
    assert glb_anchor["type"] == "hidden"
    assert json.loads(glb_anchor["value"]) == res["anchor"]
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
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert set(inputs) == {"glb_token", "glb_anchor"}
    assert inputs["glb_token"]["type"] == "hidden"
    assert inputs["glb_token"]["value"] == "tok1"
    assert json.loads(inputs["glb_anchor"]["value"]) == res["anchor"]
    assert res["dirty"] is False

    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["submit"]])
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert inputs["glb_token"]["value"] == "tok1"
    assert json.loads(inputs["glb_anchor"]["value"]) == {"lat": 37, "lng": -122, "heading_deg": 0}

  def test_save_scene_replaces_stale_inputs(self):
    """A second submit replaces the earlier token and anchor inputs instead of posting duplicates."""
    steps = [["upload"], ["submit"], ["drag", [0, 0], [100, 100]], ["submit"]]
    res = _align([_saved_model_get(), _preview_resp("tok1")], steps)
    assert sorted(i["name"] for i in res["formInputs"]) == ["glb_anchor", "glb_token"]
    inputs = {i["name"]: i for i in res["formInputs"]}
    assert json.loads(inputs["glb_anchor"]["value"]) == res["anchor"]

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
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/applied.png"}},
      {"status": 200, "body": {"use_glb_map": False, "preview_url": "/saved.png"}},
    ]
    res = _align(responses, [["toggleUse", True], ["toggleUse", False]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_UNAPPLIED, FRAME_APPLIED, FRAME_UNAPPLIED]

  def test_toggle_use_redraws_overlay_with_response_preview(self):
    """Toggling the GLB redraws the overlay from the response; the preview is the same in both states."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/saved.png"}},
      {"status": 200, "body": {"use_glb_map": False, "preview_url": "/saved.png"}},
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
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/saved.png", "state_token": "tok-applied"}},
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
    assert res["controlsDisplay"] == ""

  def test_cancel_staging_restores_saved_block_and_frame(self):
    """Cancelling the proposal brings back the saved block and its frame."""
    res = _align([_saved_model_get(), _preview_resp("tok1")], [["upload"], ["cancel"]], geomapReady=True)
    assert res["frameTrail"] == [FRAME_UNAPPLIED, None, FRAME_UNAPPLIED]
    assert res["savedBlockDisplay"] == ""
    assert res["controlsDisplay"] == ""

  def test_toggle_use_writes_applied_scene_fields_to_form(self):
    """Applying the GLB writes the server pose, scale and corners into the scene-edit form."""
    res = _align(
      [_saved_model_get(), {"status": 200, "body": {"use_glb_map": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}}],
      [["toggleUse", True]],
    )
    _assert_form_matches(res["sceneForm"], SCENE_FIELDS_APPLIED)

  def test_toggle_use_round_trip_follows_server_scene_fields(self):
    """Toggling the GLB on then off moves the scene-edit form from the applied to the base values."""
    responses = [
      _saved_model_get(),
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
      {"status": 200, "body": {"use_glb_map": False, "preview_url": "/saved.png", "scene_fields": SCENE_FIELDS_BASE}},
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
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
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
      {"status": 200, "body": {"use_glb_map": True, "preview_url": "/applied.png", "scene_fields": SCENE_FIELDS_APPLIED}},
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


def _assert_form_matches(form, scene_fields):
  """Every scene field returned by the server is written to its scene-edit input."""
  for name, value in scene_fields.items():
    actual = form[f"id_{name}"]
    if name == "map_corners_lla":
      assert (json.loads(actual) if actual else None) == value, name
    else:
      assert actual == (value if value is not None else ""), name


def _element_classes(html, element_id):
  """Return the class tokens of the element with the given id in the template."""
  match = re.search(rf'<div\s[^>]*id="{element_id}"[^>]*>', html)
  if match is None:
    raise ValueError(f"element #{element_id} not found")
  cls = re.search(r'class="([^"]*)"', match.group(0))
  return set(cls.group(1).split()) if cls else set()


def test_proposed_and_saved_panels_share_styling():
  """Proposed-state controls use the same tinted panel classes as the saved block."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  panel = {"p-3", "border", "rounded", "bg-light"}
  assert panel <= _element_classes(html, "glbSavedBlock")
  assert panel <= _element_classes(html, "glbAlignControls")


def test_template_explains_frame_colors_and_heading():
  """The form names both frame colors in text and gives the heading control a tooltip."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  legend = re.search(r'id="glbFrameLegend".*?</small>', html, re.S).group(0)
  assert "green" in legend and "red" in legend
  assert 'id="glbLegendApplied"' in legend and 'id="glbLegendUnapplied"' in legend
  label = re.search(r'<label\s[^>]*for="glbHeadingNumber"[^>]*>', html).group(0)
  assert 'title="' in label


def test_template_passes_upload_limit_to_row():
  """The GLB row carries the server upload limit for the client-side error message."""
  html = _SCENE_UPDATE_TEMPLATE.read_text()
  row = re.search(r'<div\s[^>]*id="glbAlignRow"[^>]*>', html).group(0)
  assert "data-max-upload-bytes=" in row
