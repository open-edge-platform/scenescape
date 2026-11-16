# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Isolated configuration/geometry lifecycle regression tests."""

import json
import struct
import threading
from unittest.mock import Mock, patch

import pytest
from grpc_health.v1 import health_pb2

from observation_processor.scene_provider import (
  MAX_SCENE_MESH_BYTES, SceneMeshMissingError, SceneMeshTooLargeError, SceneProvider,
  StoreUnavailableError, _read_mesh_file,
)
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
      patch.object(SceneProvider, "_mesh_bytes", return_value=b"mesh"), \
      patch.object(SceneProvider, "_load_world_mesh", side_effect=lambda scene, data: object()) as load, \
      patch("observation_conditioning.AmodalReasoner") as reasoner:
    yield SceneProvider(), rest, scene, camera, load, reasoner


def _download_client(response):
  client = Mock(token="manager-token", verify_ssl="/manager-ca.pem", timeout=7)
  client.session.get.return_value = response
  return client


def test_mesh_download_uses_authenticated_same_origin_stream(configuration):
  provider, *_ = configuration
  response = Mock(status_code=200, headers={"Content-Length": "5"})
  response.iter_content.return_value = iter((b"mesh", b"!"))
  client = _download_client(response)
  with patch.object(provider, "_client", return_value=client):
    assert provider._download("/media/scene.glb") == b"mesh!"
  client.session.get.assert_called_once_with(
    "https://web.scenescape.intel.com/media/scene.glb",
    headers={"Authorization": "Token manager-token"}, verify="/manager-ca.pem",
    timeout=7, stream=True, allow_redirects=False,
  )
  response.close.assert_called_once()


@pytest.mark.parametrize("url", [
  "https://other.example/scene.glb", "//other.example/scene.glb",
  "https://web.scenescape.intel.com:444/scene.glb",
])
def test_mesh_download_rejects_non_manager_origin_before_authentication(configuration, url):
  provider, *_ = configuration
  with patch.object(provider, "_client") as client:
    with pytest.raises(StoreUnavailableError, match="share the Manager origin"):
      provider._download(url)
  client.assert_not_called()


def test_mesh_download_rejects_oversized_content_length(configuration, monkeypatch):
  provider, *_ = configuration
  monkeypatch.setattr("observation_processor.scene_provider.MAX_SCENE_MESH_BYTES", 4)
  response = Mock(status_code=200, headers={"Content-Length": "5"})
  client = _download_client(response)
  with patch.object(provider, "_client", return_value=client):
    with pytest.raises(SceneMeshTooLargeError, match="exceeds maximum size"):
      provider._download("/media/scene.glb")
  response.iter_content.assert_not_called()
  response.close.assert_called_once()


def test_mesh_download_caps_stream_when_content_length_is_missing(configuration, monkeypatch):
  provider, *_ = configuration
  monkeypatch.setattr("observation_processor.scene_provider.MAX_SCENE_MESH_BYTES", 4)
  response = Mock(status_code=200, headers={})
  response.iter_content.return_value = iter((b"1234", b"5", b"not-read"))
  client = _download_client(response)
  with patch.object(provider, "_client", return_value=client):
    with pytest.raises(SceneMeshTooLargeError, match="exceeds maximum size"):
      provider._download("/media/scene.glb")
  response.close.assert_called_once()


def test_local_mesh_rejects_oversized_file_before_read(tmp_path, monkeypatch):
  monkeypatch.setattr("observation_processor.scene_provider.MAX_SCENE_MESH_BYTES", 4)
  mesh = tmp_path / "scene.glb"
  mesh.write_bytes(b"12345")
  with pytest.raises(SceneMeshTooLargeError, match="exceeds maximum size"):
    _read_mesh_file(str(mesh))


def test_mesh_warm_failure_retains_previous_mesh(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.get_world_mesh("scene")
  provider.invalidate()
  load.side_effect = SceneMeshMissingError("invalid mesh")
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
    assert _probe_readiness(provider, True)
  assert not provider.needs_refresh
  assert provider.get_world_mesh("scene") is previous


def test_mesh_warm_failure_without_previous_continues_without_mesh(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  load.side_effect = SceneMeshTooLargeError("too large")
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"huge mesh"):
    provider.warm()
  assert not provider.needs_refresh
  assert not provider._world_meshes
  assert not provider.has_usable_mesh("scene")
  reasoner.assert_not_called()


def test_multi_scene_warm_continues_when_one_mesh_fails(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  other = {"uid": "other", "map": "/media/other.glb"}

  def scenes(*args):
    result = Mock(statusCode=200)
    result.get.return_value = [scene, other]
    return result

  def cameras(filter_args=None):
    result = Mock(statusCode=200)
    scene_uid = (filter_args or {}).get("scene")
    result.get.return_value = [camera] if scene_uid == "scene" else [
      dict(camera, uid="other-camera")]
    return result

  rest.getScenes.side_effect = scenes
  rest.getCameras.side_effect = cameras

  def load_mesh(record, data):
    if record["uid"] == "other":
      raise SceneMeshMissingError("other mesh broken")
    return object()

  load.side_effect = load_mesh
  provider.warm()
  assert not provider.needs_refresh
  assert "scene" in provider._world_meshes
  assert "other" not in provider._world_meshes
  assert provider.has_usable_mesh("scene")
  assert not provider.has_usable_mesh("other")


def test_startup_preloads_geometry_and_first_access_is_cached(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  assert provider.needs_refresh
  assert _probe_readiness(provider, False)
  assert not provider.needs_refresh
  load.assert_called_once_with(scene, b"mesh")
  reasoner.assert_called_once()
  rest.reset_mock()
  provider.get_world_mesh("scene")
  assert provider.get_reasoner("scene", "camera") is reasoner.return_value
  assert load.call_count == reasoner.call_count == 1
  rest.getScene.assert_not_called()
  rest.getCameras.assert_not_called()


def test_pending_refresh_serves_last_good_snapshot(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  assert not provider.has_snapshot
  with pytest.raises(StoreUnavailableError):
    provider.snapshot()
  provider.warm()
  previous = provider.snapshot()
  provider.invalidate()
  current = provider.snapshot()
  assert provider.has_snapshot
  assert provider.needs_refresh
  assert not current.needs_refresh
  assert current.get_world_mesh("scene") is previous.get_world_mesh("scene")
  assert current.get_reasoner("scene", "camera") is previous.get_reasoner("scene", "camera")
  assert load.call_count == reasoner.call_count == 1


def test_refresh_replaces_mesh_at_same_url_and_reasoner(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  first = provider.get_world_mesh("scene")
  provider.invalidate()
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
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


@pytest.mark.parametrize("change", ["metadata", "camera", "mesh_pose", "mesh_content"])
def test_refresh_reuses_only_unchanged_geometry(configuration, change):
  """Metadata edits reuse all baking; calibration and mesh edits rebuild their dependents."""
  provider, rest, scene, camera, load, reasoner = configuration
  other_camera = dict(camera, uid="other-camera")
  rest.getCameras.return_value.get.return_value = [camera, other_camera]
  reasoner.side_effect = lambda **kwargs: Mock()
  provider.warm()
  previous = provider.snapshot()
  first_reasoner = previous.get_reasoner("scene", "camera")
  other_reasoner = previous.get_reasoner("scene", "other-camera")
  mesh_data = b"mesh"
  if change == "metadata":
    scene["name"] = "renamed scene"
    rest.getAssets.return_value.get.return_value = [
      {"name": "person", "x_size": 1, "y_size": 2, "z_size": 3}]
  elif change == "camera":
    camera["resolution"] = [20, 20]
  elif change == "mesh_pose":
    scene["mesh_translation"] = [1, 0, 0]
  else:
    mesh_data = b"replacement mesh"
  provider.invalidate()
  with patch.object(SceneProvider, "_mesh_bytes", return_value=mesh_data):
    provider.warm()
  current = provider.snapshot()
  mesh_changed = change in ("mesh_pose", "mesh_content")
  assert (current.get_world_mesh("scene") is previous.get_world_mesh("scene")) != mesh_changed
  assert (current.get_reasoner("scene", "camera") is first_reasoner) == (change == "metadata")
  assert (current.get_reasoner("scene", "other-camera") is other_reasoner) != mesh_changed
  assert load.call_count == (2 if mesh_changed else 1)
  assert reasoner.call_count == (4 if mesh_changed else 3 if change == "camera" else 2)
  if change == "metadata":
    assert current.get_scene("scene")["name"] == "renamed scene"
    assert "name" not in previous.get_scene("scene")
    assert current.get_asset_prior("person").prior["mu_x"] == 1
    assert previous.get_asset_prior("person").prior["mu_x"] == 0.55


def test_deleted_camera_does_not_carry_over_reasoner(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  rest.getCameras.return_value.get.return_value = []
  provider.invalidate()
  provider.warm()
  assert not provider._reasoners
  assert provider.snapshot().get_world_mesh("scene") is not None
  assert load.call_count == 1


def test_failed_initial_mesh_warmup_still_publishes_frustum_only_snapshot(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  load.side_effect = RuntimeError("bake failed")
  assert _probe_readiness(provider, False)
  assert provider.has_snapshot
  assert not provider.needs_refresh
  assert not provider._world_meshes
  assert not provider.has_usable_mesh("scene")


def test_failed_initial_configuration_warmup_remains_unavailable(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  rest.getScenes.side_effect = StoreUnavailableError("offline")
  assert not _probe_readiness(provider, False)
  assert not provider.has_snapshot
  assert provider.needs_refresh
  with pytest.raises(StoreUnavailableError):
    provider.snapshot()


def test_manager_outage_keeps_loaded_configuration_serving(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  provider.invalidate()
  with patch.object(provider, "is_ready", return_value=False):
    assert _probe_readiness(provider, True)
  assert provider.needs_refresh
  assert provider.snapshot().get_reasoner("scene", "camera") is reasoner.return_value


def test_requests_keep_old_snapshot_while_refresh_is_blocked(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.snapshot()
  scene["name"] = "updated scene"
  provider.invalidate()
  entered = threading.Event()
  release = threading.Event()
  health = Mock()
  health.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
  results = []

  def blocked_load(scene, data):
    entered.set()
    assert release.wait(5)
    return object()

  load.side_effect = blocked_load
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
    worker = threading.Thread(target=lambda: results.append(_probe_readiness(provider, True, health)))
    worker.start()
    try:
      assert entered.wait(5)
      current = provider.snapshot()
      assert "name" not in current.get_scene("scene")
      assert current.get_world_mesh("scene") is previous.get_world_mesh("scene")
      assert current.get_reasoner("scene", "camera") is reasoner.return_value
      health.set.assert_called_once_with(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    finally:
      release.set()
      worker.join(timeout=5)
  assert not worker.is_alive()
  assert results == [True]
  assert provider.snapshot().get_scene("scene")["name"] == "updated scene"
  assert "name" not in previous.get_scene("scene")


def test_uncalibrated_camera_does_not_prevent_mesh_warmup(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  camera.pop("intrinsics")
  provider.warm()
  assert not provider.needs_refresh
  load.assert_called_once()
  reasoner.assert_not_called()


def test_oversized_camera_does_not_prevent_mesh_warmup(configuration, monkeypatch):
  provider, rest, scene, camera, load, reasoner = configuration
  camera["resolution"] = [3840, 2160]
  monkeypatch.setenv("OBSERVATION_PROCESSOR_MAX_CAMERA_PIXELS", "100")
  provider.warm()
  assert not provider.needs_refresh
  load.assert_called_once()
  reasoner.assert_not_called()
  assert provider.get_world_mesh("scene") is not None


def test_failed_configuration_refresh_keeps_previous_snapshot_and_retries(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.get_world_mesh("scene")
  provider.invalidate()
  rest.getScenes.side_effect = StoreUnavailableError("offline")
  assert _probe_readiness(provider, True)
  assert provider.needs_refresh
  assert provider.get_world_mesh("scene") is previous
  rest.getScenes.side_effect = None
  scenes = Mock(statusCode=200)
  scenes.get.return_value = [scene]
  rest.getScenes.return_value = scenes
  load.side_effect = lambda scene, data: object()
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
    assert _probe_readiness(provider, True)
  assert not provider.needs_refresh
  assert provider.get_world_mesh("scene") is not previous


def test_event_during_refresh_discards_obsolete_snapshot(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  previous = provider.get_world_mesh("scene")
  provider.invalidate()

  def update_during_load(scene, data):
    provider.invalidate()
    return object()

  load.side_effect = update_during_load
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
    assert _probe_readiness(provider, True)
  assert provider.needs_refresh
  assert provider.get_world_mesh("scene") is previous
  load.side_effect = lambda scene, data: object()
  assert _probe_readiness(provider, True)


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
def test_monitor_keeps_serving_during_refresh(configuration, already_ready):
  provider, rest, scene, camera, load, reasoner = configuration
  if already_ready:
    provider.warm()
    provider.invalidate()
  stop = threading.Event()
  health = Mock()
  observed_statuses = []

  def load_mesh(scene, data):
    observed_statuses.extend(call.args[1] for call in health.set.call_args_list)
    stop.set()
    return object()

  load.side_effect = load_mesh
  with patch.object(SceneProvider, "_mesh_bytes", return_value=b"replacement mesh"):
    thread = start_readiness_monitor(provider, health, interval=0.01, stop_event=stop)
    thread.join(timeout=5)
  assert not thread.is_alive()
  assert observed_statuses == ([] if already_ready else [health_pb2.HealthCheckResponse.NOT_SERVING])
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
    assert load.call_count == 1
    assert _probe_readiness(provider, True)
    assert load.call_count == 1


def test_database_event_wakes_monitor_before_periodic_probe(configuration):
  provider, rest, scene, camera, load, reasoner = configuration
  provider.warm()
  waiting = threading.Event()
  stop = threading.Event()
  health = Mock()
  wait_for_refresh = provider.wait_for_refresh

  def wait(timeout):
    waiting.set()
    wait_for_refresh(timeout)

  def refreshed(*args):
    if not provider.needs_refresh and rest.getAssets.call_count == 2:
      stop.set()

  health.set.side_effect = refreshed
  with patch.object(provider, "wait_for_refresh", side_effect=wait):
    worker = start_readiness_monitor(provider, health, interval=60, stop_event=stop)
    try:
      assert waiting.wait(5)
      provider.invalidate()
      assert stop.wait(5)
    finally:
      stop.set()
      provider.invalidate()
      worker.join(timeout=5)
  assert not worker.is_alive()
  assert rest.getAssets.call_count == 2
  assert load.call_count == reasoner.call_count == 1


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
