# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Isolated configuration/geometry lifecycle regression tests."""

import json
import struct
import threading
from unittest.mock import Mock, patch

import pytest
from grpc_health.v1 import health_pb2

from observation_processor.scene_provider import SceneMeshMissingError, SceneProvider, StoreUnavailableError
from observation_processor.server import (
  SERVICE_NAME, _probe_readiness, start_database_watcher, start_readiness_monitor,
)


@pytest.fixture
def configuration():
  """Mock REST, mesh I/O and reasoner baking without live services."""
  scene = {"uid": "scene", "map": "/media/map.glb"}
  camera = {
    "uid": "camera", "intrinsics": {"fx": 10, "fy": 10, "cx": 5, "cy": 5},
    "translation": [0, 0, 0], "rotation": [0, 0, 0], "resolution": [10, 10],
  }
  scenes = Mock(statusCode=200)
  scenes.get.return_value = [scene]
  rest = Mock()
  rest.getScenes.return_value = scenes
  rest.getCameras.return_value = Mock(statusCode=200)
  rest.getCameras.return_value.get.return_value = [camera]
  rest.getAssets.return_value = Mock(statusCode=200)
  rest.getAssets.return_value.get.return_value = []
  with patch("observation_processor.scene_provider.RESTClient", return_value=rest), \
       patch.object(SceneProvider, "_load_world_mesh", side_effect=lambda scene: object()) as load, \
       patch("observation_conditioning.AmodalReasoner") as reasoner:
    yield SceneProvider(), rest, scene, camera, load, reasoner


def test_startup_preloads_geometry_and_first_access_is_cached(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  assert provider.needs_refresh
  assert _probe_readiness(provider, False)
  assert not provider.needs_refresh
  load.assert_called_once_with(scene)
  reasoner.assert_called_once()
  rest.reset_mock()
  provider.get_world_mesh("scene")
  assert provider.get_reasoner("scene", "camera") is reasoner.return_value
  assert load.call_count == reasoner.call_count == 1
  rest.getScene.assert_not_called()
  rest.getCameras.assert_not_called()


def test_refresh_replaces_mesh_at_same_url_and_reasoner(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  first = provider.get_world_mesh("scene")
  provider.invalidate()
  assert _probe_readiness(provider, True)
  assert provider.get_world_mesh("scene") is not first
  assert load.call_count == reasoner.call_count == 2


def test_non_mesh_scene_does_not_load_geometry(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  scene["map"] = "/media/map.png"
  provider.warm()
  assert not provider.needs_refresh
  load.assert_not_called()
  reasoner.assert_not_called()


def test_uncalibrated_camera_does_not_prevent_mesh_warmup(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  camera.pop("intrinsics")
  provider.warm()
  assert not provider.needs_refresh
  load.assert_called_once()
  reasoner.assert_not_called()


@pytest.mark.parametrize("error", [
  SceneMeshMissingError("invalid mesh"), StoreUnavailableError("offline"),
  OSError("unreadable mesh"), ValueError("invalid geometry"), RuntimeError("bake failed"),
])
def test_failed_refresh_keeps_previous_snapshot_and_retries(configuration, error):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.get_world_mesh("scene")
  provider.invalidate()
  load.side_effect = error
  assert not _probe_readiness(provider, True)
  assert provider.needs_refresh
  assert provider.get_world_mesh("scene") is previous
  load.side_effect = lambda scene: object()
  assert _probe_readiness(provider, False)
  assert provider.get_world_mesh("scene") is not previous


def test_event_during_refresh_discards_obsolete_snapshot(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.get_world_mesh("scene")
  provider.invalidate()

  def update_during_load(scene):
    provider.invalidate()
    return object()

  load.side_effect = update_during_load
  assert not _probe_readiness(provider, True)
  assert provider.needs_refresh
  assert provider.get_world_mesh("scene") is previous
  load.side_effect = lambda scene: object()
  assert _probe_readiness(provider, False)


def test_deleted_scenes_remove_cached_geometry(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  rest.getScenes.return_value.get.return_value = []
  provider.invalidate()
  provider.warm()
  assert not provider.needs_refresh
  assert not provider._world_meshes
  assert not provider._reasoners
  assert ("scene", "scene") not in provider._cache


def test_inflight_fetch_cannot_write_into_replacement_snapshot():
  provider = SceneProvider()

  def fetch():
    with provider._lock:
      provider._cache = {("scene", "scene"): "new"}
    return "old"

  assert provider._cached("scene", "scene", fetch) == "old"
  assert provider._cache[("scene", "scene")] == "new"


@pytest.mark.parametrize("already_ready", [False, True])
def test_monitor_marks_not_serving_until_refresh_finishes(configuration, already_ready):
  provider, rest, scene, camera, load, reasoner = configuration
  if already_ready:
    provider.warm()
    provider.invalidate()
  stop = threading.Event()
  health = Mock()
  observed_statuses = []

  def load_mesh(scene):
    observed_statuses.extend(call.args[1] for call in health.set.call_args_list)
    stop.set()
    return object()

  load.side_effect = load_mesh
  thread = start_readiness_monitor(provider, health, interval=0.01, stop_event=stop)
  thread.join(timeout=5)
  assert not thread.is_alive()
  assert observed_statuses == [health_pb2.HealthCheckResponse.NOT_SERVING]
  health.set.assert_called_with(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)


def test_database_events_schedule_refresh_without_loading_on_mqtt_thread(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  stop = threading.Event()
  with patch("observation_processor.server.PubSub") as pubsub_class:
    pubsub = pubsub_class.return_value
    pubsub.loopStart.side_effect = stop.set
    start_database_watcher(provider, "broker", "auth", "cert", stop_event=stop)
    assert stop.wait(5)
    pubsub.onConnect(None, None, None, 0)
    assert provider.needs_refresh
    assert _probe_readiness(provider, True)
    on_change = pubsub.addCallback.call_args.args[1]
    on_change(None, None, Mock(payload=b"ignored"))
    assert not provider.needs_refresh
    on_change(None, None, Mock(payload=b"update"))
    assert provider.needs_refresh
    assert load.call_count == 2
    assert _probe_readiness(provider, True)
    assert load.call_count == 3


def _write_plane_glb(path, height):
  """Write a minimal self-contained GLB without an exporter dependency."""
  binary = struct.pack("<12f6I", -2, -2, height, 2, -2, height,
                       2, 2, height, -2, 2, height, 0, 1, 2, 0, 2, 3)
  document = {
    "asset": {"version": "2.0"},
    "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
    "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
    "buffers": [{"byteLength": len(binary)}],
    "bufferViews": [
      {"buffer": 0, "byteOffset": 0, "byteLength": 48, "target": 34962},
      {"buffer": 0, "byteOffset": 48, "byteLength": 24, "target": 34963},
    ],
    "accessors": [
      {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3",
       "min": [-2, -2, height], "max": [2, 2, height]},
      {"bufferView": 1, "componentType": 5125, "count": 6, "type": "SCALAR"},
    ],
  }
  metadata = json.dumps(document).encode()
  metadata += b" " * (-len(metadata) % 4)
  chunks = struct.pack("<I4s", len(metadata), b"JSON") + metadata
  chunks += struct.pack("<I4s", len(binary), b"BIN\x00") + binary
  path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks)


def test_real_mesh_and_depth_map_are_ready_before_first_access(tmp_path):
  """Exercise GLB decoding, mesh transform and actual Open3D depth baking."""
  import numpy as np

  path = tmp_path / "map.glb"
  _write_plane_glb(path, 0)
  scene = {"uid": "scene", "map": "/media/map.glb"}
  camera = {
    "uid": "camera", "intrinsics": {"fx": 10, "fy": 10, "cx": 5, "cy": 5},
    "translation": [0, 0, 3], "rotation": [180, 0, 0], "resolution": [10, 10],
  }
  rest = Mock()
  for method, records in (("getScenes", [scene]), ("getCameras", [camera]), ("getAssets", [])):
    result = getattr(rest, method).return_value
    result.statusCode = 200
    result.get.return_value = records
  with patch("observation_processor.scene_provider.RESTClient", return_value=rest):
    provider = SceneProvider(media_root=str(tmp_path))
    assert _probe_readiness(provider, False)
    reasoner = provider.get_reasoner("scene", "camera")
    assert np.isclose(reasoner.depth_map.t_hit_map[5, 5, 0], 3.0, atol=1e-4)
    first_mesh = provider.get_world_mesh("scene")
    _write_plane_glb(path, 1)
    provider.invalidate()
    assert _probe_readiness(provider, True)
    with patch.object(provider, "_load_world_mesh", side_effect=AssertionError("cold mesh load")), \
         patch("observation_conditioning.AmodalReasoner",
               side_effect=AssertionError("cold depth bake")):
      assert provider.get_world_mesh("scene") is not first_mesh
      refreshed = provider.get_reasoner("scene", "camera")
      assert refreshed is not reasoner
      assert np.isclose(refreshed.depth_map.t_hit_map[5, 5, 0], 2.0, atol=1e-4)
