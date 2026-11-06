# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SceneScape demo GStreamer element that publishes detections as
external-source messages.

Combines the drone_sim metadata attached by sscape_drone_motion_sim (pose,
camera mount, per-frame intrinsics) with gvadetect/gvametaconvert detections
into the unified external-source contract and publishes each frame to
scenescape/external/{source_id}/{thing_type} over TLS MQTT.

When the cameraid property is set, the element also serves the Scenescape web
UI's live-view protocol for that camera id: a "getimage" command received on
scenescape/cmd/camera/{cameraid} is answered with an annotated JPEG of the
current (warped) frame on scenescape/image/camera/{cameraid}.

Contract: docs/user-guide/microservices/controller/data_formats.md
(External Source Input Message Format, Drone Coordinate and Camera Contract).

Place after gvametaconvert, e.g.:
  ... ! sscape_drone_motion_sim ! gvadetect ! gvametaconvert !
  sscape_external_source_publish ! fakesink
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

import cv2
import paho.mqtt.client as mqtt
from gstgva.video_frame import VideoFrame

ROOT_CA = os.environ.get("ROOT_CA", "/run/secrets/certs/scenescape-ca.pem")
DRONE_SIM_META_KEY = "drone_sim"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
ANNOTATION_COLOR = (0, 255, 0)

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("sscape_ext_publish")


class ExternalSourcePublish(GstBase.BaseTransform):
  """Publish per-frame external-source messages built from upstream metadata.

  Reads two kinds of GstGVAJSONMeta from each buffer: the drone_sim block
  attached by sscape_drone_motion_sim, and the detection objects attached by
  gvametaconvert. Emits one external_source message per frame; frames without
  detections still publish, refreshing the controller's cached pose for this
  source.
  """

  __gstmetadata__ = (
    "SceneScape External Source Publish",
    "Filter/Metadata/Video",
    "Publish detections and simulated drone pose as external-source messages",
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
    "thing-type": (
      str,
      "Platform type topic segment",
      "Platform category and final segment of the external topic "
      "(scenescape/external/{source_id}/{thing_type}). Set to 'drone' "
      "to publish the synthesized platform as a drone object; detections "
      "keep their own categories.",
      "drone",
      GObject.ParamFlags.READWRITE,
    ),
    "detection-labels": (
      str,
      "Detection label filter (CSV)",
      "Comma-separated allow-list of detection categories to publish. "
      "Empty string publishes all categories.",
      "person",
      GObject.ParamFlags.READWRITE,
    ),
    "track": (
      bool,
      "Route through Scenescape tracking",
      "Published as the message 'track' value. True lets the Scene "
      "Controller assign track ids to the observations.",
      True,
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
    "cameraid": (
      str,
      "Web UI camera identifier",
      "Camera ID registered in the Scenescape web UI. When set, the element "
      "answers 'getimage' commands on scenescape/cmd/camera/<cameraid> with "
      "annotated JPEG frames on scenescape/image/camera/<cameraid> so the UI "
      "can display the simulated drone view. Empty disables image serving.",
      "",
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = _LOG

    # Properties (defaults)
    self._thing_type: str = "drone"
    self._detection_labels: list = ["person"]
    self._track: bool = True
    self._mqtt_host: str = os.environ.get(
      "MQTT_HOST", "broker.scenescape.intel.com"
    )
    self._mqtt_port: int = 1883
    self._cameraid: str = ""

    # Runtime state
    self._sink_caps = None
    self._client = None
    self._image_requested = False
    self._subscribed_camera = None

  # ------------------------------------------------------------------
  # GObject property plumbing
  # ------------------------------------------------------------------

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "thing-type":
      return self._thing_type
    if name == "detection-labels":
      return ",".join(self._detection_labels)
    if name == "track":
      return self._track
    if name == "mqtt-host":
      return self._mqtt_host
    if name == "mqtt-port":
      return self._mqtt_port
    if name == "cameraid":
      return self._cameraid
    raise AttributeError(f"Unknown property {name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "thing-type":
      self._thing_type = value or "drone"
    elif name == "detection-labels":
      self._detection_labels = [
        s.strip() for s in (value or "").split(",") if s.strip()
      ]
    elif name == "track":
      self._track = bool(value)
    elif name == "mqtt-host":
      if value:
        self._mqtt_host = value
    elif name == "mqtt-port":
      self._mqtt_port = int(value)
    elif name == "cameraid":
      self._cameraid = value or ""
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
      self._log.exception("Failed to publish external-source data for buffer")
    return Gst.FlowReturn.OK

  # ------------------------------------------------------------------
  # MQTT setup
  # ------------------------------------------------------------------

  def _ensure_mqtt(self) -> None:
    if self._client is not None:
      return
    if not ROOT_CA or not os.path.exists(ROOT_CA):
      self._log.error(
        f"MQTT TLS CA not available at {ROOT_CA!r}; refusing plaintext MQTT"
      )
      return
    client = mqtt.Client()
    client.on_connect = self._on_connect
    try:
      client.tls_set(ca_certs=ROOT_CA)
      client.connect(self._mqtt_host, self._mqtt_port, 120)
    except Exception:  # pylint: disable=broad-except
      self._log.exception(
        f"Failed to configure TLS or connect to MQTT broker "
        f"{self._mqtt_host}:{self._mqtt_port}"
      )
      return
    client.loop_start()
    self._client = client

  def _on_connect(self, _client, _userdata, _flags, rc):
    if rc == 0:
      self._log.info(f"Connected to MQTT broker {self._mqtt_host}")
      # (Re)subscribe on every connect; paho does not restore subscriptions.
      self._subscribed_camera = None
      self._ensure_camera_subscription()
    else:
      self._log.error(f"MQTT connect failed, return code {rc}")

  def _ensure_camera_subscription(self) -> None:
    """Subscribe to the web UI's camera command topic once cameraid is known."""
    if (self._client is None or not self._cameraid
        or self._subscribed_camera == self._cameraid):
      return
    self._client.on_message = self._handle_camera_command
    topic = f"scenescape/cmd/camera/{self._cameraid}"
    self._client.subscribe(topic)
    self._subscribed_camera = self._cameraid
    self._log.info(f"Serving web UI live view; subscribed to {topic}")

  def _handle_camera_command(self, _client, _userdata, message):
    payload = message.payload.decode("utf-8", errors="replace")
    if payload == "getimage":
      self._image_requested = True

  # ------------------------------------------------------------------
  # Buffer processing
  # ------------------------------------------------------------------

  @staticmethod
  def _collect_gva_messages(frame) -> dict:
    """Merge all GVA JSON messages attached to the frame."""
    merged: dict = {}
    for message in frame.messages():
      try:
        data = json.loads(message)
      except (TypeError, json.JSONDecodeError):
        continue
      if isinstance(data, dict):
        merged.update(data)
    return merged

  @staticmethod
  def _map_detection(item: dict) -> dict:
    """Map one gvametaconvert detection to an external_detection entry."""
    detection = item.get("detection")
    if not isinstance(detection, dict) or "confidence" not in detection:
      return {}
    category = detection.get("label") or str(detection.get("label_id"))
    return {
      "category": category,
      "confidence": detection["confidence"],
      "bounding_box_px": {
        "x": item["x"], "y": item["y"],
        "width": item["w"], "height": item["h"],
      },
    }

  def _map_detections(self, gvadata: dict) -> list:
    """Map gvametaconvert detections to external_detection entries."""
    observations = []
    for item in gvadata.get("objects") or []:
      observation = self._map_detection(item)
      if not observation:
        continue
      if self._detection_labels and observation["category"] not in self._detection_labels:
        continue
      observations.append(observation)
    return observations

  def _message_timestamp(self, gvadata: dict, drone_meta: dict) -> str:
    """ISO 8601 UTC acquisition timestamp matching the simulated pose.

    Formats the sim_time instant that drove the frame warp and pose. If the
    optional sscape_timestamp_capture element runs upstream, its NTP-corrected
    postdecode_timestamp (derived from the same instant) is preferred.
    """
    timestamp = gvadata.get("postdecode_timestamp")
    if timestamp:
      return timestamp
    acquired = datetime.fromtimestamp(
      float(drone_meta["sim_time"]), tz=timezone.utc
    )
    return f"{acquired.strftime(DATETIME_FORMAT)[:-3]}Z"

  def _process_buffer(self, buffer) -> None:
    self._ensure_mqtt()
    if self._client is None or not self._client.is_connected():
      return
    self._ensure_camera_subscription()

    frame = VideoFrame(buffer, caps=self._sink_caps)
    gvadata = self._collect_gva_messages(frame)
    drone_meta = gvadata.get(DRONE_SIM_META_KEY)
    if not drone_meta:
      self._log.warning(
        "No drone_sim metadata on buffer; is sscape_drone_motion_sim upstream?"
      )
      return

    source_id = drone_meta["source_id"]
    message = {
      "timestamp": self._message_timestamp(gvadata, drone_meta),
      "source_id": source_id,
      "pose": drone_meta["pose"],
      "track": self._track,
      "cameras": [{
        "id": drone_meta["camera_id"],
        "mount": drone_meta["mount"],
        "intrinsics": drone_meta["intrinsics"],
        # track=false discards pixels in the Controller and the schema
        # requires ids on camera observations, so publish none here.
        "objects": self._map_detections(gvadata) if self._track else [],
      }],
    }

    topic = f"scenescape/external/{source_id}/{self._thing_type}"
    self._client.publish(topic, json.dumps(message))
    self._log.debug(
      f"published {topic} objs={len(message['cameras'][0]['objects'])} "
      f"ts={message['timestamp']}"
    )

    if self._image_requested and self._cameraid:
      self._image_requested = False
      self._publish_image(frame, message)

  def _publish_image(self, frame, message: dict) -> None:
    """Answer a web UI 'getimage' command with an annotated JPEG frame."""
    with frame.data(Gst.MapFlags.READ) as image:
      annotated = image.copy()
    for observation in message["cameras"][0]["objects"]:
      box = observation["bounding_box_px"]
      top_left = (int(box["x"]), int(box["y"]))
      bottom_right = (int(box["x"] + box["width"]), int(box["y"] + box["height"]))
      cv2.rectangle(annotated, top_left, bottom_right, ANNOTATION_COLOR, 2)
      cv2.putText(annotated, observation["category"],
                  (top_left[0], max(top_left[1] - 6, 12)),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, ANNOTATION_COLOR, 1)
    ok, jpeg = cv2.imencode(".jpg", annotated)
    if not ok:
      self._log.error("Failed to JPEG-encode frame for web UI live view")
      return
    payload = {
      "timestamp": message["timestamp"],
      "id": self._cameraid,
      "image": base64.b64encode(jpeg).decode("utf-8"),
    }
    self._client.publish(
      f"scenescape/image/camera/{self._cameraid}", json.dumps(payload))


GObject.type_register(ExternalSourcePublish)
__gstelementfactory__ = (
  "sscape_external_source_publish",
  Gst.Rank.NONE,
  ExternalSourcePublish,
)
