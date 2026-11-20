# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene registration must always notify the open calibration page."""

import importlib
import sys
import threading
from unittest.mock import MagicMock, call, patch

import pytest


def _import_context_module():
  # The host test venv lacks the service-only runtime (eventlet, hloc/torch); stub only what is missing.
  stubs = {}
  for name in ("eventlet", "markerless_camera_calibration_controller",
               "point_cloud_calibration_controller"):
    try:
      importlib.import_module(name)
    except ImportError:
      stubs[name] = MagicMock()
  with patch.dict(sys.modules, stubs):
    return importlib.import_module("auto_camera_calibration_context")


context_module = _import_context_module()
CameraCalibrationContext = context_module.CameraCalibrationContext


def _context(strategy):
  ctx = CameraCalibrationContext.__new__(CameraCalibrationContext)
  ctx.register_thread_lock = threading.Lock()
  ctx.current_processing_scene = {"id": "scene-1"}
  ctx.scene_strategies = {"Markerless": strategy}
  ctx.socketio = MagicMock()
  return ctx


def _scene():
  return MagicMock(id="scene-1", camera_calibration="Markerless")


@pytest.fixture(autouse=True)
def _inline_tpool():
  with patch.object(context_module.tpool, "execute", side_effect=lambda fn, *a: fn(*a)):
    yield


def _payload(data):
  return {"scene_id": "scene-1", "camera_calibration": "Markerless", "data": data}


def _assert_notified(ctx, final):
  assert ctx.socketio.emit.call_args_list == [
    call("register_result", _payload({"status": "registering"}), to="scene:scene-1"),
    call("register_result", _payload(final), to="scene:scene-1"),
  ]


def test_successful_registration_notifies_client():
  strategy = MagicMock()
  strategy.process_scene_for_calibration.return_value = {"status": "success"}
  ctx = _context(strategy)
  ctx.process_scene(_scene(), True)
  _assert_notified(ctx, {"status": "success"})
  assert not ctx.register_thread_lock.locked()
  assert ctx.current_processing_scene == {}


def test_unexpected_registration_failure_notifies_client_with_safe_error():
  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = RuntimeError("/internal/path exploded")
  ctx = _context(strategy)
  ctx.process_scene(_scene(), True)
  _assert_notified(ctx, {"status": "error", "message": "Scene registration failed"})
  assert not ctx.register_thread_lock.locked()
  assert ctx.current_processing_scene == {}


def test_tpool_failure_notifies_client_with_error():
  ctx = _context(MagicMock())
  with patch.object(context_module.tpool, "execute", side_effect=OSError("worker pool died")):
    ctx.process_scene(_scene(), True)
  _assert_notified(ctx, {"status": "error", "message": "Scene registration failed"})
  assert not ctx.register_thread_lock.locked()


def _register_results(client):
  return [e["args"][0] for e in client.get_received() if e["name"] == "register_result"]


def test_every_page_registered_for_scene_receives_result():
  from auto_camera_calibration_api import CameraCalibrationApi
  ctx = _context(MagicMock())
  api = CameraCalibrationApi(calibrationContext=ctx)
  # e.g. the camera calibration page plus another tab of the same scene opened later
  calibration_page = api.socketio.test_client(api.app)
  other_page = api.socketio.test_client(api.app)
  other_scene_page = api.socketio.test_client(api.app)
  calibration_page.emit("register_scene", {"scene_id": "scene-1"})
  other_page.emit("register_scene", {"scene_id": "scene-1"})
  other_scene_page.emit("register_scene", {"scene_id": "scene-2"})
  for client in (calibration_page, other_page, other_scene_page):
    client.get_received()

  ctx.notify_scene_registration(_scene(), {"status": "success"})

  expected = [_payload({"status": "success"})]
  assert _register_results(calibration_page) == expected
  assert _register_results(other_page) == expected
  assert _register_results(other_scene_page) == []
