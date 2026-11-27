# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A map update requested while a registration is running must not be dropped."""

import os
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from auto_camera_calibration_api import CameraCalibrationApi
from conftest import import_calibration_context
from markerless_camera_calibration_controller import MarkerlessCameraCalibrationController

context_module = import_calibration_context()
CameraCalibrationContext = context_module.CameraCalibrationContext

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
      scenes=[],
      objects=[],
      first_started=threading.Event(),
      release=threading.Event(),
      done=threading.Event())

  def process(sceneobj, map_update):
    state.calls.append(map_update)
    state.scenes.append(sceneobj.id)
    state.objects.append(sceneobj)
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
    # Native-thread offload is irrelevant here; run the strategy inline in the worker.
    stack.enter_context(
        patch.object(context_module.tpool, "execute", side_effect=lambda fn, *a: fn(*a)))
    markerless = stack.enter_context(
        patch.object(context_module, "MarkerlessCameraCalibrationController"))

    def _make(strategy):
      markerless.return_value = strategy
      ctx = CameraCalibrationContext(cert=None, root_cert=None, rest_url="", rest_auth="")
      ctx.socketio = MagicMock()
      ctx.socketio.start_background_task.side_effect = (
          lambda fn, *args: threading.Thread(target=fn, args=args).start())
      # None means the scene cannot be reloaded, so a queued run keeps its own copy.
      ctx.calibration_data_interface.scene_with_id.return_value = None
      return ctx

    yield _make


def make_scene(scene_id="scene-1", calibration="Markerless"):
  return SimpleNamespace(id=scene_id, name="lab", camera_calibration=calibration)


def test_map_update_during_run_is_rerun_after_run_finishes(make_context):
  """! Positive: a map update posted while a registration runs triggers a re-run. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  scene = make_scene()

  ctx.scene_update_thread_wrapper(scene, map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)

  ctx.scene_update_thread_wrapper(scene, map_update=True, queue_if_busy=True)
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
    ctx.scene_update_thread_wrapper(scene, map_update=True, queue_if_busy=True)
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

  ctx.scene_update_thread_wrapper(make_scene(), map_update=True, reset=True)
  assert state.first_started.wait(WAIT_TIMEOUT)
  ctx.scene_update_thread_wrapper(make_scene(), map_update=True, reset=True, queue_if_busy=True)
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
  ctx.scene_update_thread_wrapper(scene, map_update=True, queue_if_busy=True)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT), f"queued update lost after a failed run, calls={state.calls}"
  wait_until_idle(ctx)
  assert ctx.register_thread_lock.locked() is False
  assert ctx.pending_registrations == {}


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


def run_with_first_scene_blocked(ctx, state, queue_calls, expected_calls):
  """! Start scene 'run', apply queue_calls while it is busy, release it and wait for all runs. """
  ctx.scene_update_thread_wrapper(make_scene("run"), map_update=True)
  assert state.first_started.wait(WAIT_TIMEOUT)
  for call_kwargs in queue_calls:
    ctx.scene_update_thread_wrapper(queue_if_busy=True, **call_kwargs)
  state.release.set()
  assert state.done.wait(WAIT_TIMEOUT), f"queued work was dropped, scenes={state.scenes}"


@pytest.mark.parametrize("queued_ids", [["a", "b"], ["a", "b", "a"]])
def test_queued_updates_run_in_fifo_order(make_context, queued_ids):
  """! Scenes queued while busy run oldest first, and re-queuing a scene keeps its position. """
  strategy, state = make_blocking_strategy(expected_calls=3)
  ctx = make_context(strategy)

  run_with_first_scene_blocked(
      ctx, state, [{"sceneobj": make_scene(i), "map_update": True} for i in queued_ids], 3)

  assert state.scenes == ["run", "a", "b"]


def test_startup_scenes_are_all_processed_in_order(make_context):
  """! preprocess_scenes processes every non-manual scene, one after another, in database order. """
  strategy, state = make_blocking_strategy(expected_calls=3)
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [
      make_scene("a"), make_scene("manual", calibration="Manual"), make_scene("b"), make_scene("c")]

  ctx.preprocess_scenes()
  assert state.first_started.wait(WAIT_TIMEOUT)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT), f"startup scenes were dropped, scenes={state.scenes}"
  assert state.scenes == ["a", "b", "c"]
  assert state.calls == [False, False, False]


def test_wrapper_reports_whether_it_started_the_run(make_context):
  """! The wrapper returns True only when it started a run; a busy, unqueued call returns False. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)

  assert ctx.scene_update_thread_wrapper(make_scene(), map_update=True) is True
  assert state.first_started.wait(WAIT_TIMEOUT)
  assert ctx.scene_update_thread_wrapper(make_scene(), map_update=True) is False
  assert ctx.pending_registrations == {}
  assert ctx.scene_update_thread_wrapper(make_scene(), map_update=True, queue_if_busy=True) is False
  assert len(ctx.pending_registrations) == 1

  state.release.set()
  assert state.done.wait(WAIT_TIMEOUT)


@pytest.mark.parametrize("reset", [False, True])
def test_reset_runs_only_when_requested(make_context, reset):
  """! The strategy resets the scene only for a run that was started with reset=True. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  state.release.set()
  ctx = make_context(strategy)

  ctx.scene_update_thread_wrapper(make_scene(), map_update=True, reset=reset)

  assert state.done.wait(WAIT_TIMEOUT)
  assert strategy.reset_scene.call_count == (1 if reset else 0)


@pytest.mark.parametrize("flags", [(True, False), (False, True)], ids=["reset-first", "reset-last"])
def test_coalesced_entry_keeps_reset_from_either_request(make_context, flags):
  """! A queued request with reset=True merged with one without it still resets the scene. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  queued = [{"sceneobj": make_scene("a"), "map_update": True, "reset": reset} for reset in flags]

  run_with_first_scene_blocked(ctx, state, queued, 2)

  assert strategy.reset_scene.call_count == 1
  assert state.scenes == ["run", "a"]


def test_coalesced_entry_keeps_map_update_from_either_request(make_context):
  """! A startup entry (no map update) merged with a PATCH runs as a map update. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  queued = [{"sceneobj": make_scene("a"), "map_update": False},
            {"sceneobj": make_scene("a"), "map_update": True, "reset": True},
            {"sceneobj": make_scene("a"), "map_update": False}]

  run_with_first_scene_blocked(ctx, state, queued, 2)

  assert state.calls == [True, True]


def test_base_exception_in_strategy_releases_lock(make_context):
  """! Negative: a BaseException ends the worker but still releases the lock for later runs. """
  strategy = MagicMock()
  strategy.process_scene_for_calibration.side_effect = KeyboardInterrupt
  ctx = make_context(strategy)
  assert ctx.register_thread_lock.acquire(blocking=False)

  with pytest.raises(KeyboardInterrupt):
    ctx.process_scene(make_scene(), True, False)
  assert ctx.register_thread_lock.locked() is False

  ran = threading.Event()
  strategy.process_scene_for_calibration.side_effect = lambda *_args: ran.set()
  assert ctx.scene_update_thread_wrapper(make_scene(), map_update=True) is True
  assert ran.wait(WAIT_TIMEOUT)


def test_normal_run_releases_lock_exactly_once(make_context):
  """! Control: a run that ends normally must not release the already released lock again. """
  strategy = MagicMock()
  ctx = make_context(strategy)
  assert ctx.register_thread_lock.acquire(blocking=False)

  ctx.process_scene(make_scene(), True, False)

  assert ctx.register_thread_lock.locked() is False


def test_request_queued_during_refresh_survives_mark_running(make_context):
  """! Positive: a PATCH queued while the next entry is refreshed is run next, not dropped. """
  ctx = make_context(MagicMock())
  old_scene = make_scene()
  new_scene = make_scene()
  assert ctx.register_thread_lock.acquire(blocking=False)
  ctx.pending_registrations[old_scene.id] = (old_scene, True, False)

  def patch_arrives(_scene_id):
    ctx.scene_update_thread_wrapper(new_scene, map_update=True, reset=True, queue_if_busy=True)
    return None

  ctx.calibration_data_interface.scene_with_id.side_effect = patch_arrives
  first = ctx._take_next_queued_request()
  ctx.calibration_data_interface.scene_with_id.side_effect = None
  second = ctx._take_next_queued_request()

  assert first[0] is old_scene
  assert second[0] is new_scene
  assert second[1:] == (True, True)


def test_queued_reset_is_kept_when_map_looks_current(make_context):
  """! Positive: a queued reset runs even when the scene map is not stale. """
  strategy = MagicMock()
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  queued = make_scene()
  reloaded = make_scene()
  ctx.calibration_data_interface.scene_with_id.return_value = reloaded
  assert ctx.register_thread_lock.acquire(blocking=False)
  ctx.pending_registrations[queued.id] = (queued, True, True)

  request = ctx._take_next_queued_request()

  assert request[0] is reloaded
  assert request[1:] == (True, True)


def test_queued_map_update_is_skipped_when_map_is_current(make_context):
  """! Negative: a queued map update without reset is dropped when the map is already processed. """
  strategy = MagicMock()
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  queued = make_scene()
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene()
  assert ctx.register_thread_lock.acquire(blocking=False)
  ctx.pending_registrations[queued.id] = (queued, True, False)

  assert ctx._take_next_queued_request() is None
  assert ctx.register_thread_lock.locked() is False


def make_markerless_scene_with_output(tmp_path, monkeypatch):
  """! Real markerless strategy (registration mocked) and a scene with an existing output_dir. """
  monkeypatch.chdir(tmp_path)
  output_dir = tmp_path / "datasets" / "Queuing" / "output_dir"
  output_dir.mkdir(parents=True)
  (output_dir / "features.h5").write_bytes(b"features")
  done = threading.Event()
  strategy = MarkerlessCameraCalibrationController(calibration_data_interface=MagicMock())
  strategy.process_scene_for_calibration = MagicMock(side_effect=lambda *_args: done.set())
  strategy.is_map_updated = MagicMock(return_value=True)
  return strategy, output_dir, done


def test_post_keeps_existing_output_dir(make_api, tmp_path, monkeypatch):
  """! POST registers the scene without resetting it, so existing markerless output survives. """
  strategy, output_dir, done = make_markerless_scene_with_output(tmp_path, monkeypatch)
  client, _ctx, scene = make_api(strategy)
  scene.output_dir = str(output_dir)

  assert client.post(REGISTRATION_URL).status_code == 202

  assert done.wait(WAIT_TIMEOUT)
  assert (output_dir / "features.h5").exists()


def test_patch_resets_existing_output_dir(make_api, tmp_path, monkeypatch):
  """! PATCH still starts from a clean scene, removing the markerless output. """
  strategy, output_dir, done = make_markerless_scene_with_output(tmp_path, monkeypatch)
  client, _ctx, scene = make_api(strategy)
  scene.output_dir = str(output_dir)

  assert client.patch(REGISTRATION_URL).status_code == 202

  assert done.wait(WAIT_TIMEOUT)
  assert not output_dir.exists()


def test_post_response_comes_from_wrapper_result(make_api):
  """! POST reports busy when the wrapper did not start the run, whatever the lock state says. """
  strategy, _state = make_blocking_strategy(expected_calls=1)
  strategy.is_map_updated.return_value = True
  client, ctx, scene = make_api(strategy)

  with patch.object(ctx, "scene_update_thread_wrapper", return_value=False) as wrapper:
    response = client.post(REGISTRATION_URL)

  wrapper.assert_called_once_with(scene, map_update=True, reset=False, queue_if_busy=True)
  assert response.status_code == 200
  assert response.get_json()["status"] == "busy"
  assert ctx.register_thread_lock.locked() is False


def test_post_started_returns_202_registering(make_api):
  """! POST on an idle service starts the run and answers 202 'registering'. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  state.release.set()
  strategy.is_map_updated.return_value = True
  client, _ctx, _scene = make_api(strategy)

  response = client.post(REGISTRATION_URL)

  assert response.status_code == 202
  assert response.get_json()["status"] == "registering"
  assert response.get_json()["message"] == "Registration started"
  assert state.done.wait(WAIT_TIMEOUT)


def test_post_during_own_run_reports_progress_and_queues_without_reset(make_api):
  """! POST for the scene being registered reports progress, and the update runs afterwards without a reset. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_updated.return_value = True
  client, ctx, _scene = make_api(strategy)

  assert client.patch(REGISTRATION_URL).status_code == 202
  assert state.first_started.wait(WAIT_TIMEOUT)
  resets_after_patch = strategy.reset_scene.call_count
  response = client.post(REGISTRATION_URL)

  assert response.status_code == 202
  assert response.get_json()["status"] == "registering"
  assert response.get_json()["message"] == "Registration is in progress"
  assert len(ctx.pending_registrations) == 1

  state.release.set()
  assert state.done.wait(WAIT_TIMEOUT), f"POST during a run was dropped, calls={state.calls}"
  assert strategy.reset_scene.call_count == resets_after_patch


def test_startup_runs_map_update_only_for_stale_scenes(make_context):
  """! preprocess_scenes re-registers a scene whose map changed and only validates the others. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.side_effect = lambda scene: scene.id == "changed"
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [make_scene("changed"), make_scene("same")]

  ctx.preprocess_scenes()
  assert state.first_started.wait(WAIT_TIMEOUT)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT)
  assert dict(zip(state.scenes, state.calls)) == {"changed": True, "same": False}


def test_startup_check_is_side_effect_free(make_context):
  """! Startup uses the predicate-only check and never resets a scene. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  state.release.set()
  strategy.is_map_stale.return_value = True
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [make_scene("a")]

  ctx.preprocess_scenes()

  assert state.done.wait(WAIT_TIMEOUT)
  strategy.is_map_updated.assert_not_called()
  strategy.reset_scene.assert_not_called()


def test_startup_staleness_failure_does_not_stop_other_scenes(make_context):
  """! Negative: a scene whose staleness cannot be checked is processed as unchanged, and the rest still run. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.side_effect = FileNotFoundError("polycam zip is gone")
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [make_scene("a"), make_scene("b")]

  ctx.preprocess_scenes()
  assert state.first_started.wait(WAIT_TIMEOUT)
  state.release.set()

  assert state.done.wait(WAIT_TIMEOUT)
  assert state.scenes == ["a", "b"]
  assert state.calls == [False, False]


def make_markerless_scene_on_disk(tmp_path, polycam_age):
  """! Scene processed 100 s ago, whose polycam zip was written polycam_age seconds ago. """
  map_path = tmp_path / "box.glb"
  polycam_path = tmp_path / "poly.zip"
  map_path.write_bytes(b"map")
  polycam_path.write_bytes(b"zip")
  now = time.time()
  os.utime(map_path, (now - 1000, now - 1000))
  os.utime(polycam_path, (now - polycam_age, now - polycam_age))
  scene = make_scene("markerless-scene")
  scene.map = str(map_path)
  scene.polycam_data = str(polycam_path)
  scene.map_processed = datetime.fromtimestamp(now - 100, tz=timezone.utc)
  return scene


@pytest.mark.parametrize("polycam_age,expected", [(10, True), (500, False)],
                         ids=["changed-while-down", "unchanged"])
def test_startup_detects_polycam_changed_while_service_was_down(make_context, tmp_path,
                                                                polycam_age, expected):
  """! With the real markerless check, only a zip newer than the last run is re-registered at startup. """
  scene = make_markerless_scene_on_disk(tmp_path, polycam_age)
  done = threading.Event()
  calls = []
  strategy = MarkerlessCameraCalibrationController(calibration_data_interface=MagicMock())
  strategy.process_scene_for_calibration = MagicMock(
      side_effect=lambda _scene, map_update: (calls.append(map_update), done.set()))
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [scene]

  ctx.preprocess_scenes()

  assert done.wait(WAIT_TIMEOUT)
  assert calls == [expected]


def test_queued_run_uses_the_reloaded_scene(make_context):
  """! A queued request runs with the scene as stored now, not as it was when it was queued. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.return_value = True
  ctx = make_context(strategy)
  reloaded = make_scene("a")
  ctx.calibration_data_interface.scene_with_id.return_value = reloaded

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": True}], 2)

  assert state.objects[1] is reloaded


def test_queued_map_update_already_processed_is_skipped(make_context):
  """! A queued map update the previous run already processed does not run again. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene("run")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("run"), "map_update": True}], 1)
  wait_until_idle(ctx)

  assert state.calls == [True]
  strategy.reset_scene.assert_not_called()
  assert ctx.register_thread_lock.locked() is False


def test_queued_map_update_still_stale_runs(make_context):
  """! Control: a queued map update whose map is newer than the last run still runs. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.return_value = True
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene("a")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": True}], 2)

  assert state.scenes == ["run", "a"]


def test_queued_startup_validation_is_not_skipped_when_map_is_current(make_context):
  """! A queued request without a map update is a validation run, so it is never skipped. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene("a")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": False}], 2)

  assert state.calls == [True, False]


def test_skipped_queued_entry_still_lets_the_next_one_run(make_context):
  """! Negative: skipping one stale-free entry must not stall or lose the entries behind it. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.side_effect = lambda scene: scene.id == "b"
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.side_effect = lambda scene_id: make_scene(scene_id)
  queued = [{"sceneobj": make_scene("a"), "map_update": True},
            {"sceneobj": make_scene("b"), "map_update": True}]

  run_with_first_scene_blocked(ctx, state, queued, 2)
  wait_until_idle(ctx)

  assert state.scenes == ["run", "b"]
  assert ctx.register_thread_lock.locked() is False


def test_queued_entry_runs_with_queued_copy_when_reload_fails(make_context):
  """! Negative: a failing reload must not drop the queued update. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.side_effect = ConnectionError("manager down")
  queued_scene = make_scene("a")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": queued_scene, "map_update": True}], 2)

  assert state.objects[1] is queued_scene


def test_queued_update_runs_when_map_check_raises(make_context):
  """! Positive: a queued map update whose staleness check raises is retained and runs. """
  strategy, state = make_blocking_strategy(expected_calls=2)
  strategy.is_map_stale.side_effect = PermissionError("polycam zip unreadable")
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene("a")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": True}], 2)

  assert state.scenes == ["run", "a"]
  assert state.calls == [True, True]


def test_queued_update_with_missing_strategy_is_retained_and_reports_error(make_context):
  """! Negative: a queued update whose scene has no strategy is not dropped; its run reports an error. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  ctx = make_context(strategy)
  ctx.calibration_data_interface.scene_with_id.return_value = make_scene("a", calibration="Unknown")

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": True}], 1)
  wait_until_idle(ctx)

  assert state.scenes == ["run"]
  assert ctx.registration_results["a"]["status"] == "error"


def test_queued_map_update_is_skipped_when_reloaded_check_says_current(make_context):
  """! Negative: a queued map update is skipped only when the reloaded scene's check says it is current. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  strategy.is_map_stale.return_value = False
  ctx = make_context(strategy)
  reloaded = make_scene("a")
  ctx.calibration_data_interface.scene_with_id.return_value = reloaded

  run_with_first_scene_blocked(ctx, state, [{"sceneobj": make_scene("a"), "map_update": True}], 1)
  wait_until_idle(ctx)

  strategy.is_map_stale.assert_called_once_with(reloaded)
  assert state.scenes == ["run"]


def test_startup_map_check_failure_is_not_stale(make_context):
  """! Negative: at startup a scene whose staleness check raises is validated, not re-registered. """
  strategy, state = make_blocking_strategy(expected_calls=1)
  strategy.is_map_stale.side_effect = PermissionError("polycam zip unreadable")
  state.release.set()
  ctx = make_context(strategy)
  ctx.calibration_data_interface.all_scenes.return_value = [make_scene("a")]

  ctx.preprocess_scenes()

  assert state.done.wait(WAIT_TIMEOUT)
  assert state.calls == [False]
