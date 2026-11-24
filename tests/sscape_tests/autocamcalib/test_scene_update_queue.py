# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A map update requested while a registration is running must not be dropped."""

import threading
import time
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import auto_camera_calibration_context as context_module
from auto_camera_calibration_api import CameraCalibrationApi
from auto_camera_calibration_context import CameraCalibrationContext

WAIT_TIMEOUT = 5
SETTLE_SECONDS = 0.1
SCENE_ID = "5512a5de-632d-4109-95f9-b200b5a054c8"
MISSING_ID = "00000000-0000-4000-8000-000000000000"


def make_blocking_strategy(expected_calls):
  """! Strategy whose first run blocks until released.

  @param   expected_calls  number of runs after which `done` is set.
  @return  (strategy mock, state namespace with calls, first_started, release, done).
  """
  state = SimpleNamespace(
      calls=[],
      first_started=threading.Event(),
      release=threading.Event(),
      done=threading.Event())

  def process(_sceneobj, map_update):
    state.calls.append(map_update)
    if len(state.calls) == 1:
      state.first_started.set()
      state.release.wait(WAIT_TIMEOUT)
    if len(state.calls) == expected_calls:
      state.done.set()
    return {}

  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = process
  return strategy, state


@pytest.fixture
def make_context():
  """! Factory building a CameraCalibrationContext with the given Markerless strategy. """
  with ExitStack() as stack:
    stack.enter_context(patch.object(CameraCalibrationContext, "scene_strategies", {}))
    stack.enter_context(patch.object(context_module, "CameraCalibrationModel"))
    stack.enter_context(patch.object(context_module, "ApriltagCameraCalibrationController"))
    stack.enter_context(patch.object(context_module, "PointCloudCalibrationController"))
    markerless = stack.enter_context(
        patch.object(context_module, "MarkerlessCameraCalibrationController"))

    def _make(strategy):
      markerless.return_value = strategy
      return CameraCalibrationContext(cert=None, root_cert=None, rest_url="", rest_auth="")

    yield _make


def make_scene():
  return SimpleNamespace(id="scene-1", name="lab", camera_calibration="Markerless")


def test_map_update_during_run_is_rerun_after_run_finishes(make_context):
  """! Positive: a map update posted while a registration runs triggers a re-run. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  scene = make_scene()

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT), f"queued map update was dropped, calls={state.calls}"
  assert state.calls == [True, True]


def test_repeated_map_updates_during_run_coalesce_into_one_rerun(make_context):
  """! Boundary: several map updates for one scene during a run yield exactly one re-run. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  scene = make_scene()

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)

  for _ in range(3):
    ctx.scene_update_thread_wrapper(scene, map_update=True)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT)
  time.sleep(SETTLE_SECONDS)
  assert state.calls == [True, True]


def test_non_map_update_during_run_is_still_skipped(make_context):
  """! Negative: a non-map update posted during a run is not queued. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  ctx = make_context(strategy)
  scene = make_scene()

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)

  ctx.scene_update_thread_wrapper(scene, map_update=False)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT)
  time.sleep(SETTLE_SECONDS)
  assert state.calls == [True]


def test_map_update_on_idle_lock_runs_immediately(make_context):
  """! Control: with no registration running, a map update starts exactly one run. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  state.release.set()
  ctx = make_context(strategy)

  ctx.scene_update_thread_wrapper(make_scene(), map_update=True)

  assert state.done.wait(WAIT_TIMEOUT)
  time.sleep(SETTLE_SECONDS)
  assert state.calls == [True]


def wait_until_idle(ctx):
  """! Wait for the registration lock to be released, then let the thread settle. """
  deadline = time.time() + WAIT_TIMEOUT
  while ctx.register_thread_lock.locked() and time.time() < deadline:
    time.sleep(0.02)
  time.sleep(SETTLE_SECONDS)


def test_reset_runs_under_lock_before_each_map_update_run(make_context):
  """! Each map-update run resets the scene while register_thread_lock is held. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  resets = []
  strategy.reset_scene.side_effect = lambda _scene: resets.append(ctx.register_thread_lock.locked())

  ctx.scene_update_thread_wrapper(make_scene(), map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)
  ctx.scene_update_thread_wrapper(make_scene(), map_update=True)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT)
  wait_until_idle(ctx)
  assert resets == [True, True]


def test_accepted_map_update_holds_lock_before_worker_thread_runs(make_context):
  """! An accepted map update holds the registration lock, even when the worker does not take it. """
  strategy, _state = make_blocking_strategy(expected_calls=1)
  ctx = make_context(strategy)
  worker_ran = threading.Event()

  with patch.object(CameraCalibrationContext, "process_scene", side_effect=lambda *a: worker_ran.set()):
    ctx.scene_update_thread_wrapper(make_scene(), map_update=True)
    assert worker_ran.wait(WAIT_TIMEOUT)
    assert ctx.register_thread_lock.locked() is True

  ctx.register_thread_lock.release()


def test_failed_run_still_runs_queued_update_and_releases_lock(make_context):
  """! Negative: a failing run must not drop the queued update or leave the lock held. """
  state = SimpleNamespace(calls=[], first_started=threading.Event(), release=threading.Event(),
                          done=threading.Event())

  def process(_sceneobj, map_update):
    state.calls.append(map_update)
    if len(state.calls) == 1:
      state.first_started.set()
      state.release.wait(WAIT_TIMEOUT)
      raise RuntimeError("registration failed")
    state.done.set()
    return {}

  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = process
  ctx = make_context(strategy)
  scene = make_scene()

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)
  ctx.scene_update_thread_wrapper(scene, map_update=True)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT), f"queued update lost after a failed run, calls={state.calls}"
  wait_until_idle(ctx)
  assert ctx.register_thread_lock.locked() is False
  assert ctx.pending_map_updates == {}


def test_failed_run_with_empty_queue_releases_lock(make_context):
  """! Negative: a failing run with nothing queued frees the lock so a later update is accepted. """
  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = RuntimeError("registration failed")
  ctx = make_context(strategy)

  ctx.scene_update_thread_wrapper(make_scene(), map_update=True)
  wait_until_idle(ctx)
  assert ctx.register_thread_lock.locked() is False

  strategy.process_scene_for_calibration.side_effect = None
  ctx.scene_update_thread_wrapper(make_scene(), map_update=True)
  wait_until_idle(ctx)
  assert strategy.process_scene_for_calibration.call_count == 2


def make_api_scene():
  """! Scene returned by the data interface for the PATCH and GET tests. """
  return SimpleNamespace(id=SCENE_ID, name="Queuing", camera_calibration="Markerless",
                         map="/tmp/box.glb", polycam_data="/tmp/poly.zip", map_processed=None)


@pytest.fixture
def make_api(make_context):
  """! Factory returning (test client, context, scene) for the REST handlers. """
  def _make(strategy):
    ctx = make_context(strategy)
    scene = make_api_scene()
    ctx.calibration_data_interface.scene_with_id.side_effect = (
        lambda scene_id: scene if scene_id == SCENE_ID else None)
    api = CameraCalibrationApi(calibrationContext=ctx)
    return api.app.test_client(), ctx, scene
  return _make


REGISTRATION_URL = f"/v1/scenes/{SCENE_ID}/registration"


def test_patch_during_run_does_not_reset_scene_synchronously(make_api):
  """! PATCH while a run is active must not reset the scene from the request thread. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_updated.return_value = True
  client, _ctx, _scene = make_api(strategy)

  assert client.patch(REGISTRATION_URL).status_code == 202
  assert state.first_started.wait(WAIT_TIMEOUT)
  resets_before = strategy.reset_scene.call_count

  assert client.patch(REGISTRATION_URL).status_code == 202
  assert strategy.reset_scene.call_count == resets_before

  state.release.set()
  assert state.done.wait(WAIT_TIMEOUT)


def test_get_unknown_scene_returns_404(make_api):
  """! Negative: GET for a scene the manager does not know returns 404. """
  strategy, _state = make_blocking_strategy(expected_calls=1)
  client, _ctx, _scene = make_api(strategy)

  response = client.get(f"/v1/scenes/{MISSING_ID}/registration")
  assert response.status_code == 404
