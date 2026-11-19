# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene registration must always notify the open calibration page."""

import threading
from unittest.mock import MagicMock, patch

import pytest

import auto_camera_calibration_context as context_module
from auto_camera_calibration_context import CameraCalibrationContext


def _context(strategy):
  ctx = CameraCalibrationContext.__new__(CameraCalibrationContext)
  ctx.register_thread_lock = threading.Lock()
  ctx.current_processing_scene = {"id": "scene-1"}
  ctx.scene_strategies = {"Markerless": strategy}
  ctx.socket_scene_clients = {"scene-1": "sid-1"}
  ctx.socketio = MagicMock()
  return ctx


def _scene():
  return MagicMock(id="scene-1", camera_calibration="Markerless")


@pytest.fixture(autouse=True)
def _inline_tpool():
  with patch.object(context_module.tpool, "execute", side_effect=lambda fn, *a: fn(*a)):
    yield


def test_successful_registration_notifies_client():
  strategy = MagicMock()
  strategy.process_scene_for_calibration.return_value = {"status": "success"}
  ctx = _context(strategy)
  ctx.process_scene(_scene(), True)
  ctx.socketio.emit.assert_called_once_with(
    "register_result", {"scene_id": "scene-1", "data": {"status": "success"}}, to="sid-1")
  assert not ctx.register_thread_lock.locked()
  assert ctx.current_processing_scene == {}


def test_unexpected_registration_failure_notifies_client_with_safe_error():
  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = RuntimeError("/internal/path exploded")
  ctx = _context(strategy)
  ctx.process_scene(_scene(), True)
  ctx.socketio.emit.assert_called_once_with(
    "register_result",
    {"scene_id": "scene-1", "data": {"status": "error", "message": "Scene registration failed"}},
    to="sid-1")
  assert not ctx.register_thread_lock.locked()
  assert ctx.current_processing_scene == {}


def test_tpool_failure_notifies_client_with_error():
  ctx = _context(MagicMock())
  with patch.object(context_module.tpool, "execute", side_effect=OSError("worker pool died")):
    ctx.process_scene(_scene(), True)
  ctx.socketio.emit.assert_called_once_with(
    "register_result",
    {"scene_id": "scene-1", "data": {"status": "error", "message": "Scene registration failed"}},
    to="sid-1")
  assert not ctx.register_thread_lock.locked()
