# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Apply all GLBs switch in js/geospatial/apply-all-glbs.js.

The switch PUTs the requested state, reloads on success, and on any failure reverts the
checkbox and shows the server message. Its state is server-side, so nothing is kept in
browser storage.
"""

import json
import subprocess
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parent / "apply_all_harness.js"
_SCRIPT = (
  Path(__file__).resolve().parents[3]
  / "manager" / "src" / "manager" / "static" / "js" / "geospatial" / "apply-all-glbs.js"
)
_URL = "/api/v1/scene/1/geospatial-glbs/apply-all"


def run_switch(checked, click, response=None, csrf="tok"):
  """Click the switch in a fake page; returns the sent requests and the final page state."""
  scenario = {
    "url": _URL,
    "checked": checked,
    "click": click,
    "response": response or {"status": 200, "body": {"glb_apply_all": click}},
    "csrf": csrf,
  }
  proc = subprocess.run(
    ["node", str(_HARNESS)], input=json.dumps(scenario), capture_output=True, text=True, timeout=30)
  if proc.returncode != 0:
    raise RuntimeError(f"Harness exit {proc.returncode}: {proc.stderr}")
  out = json.loads(proc.stdout)
  assert "unexpected" not in out, out.get("unexpected")
  return out


@pytest.mark.usefixtures("node_runtime")
class TestApplyAllGlbsSwitch:
  """The switch sends the new state and reconciles the page with the server result."""

  def test_turning_on_sends_put_with_apply_true_and_reloads(self):
    """ON: one PUT with apply=true and the CSRF header; the switch is locked while sending."""
    out = run_switch(checked=False, click=True)

    assert out["sent"] == [{
      "url": _URL,
      "method": "PUT",
      "headers": {"X-CSRFToken": "tok", "Content-Type": "application/json"},
      "body": '{"apply":true}',
      "toggleDisabledWhileSending": True,
    }]
    assert out["reloads"] == 1
    assert out["alerts"] == []
    assert out["checked"] is True
    assert out["disabled"] is False

  def test_turning_off_sends_put_with_apply_false_and_reloads(self):
    """OFF: one PUT with apply=false, then the page reloads."""
    out = run_switch(checked=True, click=False, response={"status": 200, "body": {"glb_apply_all": False}})

    assert [s["body"] for s in out["sent"]] == ['{"apply":false}']
    assert out["reloads"] == 1
    assert out["checked"] is False

  def test_server_rejection_reverts_switch_and_shows_message(self):
    """Failure: the switch goes back to its previous state, the server message is shown, no reload."""
    out = run_switch(
      checked=False, click=True,
      response={"status": 400, "body": {"error": "Scene has no base map"}})

    assert len(out["sent"]) == 1
    assert out["checked"] is False
    assert out["alerts"] == ["Apply all GLBs failed: Scene has no base map"]
    assert out["reloads"] == 0
    assert out["disabled"] is False

  def test_failed_turn_off_reverts_to_on(self):
    """Failure when turning OFF: the switch is restored to ON."""
    out = run_switch(
      checked=True, click=False,
      response={"status": 500, "body": {}})

    assert out["checked"] is True
    assert out["alerts"] == ["Apply all GLBs failed: Request failed (500)"]
    assert out["reloads"] == 0
    assert out["disabled"] is False

  def test_network_failure_reverts_switch_and_shows_message(self):
    """No silent failure: a dropped connection reverts the switch and is reported."""
    out = run_switch(
      checked=False, click=True,
      response={"networkError": "Failed to fetch"})

    assert out["checked"] is False
    assert out["alerts"] == ["Apply all GLBs failed: Failed to fetch"]
    assert out["reloads"] == 0

  def test_missing_csrf_token_sends_nothing_and_reverts(self):
    """Without a CSRF token the PUT is not sent and the switch is reverted."""
    out = run_switch(checked=False, click=True, csrf=None)

    assert out["sent"] == []
    assert out["checked"] is False
    assert out["alerts"] == ["Apply all GLBs failed: CSRF token not found"]
    assert out["reloads"] == 0

  def test_script_keeps_no_browser_state(self):
    """The switch is not persisted in the browser; the stored server value is the only state."""
    source = _SCRIPT.read_text()
    assert "localStorage" not in source
    assert "sessionStorage" not in source
