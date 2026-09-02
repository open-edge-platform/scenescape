#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for SceneController shared state."""

import concurrent.futures
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controller.child_scene_controller import ChildSceneController
from controller.moving_object import ReidState
from controller.scene_controller import SceneController
from controller.uuid_manager import UUIDManager
import controller.uuid_manager as uuid_manager_mod
from scene_common.mqtt import PubSub

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


def _reid_object(rv_id, category="person"):
  return SimpleNamespace(
    rv_id=rv_id,
    category=category,
    gid=None,
    similarity=None,
    reid_state=ReidState.PENDING_COLLECTION,
    reid=None,
    reid_provenance=None,
    boundingBoxPixels=None,
    chain_data=None,
    when=0.0,
    metadata={},
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


class TestSceneControllerDualMqttStyleConcurrency:
  """Simulate parent MQTT + child MQTT threads hitting shared controller methods."""

  def _build_controller(self):
    controller = SceneController.__new__(SceneController)
    controller.schema_val = MagicMock()
    controller.schema_val.validateMessage.return_value = True
    controller.ntp_server = 'ntp'
    controller.ntp_client = MagicMock()
    controller.last_time_sync = None
    controller.time_offset = 0.0
    controller.max_lag = 3600
    controller.rewrite_all_time = False
    controller.rewrite_bad_time = False
    controller.cache_manager = MagicMock()
    controller.cache_manager.allScenes.return_value = []
    controller.cache_manager.sceneWithID.return_value = None
    controller.cache_manager.sceneWithRemoteChildID.return_value = None
    controller.pubsub = MagicMock()
    controller.subscribed = set()
    controller.subscribed_children = {}
    controller.scenes = []
    controller.external_source_bindings = {}
    controller._handleExternalSourceObject = MagicMock(return_value=True)
    controller._scenesForExternalPublisher = MagicMock(return_value=[])
    controller._handleChildSceneObject = MagicMock(return_value=None)
    controller.publishDetections = MagicMock()
    return controller

  def _external_message(self, scene_id, payload):
    message = MagicMock()
    message.topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=scene_id, thing_type='person')
    message.payload = json.dumps(payload).encode('utf-8')
    return message

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_parent_and_child_handlers_concurrent(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    """Parent ingest + subscription refresh must not race catastrophically."""
    controller = self._build_controller()
    errors = []

    def parent_ingest(i):
      try:
        message = self._external_message(f'drone-{i % 3}', {
          'timestamp': '2026-01-01T00:00:00Z',
          'source_id': f'drone-{i % 3}',
          'objects': [],
        })
        controller.handleMovingObjectMessage(None, None, message)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def child_style_refresh():
      try:
        for _ in range(40):
          controller.updateSubscriptions()
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def echo_drop(i):
      try:
        # Hierarchy echo without source_id; local root scene => early return.
        local = SimpleNamespace(parent=None)
        controller.cache_manager.sceneWithID.return_value = local
        message = self._external_message('scene-root', {
          'timestamp': '2026-01-01T00:00:00Z',
          'objects': [],
        })
        controller.handleMovingObjectMessage(None, None, message)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
      futures = [pool.submit(parent_ingest, i) for i in range(60)]
      futures += [pool.submit(echo_drop, i) for i in range(40)]
      futures += [pool.submit(child_style_refresh) for _ in range(4)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"dual-MQTT style race: {errors}"
    # Negative: updateSubscriptions must leave subscribed containers as sets/dicts.
    assert isinstance(controller.subscribed, set)
    assert isinstance(controller.subscribed_children, dict)


class TestSceneControllerChildMqttTrackerPoolConcurrency:
  """Child MQTT lifecycle × parent ingest × tracker UUIDManager pool."""

  def _build_parent(self, scene):
    controller = SceneController.__new__(SceneController)
    controller.schema_val = MagicMock()
    controller.schema_val.validateMessage.return_value = True
    controller.ntp_server = 'ntp'
    controller.ntp_client = MagicMock()
    controller.last_time_sync = None
    controller.time_offset = 0.0
    controller.max_lag = 3600
    controller.rewrite_all_time = False
    controller.rewrite_bad_time = False
    controller.cache_manager = MagicMock()
    controller.cache_manager.allScenes.return_value = [scene]
    controller.cache_manager.sceneWithID.return_value = None
    controller.cache_manager.sceneWithRemoteChildID.return_value = None
    controller.pubsub = MagicMock()
    controller.subscribed = set()
    controller.subscribed_children = {}
    controller.scenes = [scene]
    controller.external_source_bindings = {}
    controller._handleExternalSourceObject = MagicMock(return_value=True)
    controller._scenesForExternalPublisher = MagicMock(return_value=[scene])
    controller._handleChildSceneObject = MagicMock(return_value=(True, scene))
    controller.publishDetections = MagicMock()
    controller.republishEvents = MagicMock()
    return controller

  def _build_child(self, parent):
    child = ChildSceneController.__new__(ChildSceneController)
    child.child_name = "remote-child"
    child.child_id = "child-1"
    child.child_link_uid = "link-1"
    child.parent_controller = parent
    child.connected = False
    child.remote_config = {}
    child._last_tripwires_json = None
    child._last_rois_json = None
    child.client = MagicMock()
    child.client.subscribe.return_value = (0, 1)
    child.client.unsubscribe.return_value = (0, 1)
    child.child_scene_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=child.child_id, thing_type="+")
    child.child_event_topic = PubSub.formatTopic(
      PubSub.EVENT, region_type="+", event_type="+",
      scene_id=child.child_id, region_id="+")
    return child

  def _external_message(self, scene_id, payload):
    message = MagicMock()
    message.topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=scene_id, thing_type='person')
    message.payload = json.dumps(payload).encode('utf-8')
    return message

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_child_lifecycle_parent_ingest_and_pool(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    """Child connect/disconnect, parent/child ingest, and ReID pool must coexist."""
    database = MagicMock()
    database.findMatches.return_value = []
    database.similarity_metric = 'IP'
    database._schema_ready = True
    with patch('controller.uuid_manager.create_reid_database', return_value=database):
      uuid_manager = UUIDManager()
    uuid_manager.reid_enabled = True
    uuid_manager.reid_write_healthy = True
    embedding = [0.1] * 8
    with uuid_manager.active_ids_lock:
      for i in range(10):
        rv = f"rv-{i}"
        uuid_manager.active_ids[rv] = [None, None]
        uuid_manager.quality_features[rv] = [embedding]
        uuid_manager.quality_observation_counts[rv] = 1

    scene = _scene_with_category_uuid_manager(uuid_manager)
    scene.cameras = []
    scene.tracker.getUniqueIDCount = MagicMock(return_value=0)
    scene.tracker.currentObjects = MagicMock(return_value=[])
    parent = self._build_parent(scene)
    child = self._build_child(parent)
    errors = []

    def child_lifecycle():
      try:
        for _ in range(30):
          child.onChildConnect(child.client, None, {}, 0)
          status = MagicMock()
          status.payload = b"isConnected"
          child.publishStatus(None, None, status)
          child.onChildDisconnect(child.client, None, 0)
          child.loopStart()
          child.loopStop()
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def parent_ingest(i):
      try:
        message = self._external_message(f'drone-{i % 2}', {
          'timestamp': '2026-01-01T00:00:00Z',
          'source_id': f'drone-{i % 2}',
          'objects': [],
        })
        parent.handleMovingObjectMessage(None, None, message)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def child_ingest(i):
      try:
        message = self._external_message('child-1', {
          'timestamp': '2026-01-01T00:00:00Z',
          'objects': [],
        })
        parent.handleMovingObjectMessage(None, None, message)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def pool_query(i):
      try:
        uuid_manager.querySimilarity(_reid_object(f"rv-{i % 10}"))
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)
    def policy_reader():
      try:
        for _ in range(80):
          policy = parent._hierarchyReidPublishPolicy(scene, "person")
          assert policy in ("will_enroll", "withhold", "passthrough")
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
      futures = [pool.submit(child_lifecycle) for _ in range(2)]
      futures += [pool.submit(parent_ingest, i) for i in range(40)]
      futures += [pool.submit(child_ingest, i) for i in range(40)]
      futures += [pool.submit(pool_query, i) for i in range(40)]
      futures += [pool.submit(policy_reader) for _ in range(2)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    uuid_manager.pool.shutdown(wait=True)
    uuid_manager.shutdown()
    assert not errors, f"child MQTT × tracker × pool race: {errors}"
    # Negative: child disconnect must clear connected flag after lifecycle churn.
    assert child.connected is False
