# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""ONVIF movement and existing SceneScape calibration APIs, not a pose service."""

import base64
import json
import time

import cv2
import numpy as np
import requests

from config import read_json, validate_points


class TagCoverageError(ValueError):
  """A valid calibration request completed without usable AprilTag coverage."""


class Manager:
  """Authenticated HTTPS access; writes are only used by the apply command."""

  def __init__(self, config):
    self.url = config["manager_url"].rstrip("/")
    self.session = requests.Session()
    self.session.verify = config["ca_cert"]
    auth = read_json(config["manager_auth"])
    result = self.request("POST", "auth", data={"username": auth["user"], "password": auth["password"]})
    self.session.headers["Authorization"] = f"Token {result['token']}"

  def request(self, method, path, **kwargs):
    """Make an API request and raise on any failed response."""
    reply = self.session.request(method, f"{self.url}/{path}", timeout=60, **kwargs)
    reply.raise_for_status()
    return reply.json()

  def camera(self, uid):
    """Read one existing Manager camera."""
    return self.request("GET", f"camera/{uid}")


class Camera:
  """Bounded absolute ONVIF moves preserving zoom."""

  def __init__(self, config, validate_limits=True):
    from onvif import ONVIFCamera
    from zeep.transports import Transport

    account = read_json(config["onvif"]["auth"])
    device = config["onvif"]
    self.motion = config["motion"]
    camera = ONVIFCamera(device["host"], device["port"], account["username"], account["password"],
                        transport=Transport(timeout=10, operation_timeout=10))
    self.ptz = camera.create_ptz_service()
    # Bound transport reads, including status polling.
    self.ptz.zeep_client.transport.operation_timeout = 10
    media = camera.create_media_service()
    media.zeep_client.transport.operation_timeout = 10
    profiles = [p for p in media.GetProfiles() if p.PTZConfiguration is not None]
    available_tokens = [p.token for p in profiles]
    token = device.get("profile_token")
    profiles = [p for p in profiles if token is None or p.token == token]
    if len(profiles) != 1:
      raise ValueError("Set onvif.profile_token to exactly one PTZ-capable media profile; "
                       f"available tokens: {available_tokens}")
    self.token = profiles[0].token
    options = self.ptz.GetConfigurationOptions(
      {"ConfigurationToken": profiles[0].PTZConfiguration.token})
    position = self.status().Position
    self.zoom = position.Zoom
    uri = (position.PanTilt.space or
           profiles[0].PTZConfiguration.DefaultAbsolutePantTiltPositionSpace)
    spaces = [s for s in options.Spaces.AbsolutePanTiltPositionSpace if s.URI == uri]
    if len(spaces) != 1:
      raise ValueError("Camera must advertise its current absolute pan/tilt position space")
    space = spaces[0]
    self.space = {"uri": space.URI, "pan_min": space.XRange.Min,
                  "pan_max": space.XRange.Max, "tilt_min": space.YRange.Min,
                  "tilt_max": space.YRange.Max}
    for axis in ("pan", "tilt") if validate_limits else ():
      low, high = self.motion[f"{axis}_range"]
      if low < self.space[f"{axis}_min"] or high > self.space[f"{axis}_max"]:
        raise ValueError(f"{axis}_range exceeds this profile's advertised position space")

  def status(self):
    """Read raw status without inventing a position on failure."""
    return self.ptz.GetStatus({"ProfileToken": self.token})

  def move(self, pan, tilt):
    """Wait for actual feedback and then the configured image settling delay."""
    for name, value in (("pan", pan), ("tilt", tilt)):
      low, high = self.motion[f"{name}_range"]
      if not low <= value <= high:
        raise ValueError(f"Refusing {name}={value}: outside configured safe limits")
    position = {"PanTilt": {"x": pan, "y": tilt, "space": self.space["uri"]}}
    if self.zoom is not None:
      position["Zoom"] = self.zoom
    self.ptz.AbsoluteMove({"ProfileToken": self.token, "Position": position})
    deadline = time.monotonic() + self.motion["timeout_s"]
    while time.monotonic() < deadline:
      status = self.status()
      actual = status.Position.PanTilt
      zoom = status.Position.Zoom
      if self.zoom is not None and (zoom is None or abs(zoom.x - self.zoom.x) > 0.001):
        raise RuntimeError("Zoom changed during measurement; refusing mixed-zoom calibration")
      idle = getattr(getattr(status, "MoveStatus", None), "PanTilt", None) != "MOVING"
      if (idle and abs(actual.x - pan) <= self.motion["tolerance"] and
          abs(actual.y - tilt) <= self.motion["tolerance"]):
        time.sleep(self.motion["settle_s"])
        return [float(actual.x), float(actual.y)]
      time.sleep(0.2)
    raise TimeoutError(f"Camera did not reach pan={pan}, tilt={tilt}")

  def home(self):
    """Approach home from the configured direction on both axes."""
    home = self.motion["home"]
    before = [p + (d if a == "decreasing" else -d)
              for p, d, a in zip(home, self.motion["approach_offset"], self.motion["approach"])]
    self.move(*before)
    return self.move(*home)


class Tags:
  """Request fresh calibration frames, then wait for AprilTag correspondences."""

  def __init__(self, config):
    self.config = config
    self.session = requests.Session()
    self.session.verify = config["ca_cert"]

  def image(self):
    """Wait for SUBACK before requesting an image; retained frames are not fresh."""
    import paho.mqtt.client as mqtt

    config = self.config
    uid = config["camera_uid"]
    topic = f"scenescape/image/calibration/camera/{uid}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    account = read_json(config["mqtt"]["auth"])
    client.username_pw_set(account["user"], account["password"])
    client.tls_set(ca_certs=config["ca_cert"])
    received, state = [], {"subscribed": False}

    def connected(client, userdata, flags, reason, properties):
      if reason.is_failure:
        raise RuntimeError(f"MQTT connection refused: {reason}")
      client.subscribe(topic, qos=1)

    def subscribed(client, userdata, mid, reasons, properties):
      if any(r.is_failure for r in reasons):
        raise RuntimeError("MQTT calibration-image subscription refused")
      state["subscribed"] = True

    def message(client, userdata, msg):
      if not msg.retain:
        received.append(json.loads(msg.payload)["image"])

    client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, message
    client.connect(config["mqtt"]["host"], config["mqtt"]["port"], keepalive=30)
    deadline = time.monotonic() + 20
    try:
      while not state["subscribed"]:
        if time.monotonic() >= deadline:
          raise TimeoutError("MQTT subscription timed out")
        if client.loop(timeout=0.2) != mqtt.MQTT_ERR_SUCCESS:
          raise RuntimeError("MQTT connection lost")
      # Drain any pre-request traffic received with SUBACK.
      received.clear()
      info = client.publish(f"scenescape/cmd/camera/{uid}", "getcalibrationimage", qos=1)
      if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError("Could not publish calibration-image request")
      while not received:
        if time.monotonic() >= deadline:
          raise TimeoutError("No fresh calibration image; check the camera pipeline")
        if client.loop(timeout=0.2) != mqtt.MQTT_ERR_SUCCESS:
          raise RuntimeError("MQTT connection lost while waiting for image")
      return received[-1]
    finally:
      client.disconnect()

  def collect(self):
    """Return matched raw image/world points and actual frame resolution."""
    image = self.image()
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(image, validate=True), np.uint8),
                           cv2.IMREAD_COLOR)
    if decoded is None:
      raise ValueError("Calibration image is not a decodable JPEG/PNG")
    url = (f"{self.config['autocalibration_url'].rstrip('/')}/cameras/"
           f"{self.config['camera_uid']}/calibration")
    reply = self.session.post(url, json={"image": image}, timeout=15)
    reply.raise_for_status()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
      reply = self.session.get(url, timeout=15)
      reply.raise_for_status()
      result = reply.json()
      if result.get("status") == "pending":
        raise TagCoverageError(
          f"AprilTag coverage unavailable: {result.get('message', 'no details')}")
      if result.get("status") in ("success", "error"):
        if result.get("status") == "error":
          raise TagCoverageError(
            f"AprilTag calibration rejected: {result.get('message', 'no details')}")
        stop = {"points_2d": result.get("calibration_points_2d", []),
                "points_3d": result.get("calibration_points_3d", [])}
        if len(stop["points_2d"]) < 6:
          raise TagCoverageError("Fewer than six matched AprilTag points")
        validate_points(stop)
        stop["resolution"] = [int(decoded.shape[1]), int(decoded.shape[0])]
        return stop
      time.sleep(0.5)
    raise TimeoutError("AprilTag calibration did not finish in 90 seconds")
