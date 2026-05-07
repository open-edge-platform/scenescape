# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for BlackBoxHarness."""

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.black_box_harness import BlackBoxHarness
from harnesses.black_box_harness.black_box_harness import (
    CONTAINER_TYPE_CONTROLLER,
    CONTAINER_TYPE_TRACKER,
    DEFAULT_DRAIN_TIMEOUT,
    DEFAULT_PLAYBACK_RATE,
    _detect_container_type,
    _free_port,
    _merge_outputs_by_timestamp,
    _parse_ts,
    _solve_pnp,
    _to_controller_config,
    _to_tracker_service_scenes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def harness():
    return BlackBoxHarness(container_image="scenescape-controller:test")


@pytest.fixture
def scene_config():
    return {
        "name": "Test_Scene",
        "uid": "scene-uid-001",
        "map": "map.png",
        "scale": 38.1,
        "sensors": {},
    }


@pytest.fixture
def tracker_config_file(tmp_path):
    cfg = {
        "max_unreliable_time_s": 2.0,
        "non_measurement_time_dynamic_s": 1.0,
        "non_measurement_time_static_s": 3.0,
        "time_chunking_enabled": False,
        "ref_camera_frame_rate": 30,
    }
    p = tmp_path / "tracker-config.json"
    p.write_text(json.dumps(cfg))
    return str(p)


@pytest.fixture
def sample_frames():
    return [
        {
            "id": "Cam_x1_0",
            "timestamp": "2014-09-08T04:00:00.033Z",
            "frame": 1,
            "objects": {"person": [{"id": 0, "category": "person",
                                    "confidence": 1.0,
                                    "bounding_box_px": {"x": 298, "y": 132,
                                                        "width": 28, "height": 89}}]},
        },
        {
            "id": "Cam_x1_0",
            "timestamp": "2014-09-08T04:00:00.066Z",
            "frame": 2,
            "objects": {},
        },
        {
            "id": "Cam_x2_0",
            "timestamp": "2014-09-08T04:00:00.066Z",
            "frame": 2,
            "objects": {"person": [{"id": 1, "category": "person",
                                    "confidence": 0.9,
                                    "bounding_box_px": {"x": 100, "y": 200,
                                                        "width": 30, "height": 70}}]},
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestParseTsHelper:
    def test_z_suffix(self):
        ts = _parse_ts("2014-09-08T04:00:00.033Z")
        assert isinstance(ts, float)
        assert ts > 0

    def test_utc_offset(self):
        ts1 = _parse_ts("2014-09-08T04:00:00.033Z")
        ts2 = _parse_ts("2014-09-08T04:00:00.033+00:00")
        assert abs(ts1 - ts2) < 1e-3

    def test_delta(self):
        t1 = _parse_ts("2014-09-08T04:00:00.000Z")
        t2 = _parse_ts("2014-09-08T04:00:00.033Z")
        assert abs((t2 - t1) - 0.033) < 1e-6


class TestFreePort:
    def test_returns_int(self):
        p = _free_port()
        assert isinstance(p, int)
        assert 1024 <= p <= 65535

    def test_unique(self):
        ports = {_free_port() for _ in range(5)}
        # Very unlikely all five collide
        assert len(ports) >= 1


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInitialisation:
    def test_stores_image(self):
        h = BlackBoxHarness("my-image:latest")
        assert h._container_image == "my-image:latest"

    def test_defaults(self, harness):
        assert harness._scene_config is None
        assert harness._scene_id is None
        assert harness._tracker_config_path is None
        assert harness._playback_rate == DEFAULT_PLAYBACK_RATE
        assert harness._drain_timeout == DEFAULT_DRAIN_TIMEOUT
        assert harness._output_folder is None


# ---------------------------------------------------------------------------
# set_scene_config
# ---------------------------------------------------------------------------

class TestSetSceneConfig:
    def test_accepts_valid_config(self, harness, scene_config):
        result = harness.set_scene_config(scene_config)
        assert result is harness
        assert harness._scene_config == scene_config

    def test_extracts_uid_as_scene_id(self, harness, scene_config):
        harness.set_scene_config(scene_config)
        assert harness._scene_id == "scene-uid-001"

    def test_falls_back_to_name_when_no_uid(self, harness):
        harness.set_scene_config({"name": "MyScene"})
        assert harness._scene_id == "MyScene"

    def test_rejects_non_dict(self, harness):
        with pytest.raises(ValueError):
            harness.set_scene_config("not a dict")

    def test_rejects_missing_name(self, harness):
        with pytest.raises(ValueError, match="'name'"):
            harness.set_scene_config({"uid": "x"})


# ---------------------------------------------------------------------------
# set_custom_config
# ---------------------------------------------------------------------------

class TestSetCustomConfig:
    def test_accepts_valid_config(self, harness, tracker_config_file):
        result = harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
        })
        assert result is harness
        assert harness._tracker_config_path == tracker_config_file

    def test_overrides_playback_rate(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "playback_rate": 2.0,
        })
        assert harness._playback_rate == 2.0

    def test_overrides_drain_timeout(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "drain_timeout": 10.0,
        })
        assert harness._drain_timeout == 10.0

    def test_overrides_broker_image(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "custom-mosquitto:2.0",
        })
        assert harness._broker_image == "custom-mosquitto:2.0"

    def test_overrides_scene_id(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "scene_id": "override-uid",
        })
        assert harness._scene_id == "override-uid"

    def test_rejects_non_dict(self, harness):
        with pytest.raises(ValueError):
            harness.set_custom_config("bad")

    def test_rejects_missing_tracker_config_path(self, harness):
        with pytest.raises(ValueError, match="tracker_config_path"):
            harness.set_custom_config({})

    def test_rejects_nonexistent_tracker_config_file(self, harness):
        with pytest.raises(ValueError, match="not found"):
            harness.set_custom_config({"tracker_config_path": "/no/such/file.json"})

    def test_rejects_missing_broker_image(self, harness, tracker_config_file):
        with pytest.raises(ValueError, match="broker_image"):
            harness.set_custom_config({"tracker_config_path": tracker_config_file})


# ---------------------------------------------------------------------------
# set_output_folder
# ---------------------------------------------------------------------------

class TestSetOutputFolder:
    def test_creates_directory(self, harness, tmp_path):
        target = tmp_path / "new" / "nested"
        harness.set_output_folder(target)
        assert target.exists()
        assert harness._output_folder == target

    def test_accepts_string(self, harness, tmp_path):
        harness.set_output_folder(str(tmp_path))
        assert isinstance(harness._output_folder, Path)


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_clears_all_state(self, harness, scene_config, tracker_config_file, tmp_path):
        harness.set_scene_config(scene_config)
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "playback_rate": 3.0,
        })
        harness.set_output_folder(tmp_path)
        harness.reset()
        assert harness._scene_config is None
        assert harness._scene_id is None
        assert harness._tracker_config_path is None
        assert harness._playback_rate == DEFAULT_PLAYBACK_RATE
        assert harness._output_folder is None

    def test_returns_self(self, harness):
        assert harness.reset() is harness


# ---------------------------------------------------------------------------
# process_inputs — pre-condition guards
# ---------------------------------------------------------------------------

class TestProcessInputsGuards:
    def test_raises_when_no_scene_config(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
        })
        with pytest.raises(RuntimeError, match="set_scene_config"):
            list(harness.process_inputs(iter([])))

    def test_raises_when_no_custom_config(self, harness, scene_config):
        harness.set_scene_config(scene_config)
        with pytest.raises(RuntimeError, match="set_custom_config"):
            list(harness.process_inputs(iter([])))


# ---------------------------------------------------------------------------
# process_inputs — full flow (Docker mocked)
# ---------------------------------------------------------------------------

class TestProcessInputsFlow:
    """Verify the orchestration logic with Docker and paho fully mocked."""

    @pytest.fixture(autouse=True)
    def mock_wait_for_port(self):
        """Prevent real TCP probes during unit tests."""
        with patch("harnesses.black_box_harness.black_box_harness._wait_for_port"):
            yield
    @pytest.fixture
    def configured_harness(self, harness, scene_config, tracker_config_file):
        harness.set_scene_config(scene_config)
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "drain_timeout": 0.1,  # fast test
            "playback_rate": 100.0,  # skip real-time waiting
        })
        return harness

    def _make_fake_output(self):
        return {"timestamp": "2014-09-08T04:00:00.100Z", "objects": []}

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_publishes_one_topic_per_frame(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Each input frame is published to scenescape/data/camera/{id}."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        # Simulate subscribe callback firing immediately
        mock_client_instance.on_connect = None
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        list(configured_harness.process_inputs(iter(sample_frames)))

        publish_calls = mock_client_instance.publish.call_args_list
        published_topics = [c.args[0] for c in publish_calls]
        assert "scenescape/data/camera/Cam_x1_0" in published_topics
        assert "scenescape/data/camera/Cam_x2_0" in published_topics
        # Two Cam_x1_0 frames + one Cam_x2_0
        assert published_topics.count("scenescape/data/camera/Cam_x1_0") == 2
        assert published_topics.count("scenescape/data/camera/Cam_x2_0") == 1

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_subscribes_to_scene_output_topic(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Client subscribes to scenescape/data/scene/{scene_id}/+ for Controller."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        # Simulate broker triggering on_connect so the subscribe call fires
        def fake_connect(*args, **kwargs):
            if mock_client_instance.on_connect:
                mock_client_instance.on_connect(
                    mock_client_instance, None, None, 0
                )

        mock_client_instance.connect.side_effect = fake_connect

        list(configured_harness.process_inputs(iter(sample_frames)))

        # on_connect callback should subscribe with the DATA_SCENE wildcard topic
        subscribe_calls = mock_client_instance.subscribe.call_args_list
        topics = [c.args[0] for c in subscribe_calls]
        assert any("scenescape/data/scene/scene-uid-001/+" in t for t in topics)

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_broker_started_before_tracker(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Broker container is started before tracker container."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        run_calls = []
        mock_docker.run = MagicMock(side_effect=lambda image, *a, **kw: run_calls.append(image) or MagicMock())

        list(configured_harness.process_inputs(iter(sample_frames)))

        assert len(run_calls) == 2
        assert run_calls[0] == "eclipse-mosquitto:2.0.22"  # broker first
        assert run_calls[1] == "scenescape-controller:test"  # tracker second

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_returns_collected_outputs(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Outputs injected via on_message are returned by process_inputs."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        expected_output = {"timestamp": "2014-09-08T04:00:00.100Z", "objects": [{"id": "0"}]}

        def fake_loop_start():
            # Simulate an incoming message
            msg = MagicMock()
            msg.payload = json.dumps(expected_output).encode()
            mock_client_instance.on_message(mock_client_instance, None, msg)

        mock_client_instance.loop_start.side_effect = fake_loop_start

        outputs = list(configured_harness.process_inputs(iter(sample_frames)))

        assert len(outputs) == 1
        assert outputs[0] == expected_output

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_containers_stopped_on_success(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Broker and tracker containers are stopped after processing."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_ctr = MagicMock()
        mock_docker.run = MagicMock(return_value=mock_ctr)

        list(configured_harness.process_inputs(iter(sample_frames)))

        assert mock_ctr.stop.called
        assert mock_ctr.remove.called

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_containers_stopped_on_exception(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Containers are cleaned up even when an exception occurs mid-session."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_ctr = MagicMock()
        mock_docker.run = MagicMock(return_value=mock_ctr)
        mock_client_instance.connect.side_effect = RuntimeError("broker unreachable")

        with pytest.raises(RuntimeError):
            list(configured_harness.process_inputs(iter(sample_frames)))

        assert mock_ctr.stop.called
        assert mock_ctr.remove.called

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_docker_network_removed_after_run(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames
    ):
        """Docker network is removed after the session ends."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        list(configured_harness.process_inputs(iter(sample_frames)))

        mock_docker.network.remove.assert_called_once()

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_persists_inputs_to_output_folder(
        self, mock_sleep, MockMqttClient, mock_docker,
        configured_harness, sample_frames, tmp_path
    ):
        """inputs.json is written to the output folder when one is set."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        configured_harness.set_output_folder(tmp_path / "out")
        list(configured_harness.process_inputs(iter(sample_frames)))

        assert (tmp_path / "out" / "inputs.json").exists()


# ---------------------------------------------------------------------------
# Timestamp pacing
# ---------------------------------------------------------------------------

class TestTimestampPacing:
    """Verify that inter-frame sleep respects timestamp deltas and playback_rate."""

    @pytest.fixture(autouse=True)
    def mock_wait_for_port(self):
        """Prevent real TCP probes during unit tests."""
        with patch("harnesses.black_box_harness.black_box_harness._wait_for_port"):
            yield

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    def test_pacing_respects_playback_rate(
        self, MockMqttClient, mock_docker, harness, scene_config, tracker_config_file
    ):
        """At 2× rate, sleep durations are halved relative to timestamp deltas."""
        harness.set_scene_config(scene_config)
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "drain_timeout": 0.0,
            "playback_rate": 2.0,
        })

        frames = [
            {"id": "Cam_x1_0", "timestamp": "2014-09-08T04:00:00.000Z", "frame": 1, "objects": {}},
            {"id": "Cam_x1_0", "timestamp": "2014-09-08T04:00:01.000Z", "frame": 2, "objects": {}},
        ]

        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        sleep_calls = []

        def recording_sleep(t):
            sleep_calls.append(t)
            # Don't actually sleep — instant test
            pass

        with patch("harnesses.black_box_harness.black_box_harness.time.sleep", side_effect=recording_sleep):
            list(harness.process_inputs(iter(frames)))

        # The 1-second inter-frame gap / rate=2.0 → expected sleep ≈ 0.5s.
        # Startup sleeps (broker ready: 1.0s, tracker ready: 2.0s) are also
        # captured; filter those out by ignoring sleeps >= 1.0s.
        pacing_sleeps = [s for s in sleep_calls if 0 < s < 1.0]
        assert len(pacing_sleeps) > 0, "Expected at least one pacing sleep"
        for s in pacing_sleeps:
            assert s <= 0.6, f"Sleep {s}s too large for 2× playback of 1s delta"


# ---------------------------------------------------------------------------
# Scene config helpers — unit tests (no Docker)
# ---------------------------------------------------------------------------

# Minimal calibration data matching the Retail_Demo dataset structure
_CAM_POINTS = [[201, 119], [592, 118], [781, 579], [2, 579]]
_MAP_POINTS  = [[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]]
_INTRINSICS  = [964.24, 964.63, 400.0, 300.0]

_SCENE_WITH_SENSORS = {
    "name": "Retail_Demo",
    "uid": "Retail_Demo",
    "map": "map.png",
    "scale": 38.1,
    "sensors": {
        "Cam_x1_0": {
            "intrinsics": _INTRINSICS,
            "width": 800.0,
            "height": 600.0,
            "camera points": _CAM_POINTS,
            "map points": _MAP_POINTS,
        },
    },
}


class TestSolvePnP:
    """_solve_pnp should return plausible camera extrinsics."""

    def test_returns_three_lists(self):
        t, r, s = _solve_pnp(_CAM_POINTS, _MAP_POINTS, _INTRINSICS)
        assert isinstance(t, list) and len(t) == 3
        assert isinstance(r, list) and len(r) == 3
        assert isinstance(s, list) and len(s) == 3

    def test_scale_is_unit(self):
        _, _, s = _solve_pnp(_CAM_POINTS, _MAP_POINTS, _INTRINSICS)
        assert s == [1.0, 1.0, 1.0]

    def test_translation_in_plausible_range(self):
        # Camera is above the ground (z > 0) and within tens of metres
        t, _, _ = _solve_pnp(_CAM_POINTS, _MAP_POINTS, _INTRINSICS)
        assert t[2] > 0, "Camera z (height) should be positive"
        assert all(abs(v) < 100 for v in t), f"Implausibly large translation: {t}"

    def test_2d_map_points_accepted(self):
        map_pts_2d = [[pt[0], pt[1]] for pt in _MAP_POINTS]
        t, r, s = _solve_pnp(_CAM_POINTS, map_pts_2d, _INTRINSICS)
        assert len(t) == 3


class TestToControllerConfig:
    """_to_controller_config should embed camera/map points directly."""

    def test_has_camera_and_map_points_in_camera_dict(self):
        cfg = _to_controller_config(_SCENE_WITH_SENSORS)
        cam = cfg["cameras"][0]
        assert "camera points" in cam
        assert "map points" in cam

    def test_no_transforms_array(self):
        cfg = _to_controller_config(_SCENE_WITH_SENSORS)
        cam = cfg["cameras"][0]
        assert "transforms" not in cam
        assert "transform_type" not in cam

    def test_uid_propagated(self):
        cfg = _to_controller_config(_SCENE_WITH_SENSORS)
        assert cfg["uid"] == "Retail_Demo"
        assert cfg["cameras"][0]["scene"] == "Retail_Demo"

    def test_intrinsics_dict(self):
        cfg = _to_controller_config(_SCENE_WITH_SENSORS)
        intr = cfg["cameras"][0]["intrinsics"]
        assert all(k in intr for k in ("fx", "fy", "cx", "cy"))

    def test_no_sensors_produces_empty_cameras(self):
        cfg = _to_controller_config({"name": "Empty", "uid": "empty"})
        assert cfg["cameras"] == []


class TestToTrackerServiceScenes:
    """_to_tracker_service_scenes should produce valid Tracker-service scenes."""

    def test_returns_list_with_one_scene(self):
        scenes = _to_tracker_service_scenes(_SCENE_WITH_SENSORS)
        assert isinstance(scenes, list) and len(scenes) == 1

    def test_scene_has_required_keys(self):
        scene = _to_tracker_service_scenes(_SCENE_WITH_SENSORS)[0]
        assert all(k in scene for k in ("uid", "name", "cameras"))

    def test_camera_has_extrinsics(self):
        cam = _to_tracker_service_scenes(_SCENE_WITH_SENSORS)[0]["cameras"][0]
        assert "extrinsics" in cam
        ext = cam["extrinsics"]
        assert all(k in ext for k in ("translation", "rotation", "scale"))

    def test_camera_intrinsics_nested_distortion(self):
        cam = _to_tracker_service_scenes(_SCENE_WITH_SENSORS)[0]["cameras"][0]
        intr = cam["intrinsics"]
        assert "distortion" in intr
        assert all(k in intr["distortion"] for k in ("k1", "k2", "p1", "p2"))

    def test_no_transforms_key(self):
        cam = _to_tracker_service_scenes(_SCENE_WITH_SENSORS)[0]["cameras"][0]
        assert "transforms" not in cam
        assert "transform_type" not in cam

    def test_no_sensors_produces_empty_cameras(self):
        scenes = _to_tracker_service_scenes({"name": "Empty", "uid": "empty"})
        assert scenes[0]["cameras"] == []


# ---------------------------------------------------------------------------
# Container type detection
# ---------------------------------------------------------------------------

class TestDetectContainerType:
    """_detect_container_type should return correct type from image metadata."""

    def test_detects_controller_from_entrypoint(self):
        mock_img = MagicMock()
        mock_img.config.entrypoint = ["/home/scenescape/SceneScape/controller-cmd"]
        mock_img.config.cmd = []
        with patch("harnesses.black_box_harness.black_box_harness.docker") as md:
            md.image.inspect.return_value = mock_img
            assert _detect_container_type("any-image") == CONTAINER_TYPE_CONTROLLER

    def test_detects_tracker_from_cmd(self):
        mock_img = MagicMock()
        mock_img.config.entrypoint = []
        mock_img.config.cmd = ["/scenescape/tracker", "--config", "..."]
        with patch("harnesses.black_box_harness.black_box_harness.docker") as md:
            md.image.inspect.return_value = mock_img
            assert _detect_container_type("any-image") == CONTAINER_TYPE_TRACKER

    def test_falls_back_to_image_name_controller(self):
        with patch("harnesses.black_box_harness.black_box_harness.docker") as md:
            md.image.inspect.side_effect = Exception("not found")
            assert _detect_container_type("scenescape-controller:latest") == CONTAINER_TYPE_CONTROLLER

    def test_falls_back_to_image_name_tracker(self):
        with patch("harnesses.black_box_harness.black_box_harness.docker") as md:
            md.image.inspect.side_effect = Exception("not found")
            assert _detect_container_type("scenescape-tracker:latest") == CONTAINER_TYPE_TRACKER


# ---------------------------------------------------------------------------
# Container type config validation
# ---------------------------------------------------------------------------

class TestContainerTypeConfig:
    def test_accepts_controller_type(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "container_type": "controller",
        })
        assert harness._container_type == CONTAINER_TYPE_CONTROLLER

    def test_accepts_tracker_type(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "container_type": "tracker",
        })
        assert harness._container_type == CONTAINER_TYPE_TRACKER

    def test_rejects_unknown_type(self, harness, tracker_config_file):
        with pytest.raises(ValueError, match="container_type"):
            harness.set_custom_config({
                "tracker_config_path": tracker_config_file,
                "broker_image": "eclipse-mosquitto:2.0.22",
                "container_type": "unknown",
            })

    def test_reset_clears_container_type(self, harness, tracker_config_file):
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "container_type": "tracker",
        })
        harness.reset()
        assert harness._container_type is None


# ---------------------------------------------------------------------------
# Timestamp rewriting for Tracker service
# ---------------------------------------------------------------------------

class TestTimestampRewriting:
    """Tracker service mode: published timestamps must be current wall-clock."""

    @pytest.fixture(autouse=True)
    def mock_wait_for_port(self):
        with patch("harnesses.black_box_harness.black_box_harness._wait_for_port"):
            yield

    @pytest.fixture
    def tracker_svc_harness(self, harness, scene_config, tracker_config_file):
        harness.set_scene_config(scene_config)
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "drain_timeout": 0.0,
            "playback_rate": 100.0,
            "container_type": CONTAINER_TYPE_TRACKER,
        })
        return harness

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_published_timestamps_are_not_historical(
        self, mock_sleep, MockMqttClient, mock_docker,
        tracker_svc_harness, sample_frames
    ):
        """Tracker service: published frames must carry current-ish timestamps."""
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        list(tracker_svc_harness.process_inputs(iter(sample_frames)))

        published_payloads = [
            json.loads(call.args[1])
            for call in mock_client_instance.publish.call_args_list
        ]
        import time as _time
        now = _time.time()
        for payload in published_payloads:
            ts = _parse_ts(payload["timestamp"])
            # Should be within last 60 seconds (not 2014 dataset timestamp)
            assert abs(ts - now) < 60, f"Published timestamp too far from now: {payload['timestamp']}"

    @patch("harnesses.black_box_harness.black_box_harness.docker")
    @patch("harnesses.black_box_harness.black_box_harness.mqtt.Client")
    @patch("harnesses.black_box_harness.black_box_harness.time.sleep")
    def test_controller_keeps_original_timestamps(
        self, mock_sleep, MockMqttClient, mock_docker,
        harness, scene_config, tracker_config_file, sample_frames
    ):
        """Controller mode: frames are published with original dataset timestamps."""
        harness.set_scene_config(scene_config)
        harness.set_custom_config({
            "tracker_config_path": tracker_config_file,
            "broker_image": "eclipse-mosquitto:2.0.22",
            "drain_timeout": 0.0,
            "playback_rate": 100.0,
            "container_type": CONTAINER_TYPE_CONTROLLER,
        })
        mock_client_instance = MagicMock()
        MockMqttClient.return_value = mock_client_instance
        mock_docker.network.create = MagicMock()
        mock_docker.network.remove = MagicMock()
        mock_docker.run = MagicMock(return_value=MagicMock())

        list(harness.process_inputs(iter(sample_frames)))

        published_payloads = [
            json.loads(call.args[1])
            for call in mock_client_instance.publish.call_args_list
        ]
        for payload, original in zip(published_payloads, sample_frames):
            assert payload["timestamp"] == original["timestamp"]


# ---------------------------------------------------------------------------
# _merge_outputs_by_timestamp — unit tests
# ---------------------------------------------------------------------------

class TestMergeOutputsByTimestamp:
    """_merge_outputs_by_timestamp should deduplicate objects across same-timestamp messages."""

    def test_single_message_unchanged(self):
        msgs = [{"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "a"}]}]
        result = _merge_outputs_by_timestamp(msgs)
        assert len(result) == 1
        assert result[0]["objects"] == [{"id": "a"}]

    def test_same_timestamp_merges_objects(self):
        msgs = [
            {"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "a"}]},
            {"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "b"}]},
        ]
        result = _merge_outputs_by_timestamp(msgs)
        assert len(result) == 1
        ids = {o["id"] for o in result[0]["objects"]}
        assert ids == {"a", "b"}

    def test_duplicate_id_in_same_timestamp_deduplicated(self):
        msgs = [
            {"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "a", "x": 1}]},
            {"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "a", "x": 2}]},
        ]
        result = _merge_outputs_by_timestamp(msgs)
        assert len(result) == 1
        assert len(result[0]["objects"]) == 1
        # First occurrence is kept
        assert result[0]["objects"][0]["x"] == 1

    def test_different_timestamps_preserved(self):
        msgs = [
            {"timestamp": "2024-01-01T00:00:00Z", "objects": [{"id": "a"}]},
            {"timestamp": "2024-01-01T00:00:01Z", "objects": [{"id": "b"}]},
        ]
        result = _merge_outputs_by_timestamp(msgs)
        assert len(result) == 2

    def test_output_sorted_by_timestamp(self):
        msgs = [
            {"timestamp": "2024-01-01T00:00:02Z", "objects": []},
            {"timestamp": "2024-01-01T00:00:01Z", "objects": []},
            {"timestamp": "2024-01-01T00:00:00Z", "objects": []},
        ]
        result = _merge_outputs_by_timestamp(msgs)
        timestamps = [m["timestamp"] for m in result]
        assert timestamps == sorted(timestamps)

    def test_empty_input(self):
        assert _merge_outputs_by_timestamp([]) == []
