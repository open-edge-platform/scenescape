#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for SceneController shared state."""

import concurrent.futures
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controller.scene_controller import SceneController
from controller.uuid_manager import UUIDManager
import controller.uuid_manager as uuid_manager_mod

TEST_NAME = "NEX-T28255"


@pytest.fixture(autouse=True)
def clear_purge_owner():
  yield
  with uuid_manager_mod._PURGE_OWNER_LOCK:
    uuid_manager_mod._PURGE_OWNER = None


def _scene_with_category_uuid_manager(uuid_manager, category="person"):
  category_tracker = SimpleNamespace(uuid_manager=uuid_manager)
  tracker = SimpleNamespace(
    uuid_manager=MagicMock(),
    trackers={category: category_tracker},
  )
  return SimpleNamespace(
    tracker=tracker,
    reid_config_data={},
    uid="scene-1",
    name="scene-1",
  )


class TestSceneControllerHierarchyConcurrency:
  def test_track_has_reid_enrollment_under_map_churn(self):
    """Hierarchy enrollment checks must tolerate concurrent map mutations."""
    scene_controller = SceneController.__new__(SceneController)
    with patch('controller.uuid_manager.create_reid_database', return_value=MagicMock()):
      uuid_manager = UUIDManager()
    scene = _scene_with_category_uuid_manager(uuid_manager)
    errors = []

    def mutator():
      try:
        for i in range(400):
          track_id = f"rv-{i % 20}"
          with uuid_manager.active_ids_lock:
            if i % 2 == 0:
              uuid_manager.quality_features[track_id] = [[0.1]]
              uuid_manager.active_ids[track_id] = [None, None]
            else:
              uuid_manager.quality_features.pop(track_id, None)
              uuid_manager.features_for_database[track_id] = {
                "reid_vectors": [[0.2]]}
              uuid_manager.active_ids.pop(track_id, None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for i in range(400):
          obj = SimpleNamespace(rv_id=f"rv-{i % 20}", category="person")
          result = scene_controller._trackHasReidEnrollment(scene, obj)
          assert isinstance(result, bool)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=mutator) for _ in range(2)] + [
      threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    uuid_manager.shutdown()
    assert not errors, f"_trackHasReidEnrollment race: {errors}"

  def test_hierarchy_policy_under_write_health_churn(self):
    """Policy readers must stay consistent while write-health flags flip."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True,
      reid_database=database,
      reid_write_healthy=True,
      reid_write_confirmed=False,
      reid_empty_batch_before_confirm=False,
    )
    scene = _scene_with_category_uuid_manager(uuid_manager)
    errors = []
    policies = []

    def flipper():
      try:
        for i in range(500):
          uuid_manager.reid_enabled = (i % 2 == 0)
          uuid_manager.reid_write_healthy = (i % 3 != 0)
          uuid_manager.reid_write_confirmed = (i % 4 == 0)
          uuid_manager.reid_empty_batch_before_confirm = (i % 5 == 0)
          database._schema_ready = (i % 6 != 0)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(500):
          # Patch write-intent true so policy exercises health/schema branches.
          scene_controller._sceneHasReidWriteIntent = lambda: True
          policy = scene_controller._hierarchyReidPublishPolicy(scene, "person")
          assert policy in ("will_enroll", "withhold", "passthrough")
          policies.append(policy)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
      futures = [pool.submit(flipper)]
      futures += [pool.submit(reader) for _ in range(4)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"hierarchy policy race: {errors}"
    assert policies, "policy reader produced no samples"
    # Negative: unknown category with empty trackers falls back safely.
    empty_scene = SimpleNamespace(
      tracker=SimpleNamespace(uuid_manager=uuid_manager, trackers={}),
      reid_config_data={},
    )
    scene_controller._sceneHasReidWriteIntent = lambda: True
    assert scene_controller._hierarchyReidPublishPolicy(
      empty_scene, "missing") in ("will_enroll", "withhold", "passthrough")

  def test_concurrent_trackers_dict_lookup_during_mutation(self):
    """Unlocked trackers.get used by hierarchy policy must not raise on churn."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller._sceneHasReidWriteIntent = lambda: True
    uuid_manager = SimpleNamespace(
      reid_enabled=True,
      reid_database=SimpleNamespace(_schema_ready=True),
      reid_write_healthy=True,
      reid_write_confirmed=True,
      reid_empty_batch_before_confirm=False,
    )
    tracker = SimpleNamespace(uuid_manager=MagicMock(), trackers={})
    scene = SimpleNamespace(tracker=tracker, reid_config_data={})
    errors = []

    def mutator():
      try:
        for i in range(600):
          if i % 2 == 0:
            tracker.trackers["person"] = SimpleNamespace(uuid_manager=uuid_manager)
          else:
            tracker.trackers.pop("person", None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(600):
          policy = scene_controller._hierarchyReidPublishPolicy(scene, "person")
          assert policy in ("will_enroll", "withhold", "passthrough")
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=mutator),
               threading.Thread(target=reader),
               threading.Thread(target=reader)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"trackers dict race: {errors}"
