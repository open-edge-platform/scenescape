# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests proving that SscapePostInferenceDataPublish's own logic (property
plumbing, MQTT connect handling, camera-command dispatch, per-frame object
data construction, custom-region merging, tracker-id resolution, and MQTT
publish orchestration) is testable on the host by stubbing out
gi/GstBase/gstgva (see conftest.py) and the paho MQTT client, without a real
PyGObject/GStreamer installation and without any production code changes.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sscape_post_inference_data_publish import (  # noqa: E402
  SscapePostInferenceDataPublish,
)
import sscape_post_inference_data_publish as pubmod  # noqa: E402

def make_prop(name):
  return SimpleNamespace(name=name)

class RecordingVideoFrame:
  """Test double that records every constructed instance, the GVA JSON
  messages seeded into it and the messages produced by add_message(), so
  assertions can inspect what do_transform_ip published downstream."""

  instances = []

  def __init__(self, buffer, caps=None, seed_messages=None):
    self.buffer = buffer
    self.caps = caps
    self._seed_messages = list(seed_messages or [])
    self.added_messages = []
    RecordingVideoFrame.instances.append(self)

  # gstgva.VideoFrame API surface used by the plugin
  def messages(self):
    return list(self._seed_messages)

  def add_message(self, payload):
    self.added_messages.append(payload)


@pytest.fixture
def element():
  return SscapePostInferenceDataPublish()


@pytest.fixture
def connected_element(element):
  """Element with a pre-injected MQTT client that reports as connected, so
  tests can exercise buffer processing without touching real networking."""
  element._cameraid = "cam-1"
  element._frame_level_data["id"] = "cam-1"
  fake_client = MagicMock()
  fake_client.is_connected.return_value = True
  element._client = fake_client
  return element


class TestProperties:

  def test_defaults(self, element):
    assert element.do_get_property(make_prop("cameraid")) == ""
    assert element.do_get_property(make_prop("metadatagenpolicy")) == "detectionPolicy"
    assert element.do_get_property(make_prop("publish-image")) is False
    assert element.do_get_property(make_prop("detection-labels")) == ""
    assert element.do_get_property(make_prop("mqtt-port")) == 1883

  def test_set_and_get_cameraid(self, element):
    element.do_set_property(make_prop("cameraid"), "cam-42")
    assert element.do_get_property(make_prop("cameraid")) == "cam-42"

  def test_set_cameraid_none_becomes_empty_string(self, element):
    element.do_set_property(make_prop("cameraid"), None)
    assert element.do_get_property(make_prop("cameraid")) == ""

  def test_set_and_get_metadatagenpolicy_switches_policy_callable(self, element):
    element.do_set_property(make_prop("metadatagenpolicy"), "reidPolicy")
    assert element.do_get_property(make_prop("metadatagenpolicy")) == "reidPolicy"
    assert element._policy is pubmod.METADATA_POLICIES["reidPolicy"]

  def test_unknown_metadatagenpolicy_raises(self, element):
    with pytest.raises(ValueError):
      element.do_set_property(make_prop("metadatagenpolicy"), "nopePolicy")

  def test_set_and_get_publish_image(self, element):
    element.do_set_property(make_prop("publish-image"), True)
    assert element.do_get_property(make_prop("publish-image")) is True

  def test_detection_labels_csv_is_split(self, element):
    element.do_set_property(make_prop("detection-labels"), "person, car ,,bicycle")
    assert element._detection_labels == ["person", "car", "bicycle"]
    assert element.do_get_property(make_prop("detection-labels")) == "person,car,bicycle"

  def test_detection_labels_empty_string_clears_list(self, element):
    element.do_set_property(make_prop("detection-labels"), "person")
    element.do_set_property(make_prop("detection-labels"), "")
    assert element._detection_labels == []

  def test_set_and_get_mqtt_host(self, element):
    element.do_set_property(make_prop("mqtt-host"), "broker.local")
    assert element.do_get_property(make_prop("mqtt-host")) == "broker.local"

  def test_set_mqtt_host_empty_leaves_previous_value(self, element):
    element.do_set_property(make_prop("mqtt-host"), "broker.local")
    element.do_set_property(make_prop("mqtt-host"), "")
    assert element.do_get_property(make_prop("mqtt-host")) == "broker.local"

  def test_set_and_get_mqtt_port_coerces_to_int(self, element):
    element.do_set_property(make_prop("mqtt-port"), "8883")
    assert element.do_get_property(make_prop("mqtt-port")) == 8883

  def test_get_unknown_property_raises(self, element):
    with pytest.raises(AttributeError):
      element.do_get_property(make_prop("does-not-exist"))

  def test_set_unknown_property_raises(self, element):
    with pytest.raises(AttributeError):
      element.do_set_property(make_prop("does-not-exist"), 1)


class TestEnsureMqtt:

  def test_skipped_without_cameraid(self, element, monkeypatch):
    fake_mqtt = MagicMock()
    monkeypatch.setattr(pubmod, "mqtt", fake_mqtt)
    element._ensure_mqtt()
    fake_mqtt.Client.assert_not_called()
    assert element._client is None

  def test_connects_when_cameraid_set(self, element, monkeypatch):
    element._cameraid = "cam-7"
    element._mqtt_host = "broker.local"
    element._mqtt_port = 4321
    fake_mqtt = MagicMock()
    monkeypatch.setattr(pubmod, "mqtt", fake_mqtt)
    monkeypatch.setattr(pubmod.os.path, "exists", lambda _p: False)

    element._ensure_mqtt()

    client = fake_mqtt.Client.return_value
    client.connect.assert_called_once_with("broker.local", 4321, 120)
    client.loop_start.assert_called_once()
    assert element._client is client
    assert element._frame_level_data["id"] == "cam-7"

  def test_only_connects_once(self, element, monkeypatch):
    element._cameraid = "cam-7"
    fake_mqtt = MagicMock()
    monkeypatch.setattr(pubmod, "mqtt", fake_mqtt)
    monkeypatch.setattr(pubmod.os.path, "exists", lambda _p: False)

    element._ensure_mqtt()
    element._ensure_mqtt()

    fake_mqtt.Client.assert_called_once()

  def test_connect_failure_leaves_client_unset(self, element, monkeypatch):
    element._cameraid = "cam-7"
    fake_mqtt = MagicMock()
    fake_mqtt.Client.return_value.connect.side_effect = OSError("unreachable")
    monkeypatch.setattr(pubmod, "mqtt", fake_mqtt)
    monkeypatch.setattr(pubmod.os.path, "exists", lambda _p: False)

    element._ensure_mqtt()  # must not raise

    assert element._client is None


class TestOnConnect:

  def test_success_subscribes_to_camera_topic(self, element):
    element._cameraid = "cam-9"
    client = MagicMock()
    element._on_connect(client, None, None, 0)
    client.subscribe.assert_called_once_with("scenescape/cmd/camera/cam-9")

  def test_failure_does_not_subscribe(self, element):
    element._cameraid = "cam-9"
    client = MagicMock()
    element._on_connect(client, None, None, 5)
    client.subscribe.assert_not_called()


class TestHandleCameraMessage:

  def test_getimage_sets_publish_flag(self, element):
    element._handle_camera_message(None, None, SimpleNamespace(payload=b"getimage"))
    assert element._publish_image is True

  def test_getcalibrationimage_sets_flag(self, element):
    element._handle_camera_message(
      None, None, SimpleNamespace(payload=b"getcalibrationimage"),
    )
    assert element._is_publish_calibration_image is True

  def test_localize_sets_auto_calibrate_and_intrinsics(self, element):
    payload = json.dumps({"command": "localize", "payload_intrinsics": {"fx": 1}})
    element._handle_camera_message(
      None, None, SimpleNamespace(payload=payload.encode("utf-8")),
    )
    assert element._cam_auto_calibrate is True
    assert element._cam_auto_calibrate_intrinsics == {"fx": 1}

  def test_localize_without_intrinsics_still_triggers_calibrate(self, element):
    payload = json.dumps({"command": "localize"})
    element._handle_camera_message(
      None, None, SimpleNamespace(payload=payload.encode("utf-8")),
    )
    assert element._cam_auto_calibrate is True
    assert element._cam_auto_calibrate_intrinsics is None

  def test_invalid_json_is_ignored(self, element):
    element._handle_camera_message(
      None, None, SimpleNamespace(payload=b"{not json"),
    )
    assert element._cam_auto_calibrate is False
    assert element._publish_image is False

  def test_unknown_json_command_is_ignored(self, element):
    payload = json.dumps({"command": "something-else"})
    element._handle_camera_message(
      None, None, SimpleNamespace(payload=payload.encode("utf-8")),
    )
    assert element._cam_auto_calibrate is False


class TestResolveObjectId:

  def test_uses_tracker_id_when_present(self):
    assert SscapePostInferenceDataPublish._resolve_object_id(
      {"id": 42}, ["a", "b"]
    ) == 42

  def test_falls_back_to_sequential_id_when_missing(self):
    assert SscapePostInferenceDataPublish._resolve_object_id(
      {}, ["a", "b"]
    ) == 3


class TestMergeRegionsIntoObjects:

  def test_no_regions_no_op(self, element):
    gvadata = {"objects": [{"x": 1, "y": 2, "w": 3, "h": 4}]}
    element._merge_regions_into_objects(gvadata)
    assert "extra_params" not in gvadata["objects"][0]

  def test_exact_match_attaches_extra_params(self, element):
    region = {
      "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
      "translation": [0.1, 0.2, 0.3],
      "rotation": [0, 0, 0, 1],
      "dimension": [1, 1, 1],
    }
    gvadata = {
      "objects": [{"x": 1, "y": 2, "w": 3, "h": 4}],
      "custom_regions_3d": [region],
    }
    element._merge_regions_into_objects(gvadata)
    assert gvadata["objects"][0]["extra_params"] == {
      "translation": [0.1, 0.2, 0.3],
      "rotation": [0, 0, 0, 1],
      "dimension": [1, 1, 1],
    }

  def test_nearest_bbox_wins_when_no_exact_match(self, element):
    far_region = {
      "bbox": {"x": 100, "y": 100, "w": 100, "h": 100},
      "translation": [9, 9, 9], "rotation": [0, 0, 0, 1], "dimension": [1, 1, 1],
    }
    near_region = {
      "bbox": {"x": 2, "y": 2, "w": 3, "h": 4},
      "translation": [1, 1, 1], "rotation": [0, 0, 0, 1], "dimension": [2, 2, 2],
    }
    gvadata = {
      "objects": [{"x": 1, "y": 2, "w": 3, "h": 4}],
      "custom_regions_3d": [far_region, near_region],
    }
    element._merge_regions_into_objects(gvadata)
    assert gvadata["objects"][0]["extra_params"]["translation"] == [1, 1, 1]


class TestBuildObjectData:

  @staticmethod
  def _det(label, x=0, y=0, w=10, h=10, **extra):
    d = {
      "x": x, "y": y, "w": w, "h": h,
      "detection": {"label": label, "confidence": 0.9},
    }
    d.update(extra)
    return d

  def _gvadata(self, objects, **extra):
    base = {
      "postdecode_timestamp": "2026-07-21T00:00:00.000Z",
      "timestamp_for_next_block": 0.0,
      "fps": 30.0,
      "resolution": {"width": 640, "height": 480},
      "objects": objects,
    }
    base.update(extra)
    return base

  def test_frame_level_data_populated_from_gvadata(self, element):
    element._cameraid = "cam-a"
    gvadata = self._gvadata([], fps=15.5, initial_intrinsics={"fx": 1000})

    element._build_object_data(gvadata)

    fld = element._frame_level_data
    assert fld["id"] == "cam-a"
    assert fld["timestamp"] == "2026-07-21T00:00:00.000Z"
    assert fld["rate"] == 15.5
    assert fld["initial_intrinsics"] == {"fx": 1000}
    assert fld["debug_timestamp_end"].endswith("Z")
    assert isinstance(fld["objects"], dict) and not fld["objects"]

  def test_detection_labels_filter_excludes_non_matching(self, element):
    element._detection_labels = ["person"]
    gvadata = self._gvadata([self._det("person"), self._det("car")])

    element._build_object_data(gvadata)

    objects = element._frame_level_data["objects"]
    assert list(objects.keys()) == ["person"]
    assert len(objects["person"]) == 1

  def test_tracker_id_is_preserved(self, element):
    gvadata = self._gvadata([self._det("person", id=7)])
    element._build_object_data(gvadata)
    assert element._frame_level_data["objects"]["person"][0]["id"] == 7

  def test_fallback_sequential_id_when_tracker_absent(self, element):
    gvadata = self._gvadata([self._det("person"), self._det("person")])
    element._build_object_data(gvadata)
    ids = [o["id"] for o in element._frame_level_data["objects"]["person"]]
    assert ids == [1, 2]

  def test_parent_id_nests_children_under_parent(self, element):
    parent = self._det("car", region_id=10)
    child = self._det("license_plate", region_id=11, parent_id=10)
    gvadata = self._gvadata([parent, child])

    element._build_object_data(gvadata)

    cars = element._frame_level_data["objects"]["car"]
    assert len(cars) == 1
    assert "sub_objects" in cars[0]
    assert isinstance(cars[0]["sub_objects"], dict)
    assert cars[0]["sub_objects"]["license_plate"][0]["category"] == "license_plate"
    # Child must not also appear at top level
    assert "license_plate" not in element._frame_level_data["objects"]

  def test_orphan_parent_id_falls_back_to_top_level(self, element):
    orphan = self._det("license_plate", region_id=99, parent_id=12345)
    gvadata = self._gvadata([orphan])
    element._build_object_data(gvadata)
    assert "license_plate" in element._frame_level_data["objects"]

  def test_empty_objects_produces_empty_dict(self, element):
    element._build_object_data(self._gvadata([]))
    assert element._frame_level_data["objects"] == {}


class TestProcessSubDetections:

  def test_associates_car_with_license_plate(self, element):
    element._sub_detector = MagicMock()
    element._sub_detector.associateObjects.return_value = [{"any": "thing"}]
    objects = {"car": [{"id": 1}], "license_plate": [{"id": 2}]}

    element._process_sub_detections(objects)

    element._sub_detector.associateObjects.assert_called_once()
    assert element._frame_level_data["sub_detections"] == [{"any": "thing"}]

  def test_no_association_without_both_categories(self, element):
    element._sub_detector = MagicMock()
    element._process_sub_detections({"car": [{"id": 1}]})
    element._sub_detector.associateObjects.assert_not_called()
    assert "sub_detections" not in element._frame_level_data


class TestProcessBuffer:

  @pytest.fixture(autouse=True)
  def _patch_video_frame(self, monkeypatch):
    RecordingVideoFrame.instances = []

    def _factory(buffer, caps=None):
      # Seed the frame with a timestamp-capture-style GVA message and a
      # gvametaconvert-style detections message, mirroring how the real
      # upstream elements attach data.
      return RecordingVideoFrame(
        buffer, caps=caps,
        seed_messages=[
          json.dumps({
            "postdecode_timestamp": "2026-07-21T00:00:00.000Z",
            "timestamp_for_next_block": 0.0,
            "fps": 25.0,
          }),
          json.dumps({
            "resolution": {"width": 320, "height": 240},
            "objects": [{
              "x": 0, "y": 0, "w": 10, "h": 10,
              "detection": {"label": "person", "confidence": 0.9},
            }],
          }),
        ],
      )

    monkeypatch.setattr(pubmod, "VideoFrame", _factory)

  def test_skipped_when_mqtt_not_connected(self, element, monkeypatch):
    # No cameraid -> _ensure_mqtt is a no-op, client stays None
    element.do_transform_ip(MagicMock())
    assert RecordingVideoFrame.instances == []

  def test_publishes_data_topic_and_frame_message(self, connected_element):
    connected_element.do_transform_ip(MagicMock())

    client = connected_element._client
    topics = [call.args[0] for call in client.publish.call_args_list]
    assert "scenescape/data/camera/cam-1" in topics
    # Also propagated downstream via frame.add_message
    frame = RecordingVideoFrame.instances[-1]
    assert len(frame.added_messages) == 1
    payload = json.loads(frame.added_messages[0])
    assert payload["id"] == "cam-1"
    assert "person" in payload["objects"]

  def test_publish_image_flag_publishes_image_topic_once(self, connected_element, monkeypatch):
    connected_element._publish_image = True
    # Bypass real image encoding
    monkeypatch.setattr(
      connected_element, "_build_image_data",
      lambda imgdatadict, *_a, **_kw: imgdatadict.update({"image": "base64"}),
    )

    connected_element.do_transform_ip(MagicMock())

    topics = [call.args[0] for call in connected_element._client.publish.call_args_list]
    assert "scenescape/image/camera/cam-1" in topics
    assert connected_element._publish_image is False

  def test_calibration_image_flag_publishes_calibration_topic_once(
    self, connected_element, monkeypatch,
  ):
    connected_element._is_publish_calibration_image = True
    monkeypatch.setattr(
      connected_element, "_build_image_data",
      lambda imgdatadict, *_a, **_kw: imgdatadict.update({"image": "base64"}),
    )

    connected_element.do_transform_ip(MagicMock())

    topics = [call.args[0] for call in connected_element._client.publish.call_args_list]
    assert "scenescape/image/calibration/camera/cam-1" in topics
    assert connected_element._is_publish_calibration_image is False

  def test_auto_calibrate_publishes_calibration_topic_with_intrinsics(
    self, connected_element, monkeypatch,
  ):
    connected_element._cam_auto_calibrate = True
    connected_element._cam_auto_calibrate_intrinsics = {"fx": 1234}
    captured = {}

    def _fake_build(imgdatadict, *_a, **_kw):
      imgdatadict.update({"image": "base64"})
      captured["img"] = imgdatadict

    monkeypatch.setattr(connected_element, "_build_image_data", _fake_build)

    connected_element.do_transform_ip(MagicMock())

    assert connected_element._cam_auto_calibrate is False
    # Locate the calibration publish
    publishes = connected_element._client.publish.call_args_list
    calib = next(
      c for c in publishes
      if c.args[0] == "scenescape/image/calibration/camera/cam-1"
    )
    payload = json.loads(calib.args[1])
    assert payload["calibrate"] is True
    assert payload["intrinsics"] == {"fx": 1234}

  def test_do_transform_ip_never_raises_and_still_returns_ok(
    self, connected_element, monkeypatch,
  ):
    monkeypatch.setattr(
      connected_element, "_process_buffer",
      MagicMock(side_effect=RuntimeError("boom")),
    )

    result = connected_element.do_transform_ip(MagicMock())

    assert result == pubmod.Gst.FlowReturn.OK
