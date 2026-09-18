# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SceneScape custom GStreamer element that consumes gvametaconvert JSON metadata
and post-decode timestamps attached upstream and publishes per-frame inference
data over MQTT (and, on request, JPEG-encoded frame images).
"""

import base64
import json
import os
import time
from collections import defaultdict
from datetime import datetime
from uuid import getnode as get_mac

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from pytz import timezone

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

from gstgva.video_frame import VideoFrame

from sscape_policies import (  # noqa: E402  pylint: disable=wrong-import-position
  detectionPolicy,
  detection3DPolicy,
  reidPolicy,
  classificationPolicy,
  ocrPolicy,
)
from sscape_3d_detector import (  # noqa: E402  pylint: disable=wrong-import-position
  Object3DChainedDataProcessor,
)
from sscape_gst_log import (  # noqa: E402  pylint: disable=wrong-import-position
  GstCategoryLogger,
)

ROOT_CA = os.environ.get("ROOT_CA", "/run/secrets/certs/scenescape-ca.pem")
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
TIMEZONE = "UTC"

METADATA_POLICIES = {
  "detectionPolicy": detectionPolicy,
  "detection3DPolicy": detection3DPolicy,
  "reidPolicy": reidPolicy,
  "classificationPolicy": classificationPolicy,
  "ocrPolicy": ocrPolicy,
}

CONVERSION_MAP = {
  "GST_VIDEO_FORMAT_NV12": cv2.COLOR_YUV2BGR_NV12,
  "GST_VIDEO_FORMAT_I420": cv2.COLOR_YUV2BGR_I420,
  "GST_VIDEO_FORMAT_BGRA": cv2.COLOR_BGRA2BGR,
  "GST_VIDEO_FORMAT_RGB": cv2.COLOR_RGB2BGR,
}

# GstDebugCategory registered at module load so `GST_DEBUG=sscape_post_inference:2`
# (or any level) toggles this plugin's verbosity like any built-in category.
_GST_LOG = GstCategoryLogger(
  "sscape_post_inference",
  "SceneScape post-inference MQTT publisher element",
)


def _get_mac_address() -> str:
  if "MACADDR" in os.environ:
    return os.environ["MACADDR"]
  a = get_mac()
  h = iter(hex(a)[2:].zfill(12))
  return ":".join(i + next(h) for i in h)


class SscapePostInferenceDataPublish(GstBase.BaseTransform):
  """Publish per-frame SceneScape metadata to MQTT.

  Consumes `GstGVAJSONMeta` attached upstream (by `gvametaconvert` and by
  `sscape_timestamp_capture`), builds the SceneScape per-frame payload, and
  publishes it directly over MQTT via paho-mqtt. Also re-attaches the final
  payload as `GstGVAJSONMeta` for any downstream GVA-aware element.
  """

  __gstmetadata__ = (
    "SceneScape Post-Inference Data Publish",
    "Filter/Metadata/Video",
    "Publish gvametaconvert inference output to MQTT with SceneScape schema",
    "Intel SceneScape",
  )

  __gsttemplates__ = (
    Gst.PadTemplate.new(
      "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
    ),
    Gst.PadTemplate.new(
      "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
    ),
  )

  __gproperties__ = {
    "cameraid": (
      str,
      "Camera identifier",
      "Camera ID used for MQTT topics and payload 'id' field.",
      None,
      GObject.ParamFlags.READWRITE,
    ),
    "metadatagenpolicy": (
      str,
      "Metadata generation policy",
      "One of: detectionPolicy, detection3DPolicy, reidPolicy, "
      "classificationPolicy, ocrPolicy.",
      "detectionPolicy",
      GObject.ParamFlags.READWRITE,
    ),
    "publish-image": (
      bool,
      "Publish annotated frame image",
      "When true, publish an annotated JPEG frame on the "
      "scenescape/image/camera/<cameraid> topic each frame.",
      False,
      GObject.ParamFlags.READWRITE,
    ),
    "detection-labels": (
      str,
      "Detection label filter (CSV)",
      "Comma-separated allow-list of detection categories to publish. "
      "Empty string publishes all categories.",
      "",
      GObject.ParamFlags.READWRITE,
    ),
    "mqtt-host": (
      str,
      "MQTT broker host",
      "Broker hostname. Falls back to MQTT_HOST env var or "
      "'broker.scenescape.intel.com'.",
      None,
      GObject.ParamFlags.READWRITE,
    ),
    "mqtt-port": (
      int,
      "MQTT broker port",
      "Broker port.",
      1, 65535, 1883,
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = _GST_LOG

    # Properties (defaults)
    self._cameraid: str = ""
    self._policy_name: str = "detectionPolicy"
    self._publish_image: bool = False
    self._detection_labels: list = []
    self._mqtt_host: str = os.environ.get(
      "MQTT_HOST", "broker.scenescape.intel.com"
    )
    self._mqtt_port: int = 1883

    # Runtime state
    self._sink_caps = None
    self._policy = METADATA_POLICIES[self._policy_name]
    self._sub_detector = Object3DChainedDataProcessor()
    self._frame_level_data = {"debug_mac": _get_mac_address()}
    self._client = None
    self._is_publish_calibration_image = False
    self._cam_auto_calibrate = False
    self._cam_auto_calibrate_intrinsics = None

  # ------------------------------------------------------------------
  # GObject property plumbing
  # ------------------------------------------------------------------

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "cameraid":
      return self._cameraid
    if name == "metadatagenpolicy":
      return self._policy_name
    if name == "publish-image":
      return self._publish_image
    if name == "detection-labels":
      return ",".join(self._detection_labels)
    if name == "mqtt-host":
      return self._mqtt_host
    if name == "mqtt-port":
      return self._mqtt_port
    raise AttributeError(f"Unknown property {name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "cameraid":
      self._cameraid = value or ""
    elif name == "metadatagenpolicy":
      if value not in METADATA_POLICIES:
        raise ValueError(
          f"Unknown metadatagenpolicy '{value}'. "
          f"Valid: {sorted(METADATA_POLICIES)}"
        )
      self._policy_name = value
      self._policy = METADATA_POLICIES[value]
    elif name == "publish-image":
      self._publish_image = bool(value)
    elif name == "detection-labels":
      if not value:
        self._detection_labels = []
      else:
        self._detection_labels = [
          s.strip() for s in value.split(",") if s.strip()
        ]
    elif name == "mqtt-host":
      if value:
        self._mqtt_host = value
    elif name == "mqtt-port":
      self._mqtt_port = int(value)
    else:
      raise AttributeError(f"Unknown property {name}")

  # ------------------------------------------------------------------
  # BaseTransform lifecycle
  # ------------------------------------------------------------------

  def do_set_caps(self, incaps, _outcaps):  # pylint: disable=arguments-differ
    self._sink_caps = incaps
    return True

  def do_start(self):  # pylint: disable=arguments-differ
    self._ensure_mqtt()
    return True

  def do_stop(self):  # pylint: disable=arguments-differ
    if self._client is not None:
      try:
        self._client.loop_stop()
        self._client.disconnect()
      except Exception:  # pylint: disable=broad-except
        self._log.exception("Error shutting down MQTT client")
      self._client = None
    return True

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    try:
      self._process_buffer(buffer)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to publish inference data for buffer")
    return Gst.FlowReturn.OK

  # ------------------------------------------------------------------
  # MQTT setup
  # ------------------------------------------------------------------

  def _ensure_mqtt(self) -> None:
    if self._client is not None:
      return
    if not self._cameraid:
      # Defer until cameraid is set (e.g. via DLSPS parameters payload).
      return
    self._frame_level_data["id"] = self._cameraid
    client = mqtt.Client()
    client.on_connect = self._on_connect
    client.on_message = self._handle_camera_message
    if ROOT_CA and os.path.exists(ROOT_CA):
      client.tls_set(ca_certs=ROOT_CA)
    try:
      client.connect(self._mqtt_host, self._mqtt_port, 120)
    except Exception:  # pylint: disable=broad-except
      self._log.exception(
        f"Failed to connect to MQTT broker "
        f"{self._mqtt_host}:{self._mqtt_port}"
      )
      return
    client.loop_start()
    self._client = client

  def _on_connect(self, client, _userdata, _flags, rc):
    if rc == 0:
      self._log.info(f"Connected to MQTT broker {self._mqtt_host}")
      topic = f"scenescape/cmd/camera/{self._cameraid}"
      client.subscribe(topic)
      self._log.info(f"Subscribed to topic: {topic}")
    else:
      self._log.error(f"MQTT connect failed, return code {rc}")

  def _handle_camera_message(self, _client, _userdata, message):
    payload = message.payload.decode("utf-8", errors="replace")
    self._log.info(f"Received camera command: '{payload}' for cam={self._cameraid}")
    if payload == "getimage":
      self._publish_image = True
      return
    if payload == "getcalibrationimage":
      self._log.info(f"Setting calibration image flag for cam={self._cameraid}")
      self._is_publish_calibration_image = True
      return
    try:
      msg = json.loads(payload)
    except json.JSONDecodeError:
      return
    if isinstance(msg, dict) and msg.get("command") == "localize":
      self._cam_auto_calibrate = True
      if "payload_intrinsics" in msg:
        self._cam_auto_calibrate_intrinsics = msg["payload_intrinsics"]

  # ------------------------------------------------------------------
  # Buffer processing
  # ------------------------------------------------------------------

  def _process_buffer(self, buffer) -> None:
    # Ensure MQTT is up (properties may have arrived after do_start).
    self._ensure_mqtt()
    if self._client is None or not self._client.is_connected():
      return

    frame = VideoFrame(buffer, caps=self._sink_caps)
    gvametadata: dict = {}
    self._collect_gva_messages(frame, gvametadata)
    self._merge_regions_into_objects(gvametadata)

    original_image_base64 = gvametadata.get("original_image_base64")
    self._build_object_data(gvametadata)

    annotated_img: dict = {}
    unannotated_img: dict = {}

    if self._publish_image:
      self._build_image_data(annotated_img, frame, True, original_image_base64)
      self._client.publish(
        f"scenescape/image/camera/{self._cameraid}",
        json.dumps(annotated_img),
      )
      self._publish_image = False

    if self._is_publish_calibration_image:
      if not unannotated_img:
        self._build_image_data(
          unannotated_img, frame, False, original_image_base64
        )
      self._client.publish(
        f"scenescape/image/calibration/camera/{self._cameraid}",
        json.dumps(unannotated_img),
      )
      self._is_publish_calibration_image = False

    if self._cam_auto_calibrate:
      self._cam_auto_calibrate = False
      if not unannotated_img:
        self._build_image_data(unannotated_img, frame, False)
      unannotated_img["calibrate"] = True
      if self._cam_auto_calibrate_intrinsics:
        unannotated_img["intrinsics"] = self._cam_auto_calibrate_intrinsics
      self._client.publish(
        f"scenescape/image/calibration/camera/{self._cameraid}",
        json.dumps(unannotated_img),
      )

    payload = json.dumps(self._frame_level_data)
    self._client.publish(f"scenescape/data/camera/{self._cameraid}", payload)
    frame.add_message(payload)

    self._log.debug(
      f"published cam={self._cameraid} "
      f"objs={len(self._frame_level_data.get('objects', []))} "
      f"ts={self._frame_level_data.get('timestamp')} "
      f"bytes={len(payload)}"
    )

  @staticmethod
  def _collect_gva_messages(frame, out: dict) -> None:
    """Merge all GVA JSON messages attached to the frame into `out`."""
    for msg in frame.messages():
      try:
        data = json.loads(msg)
      except (TypeError, json.JSONDecodeError):
        continue
      if isinstance(data, dict):
        out.update(data)

  def _merge_regions_into_objects(self, gvadata: dict) -> None:
    custom_regions = gvadata.get("custom_regions_3d", [])
    objects = gvadata.get("objects", [])
    if not custom_regions or not objects:
      return
    self._log.debug(
      f"Merging {len(custom_regions)} custom 3D regions into "
      f"{len(objects)} objects"
    )

    for det in objects:
      dx, dy, dw, dh = det.get("x"), det.get("y"), det.get("w"), det.get("h")
      best_match = None
      best_score = None
      for region in custom_regions:
        bbox = region.get("bbox", {})
        rx = bbox.get("x")
        ry = bbox.get("y")
        rw = bbox.get("w")
        rh = bbox.get("h")
        if None in (dx, dy, dw, dh, rx, ry, rw, rh):
          continue
        if dx == rx and dy == ry and dw == rw and dh == rh:
          best_match = region
          break
        score = abs(dx - rx) + abs(dy - ry) + abs(dw - rw) + abs(dh - rh)
        if best_score is None or score < best_score:
          best_score = score
          best_match = region
      if best_match is not None:
        det["extra_params"] = {
          "translation": best_match.get("translation"),
          "rotation": best_match.get("rotation"),
          "dimension": best_match.get("dimension"),
        }

  def _build_object_data(self, gvadata: dict) -> None:
    now = time.time()
    ts_next_block = gvadata.get("timestamp_for_next_block")
    self._frame_level_data.update({
      "id": self._cameraid,
      "timestamp": gvadata.get("postdecode_timestamp"),
      "debug_timestamp_end":
        f"{datetime.fromtimestamp(now, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z",
      "debug_processing_time":
        (now - float(ts_next_block)) if ts_next_block is not None else 0.0,
      "rate": float(gvadata.get("fps", 0.0)),
    })
    if "initial_intrinsics" in gvadata:
      self._frame_level_data["initial_intrinsics"] = gvadata["initial_intrinsics"]
    else:
      self._frame_level_data.pop("initial_intrinsics", None)

    objects = defaultdict(list)
    raw_objects = gvadata.get("objects") or []
    if raw_objects:
      resolution = gvadata.get("resolution", {})
      framewidth = resolution.get("width")
      frameheight = resolution.get("height")
      has_parent_ids = any("parent_id" in det for det in raw_objects)
      if has_parent_ids:
        region_id_map: dict = {}
        ordered = []
        for det in raw_objects:
          vaobj: dict = {}
          self._policy(vaobj, det, framewidth, frameheight)
          if not vaobj:
            continue
          if self._detection_labels and vaobj["category"] not in self._detection_labels:
            continue
          region_id = det.get("region_id")
          parent_id = det.get("parent_id")
          ordered.append((det, vaobj, region_id, parent_id))
          if region_id is not None:
            region_id_map[region_id] = vaobj

        for det, vaobj, _region_id, parent_id in ordered:
          otype = vaobj["category"]
          if parent_id is not None and parent_id in region_id_map:
            parent_obj = region_id_map[parent_id]
            sub_objects = parent_obj.setdefault("sub_objects", defaultdict(list))
            vaobj["id"] = self._resolve_object_id(det, sub_objects[otype])
            sub_objects[otype].append(vaobj)
          else:
            vaobj["id"] = self._resolve_object_id(det, objects[otype])
            objects[otype].append(vaobj)

        for obj_list in objects.values():
          for obj in obj_list:
            if "sub_objects" in obj:
              obj["sub_objects"] = dict(obj["sub_objects"])
      else:
        for det in raw_objects:
          vaobj = {}
          self._policy(vaobj, det, framewidth, frameheight)
          if not vaobj:
            continue
          if self._detection_labels and vaobj["category"] not in self._detection_labels:
            continue
          otype = vaobj["category"]
          vaobj["id"] = self._resolve_object_id(det, objects[otype])
          objects[otype].append(vaobj)

    self._process_sub_detections(objects)
    self._frame_level_data["objects"] = objects

  @staticmethod
  def _resolve_object_id(det: dict, existing_objects: list):
    """Preserve tracker ID when available; otherwise use sequential fallback."""
    tracker_id = det.get("id")
    if tracker_id is not None:
      return tracker_id
    return len(existing_objects) + 1

  def _process_sub_detections(self, objects: dict) -> None:
    self._frame_level_data.pop("sub_detections", None)
    if "car" in objects and "license_plate" in objects:
      intrinsics = self._frame_level_data.get("initial_intrinsics")
      sub_detections = self._sub_detector.associateObjects(
        objects, "car", "license_plate", intrinsics=intrinsics
      )
      if sub_detections:
        self._frame_level_data["sub_detections"] = sub_detections

  # ------------------------------------------------------------------
  # Image rendering
  # ------------------------------------------------------------------

  @staticmethod
  def _try_convert_to_bgr(raw_frame, video_meta):
    video_format = video_meta.format.value_name
    if video_format in CONVERSION_MAP:
      return cv2.cvtColor(raw_frame, CONVERSION_MAP[video_format])
    return np.copy(raw_frame)

  def _build_image_data(
    self, imgdatadict: dict, gvaframe, annotate: bool,
    original_image_base64: str = None,
  ) -> None:
    imgdatadict.update({
      "timestamp": self._frame_level_data.get("timestamp"),
      "id": self._cameraid,
    })
    image = None
    if original_image_base64:
      try:
        decoded_image = base64.b64decode(original_image_base64)
        original_image = cv2.imdecode(
          np.frombuffer(decoded_image, np.uint8), cv2.IMREAD_COLOR
        )
        if original_image is None:
          raise ValueError("Failed to decode original image from base64")
        image = original_image
      except Exception as exc:  # pylint: disable=broad-except
        self._log.warning(
          f"Error using original image: {exc}. Falling back to current frame."
        )

    if image is None:
      with gvaframe.data() as img:
        video_meta = gvaframe.video_meta()
        image = self._try_convert_to_bgr(img, video_meta)

    if annotate:
      self._annotate_objects(image)
      self._annotate_fps(image, self._frame_level_data.get("rate", 0.0))
    _, jpeg = cv2.imencode(".jpg", image)
    imgdatadict["image"] = base64.b64encode(jpeg).decode("utf-8")

  def _annotate_objects(self, img) -> None:
    obj_colors = ((0, 0, 255), (66, 186, 150), (207, 83, 255), (31, 156, 238))
    objects = self._frame_level_data.get("objects", {})
    if "car" in objects:
      intrinsics = self._frame_level_data.get("initial_intrinsics")
      self._sub_detector.annotateObjectAssociations(
        img, objects, obj_colors, "car", "license_plate", intrinsics=intrinsics
      )
      return
    for otype, obj_list in objects.items():
      if otype == "person":
        cindex = 0
      elif otype in ("vehicle", "bicycle"):
        cindex = 1
      else:
        cindex = 2
      for obj in obj_list:
        bbox = obj["bounding_box_px"]
        topleft = (int(bbox["x"]), int(bbox["y"]))
        bottomright = (
          int(bbox["x"] + bbox["width"]),
          int(bbox["y"] + bbox["height"]),
        )
        cv2.rectangle(img, topleft, bottomright, obj_colors[cindex], 4)

  @staticmethod
  def _annotate_fps(img, fpsval: float) -> None:
    fps_str = f"FPS {fpsval:.1f}"
    scale = int((img.shape[0] + 479) / 480)
    cv2.putText(
      img, fps_str, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
      1 * scale, (0, 0, 0), 5 * scale,
    )
    cv2.putText(
      img, fps_str, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
      1 * scale, (255, 255, 255), 2 * scale,
    )


GObject.type_register(SscapePostInferenceDataPublish)
__gstelementfactory__ = (
  "sscape_post_inference_data_publish",
  Gst.Rank.NONE,
  SscapePostInferenceDataPublish,
)
