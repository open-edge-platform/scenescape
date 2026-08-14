# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MAVLink → Scenescape external_source MQTT adapter.

Reads GLOBAL_POSITION_INT and ATTITUDE from a MAVLink connection and publishes
authenticated MQTT messages on scenescape/external/{publisher_id}/{thing_type}
where publisher_id is SCENESCAPE_SOURCE_ID.

Contract fields and examples:
  docs/user-guide/microservices/controller/data_formats.md
  (External Source Input Message Format)

How-to:
  docs/user-guide/how-to-guides/publish-external-source-adapter.md

This adapter maps the vehicle's own GNSS/attitude into a wgs84 pose. Optionally
it also reports the vehicle as a tracked object at the source local origin
([0, 0, 0]) using the same persistent id as source_id.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time

from pymavlink import mavutil

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

logger = logging.getLogger(__name__)

IDENTITY_QUAT = [0.0, 0.0, 0.0, 1.0]


def _env(name, default=None, required=False):
  value = os.environ.get(name, default)
  if required and (value is None or value == ""):
    raise SystemExit(f"Missing required environment variable: {name}")
  return value


def euler_zyx_to_quaternion(roll, pitch, yaw):
  """Convert MAVLink ATTITUDE roll/pitch/yaw (radians) to quaternion (x,y,z,w)."""
  cy = math.cos(yaw * 0.5)
  sy = math.sin(yaw * 0.5)
  cp = math.cos(pitch * 0.5)
  sp = math.sin(pitch * 0.5)
  cr = math.cos(roll * 0.5)
  sr = math.sin(roll * 0.5)
  return [
    sr * cp * cy - cr * sp * sy,
    cr * sp * cy + sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
    cr * cp * cy + sr * sp * sy,
  ]


class MavlinkState:
  """Accumulates the latest usable MAVLink position and attitude."""

  def __init__(self):
    self.lat = None
    self.lon = None
    self.alt_m = None
    self.rotation = list(IDENTITY_QUAT)
    self.have_attitude = False

  @property
  def have_position(self):
    return self.lat is not None and self.lon is not None and self.alt_m is not None

  def update(self, msg):
    msg_type = msg.get_type()
    if msg_type == "GLOBAL_POSITION_INT":
      # lat/lon: degE7; alt: mm above MSL
      self.lat = msg.lat / 1.0e7
      self.lon = msg.lon / 1.0e7
      self.alt_m = msg.alt / 1000.0
      return True
    if msg_type == "GPS_RAW_INT" and not self.have_position:
      if msg.fix_int >= 2 and msg.lat != 0 and msg.lon != 0:
        self.lat = msg.lat / 1.0e7
        self.lon = msg.lon / 1.0e7
        self.alt_m = msg.alt / 1000.0
        return True
    if msg_type == "ATTITUDE":
      self.rotation = euler_zyx_to_quaternion(msg.roll, msg.pitch, msg.yaw)
      self.have_attitude = True
      return True
    return False


def build_payload(state, source_id, category, publish_self, include_pose=True):
  """Build an external_source dict from current MAVLink state.

  See data_formats.md for required fields; do not invent alternate shapes.
  """
  objects = []
  if publish_self:
    # Vehicle reports itself at the source local origin.
    objects.append({
      "id": source_id,
      "category": category,
      "translation": [0.0, 0.0, 0.0],
      "rotation": list(state.rotation),
    })

  payload = {
    "timestamp": get_iso_time(),
    "source_id": source_id,
    "objects": objects,
  }
  if include_pose and state.have_position:
    payload["pose"] = {
      "reference_frame": "wgs84",
      "lat_long_alt": [state.lat, state.lon, state.alt_m],
      "rotation": list(state.rotation),
      "provider": "mavlink",
    }
  return payload


def parse_args(argv=None):
  parser = argparse.ArgumentParser(
    description="Publish MAVLink GNSS/attitude as Scenescape external_source MQTT messages.")
  parser.add_argument(
    "--connection",
    default=_env("MAVLINK_CONNECTION", "udp:0.0.0.0:14550"),
    help="pymavlink connection string (default: udp:0.0.0.0:14550 or MAVLINK_CONNECTION)")
  parser.add_argument(
    "--baud", type=int, default=int(_env("MAVLINK_BAUD", "57600")),
    help="Serial baud rate when connection is a device path")
  parser.add_argument(
    "--publish-hz", type=float, default=float(_env("PUBLISH_HZ", "5")),
    help="MQTT publish rate in Hz")
  parser.add_argument(
    "--publish-self", action="store_true",
    default=_env("PUBLISH_SELF", "true").lower() in ("1", "true", "yes"),
    help="Include the vehicle as a tracked object at [0,0,0] (default: on)")
  parser.add_argument(
    "--no-publish-self", action="store_false", dest="publish_self",
    help="Pose-only messages (empty objects array)")
  parser.add_argument(
    "--pose-every-n", type=int, default=int(_env("POSE_EVERY_N", "1")),
    help="Include pose every N publishes (1=always; higher reuses controller cache)")
  return parser.parse_args(argv)


def main(argv=None):
  logging.basicConfig(
    level=getattr(logging, _env("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

  args = parse_args(argv)

  scene_id = _env("SCENESCAPE_SCENE_ID", default="")
  thing_type = _env("SCENESCAPE_THING_TYPE", "vehicle")
  source_id = _env("SCENESCAPE_SOURCE_ID", required=True)
  category = _env("SCENESCAPE_OBJECT_CATEGORY", thing_type)
  broker = _env("SCENESCAPE_BROKER", "localhost")
  broker_port = int(_env("SCENESCAPE_BROKER_PORT", "1883"))
  mqtt_auth = _env("SCENESCAPE_MQTT_AUTH", required=True)
  root_cert = _env("SCENESCAPE_ROOT_CERT", required=True)

  if args.publish_hz <= 0:
    raise SystemExit("--publish-hz must be > 0")
  if args.pose_every_n < 1:
    raise SystemExit("--pose-every-n must be >= 1")

  logger.info("Connecting to MAVLink: %s", args.connection)
  mav = mavutil.mavlink_connection(args.connection, baud=args.baud)
  mav.wait_heartbeat(timeout=30)
  logger.info("MAVLink heartbeat from system %s component %s",
              mav.target_system, mav.target_component)

  pubsub = PubSub(mqtt_auth, None, root_cert, broker, port=broker_port)
  pubsub.connect()
  pubsub.loopStart()
  # Publisher-centric: topic path is source_id. Optional SCENESCAPE_SCENE_ID is
  # only for operator notes / manual CONTROLLER_EXTERNAL_SOURCE_BINDINGS.
  topic = PubSub.formatTopic(
    PubSub.DATA_EXTERNAL, scene_id=source_id, thing_type=thing_type)
  logger.info(
    "Publishing to MQTT topic %s (publisher id=%s); optional scene hint=%s",
    topic, source_id, scene_id)

  state = MavlinkState()
  interval = 1.0 / args.publish_hz
  next_publish = time.monotonic()
  publish_count = 0

  try:
    while True:
      msg = mav.recv_match(
        type=["GLOBAL_POSITION_INT", "GPS_RAW_INT", "ATTITUDE"],
        blocking=True, timeout=1.0)
      if msg is not None:
        state.update(msg)

      now = time.monotonic()
      if now < next_publish:
        continue
      next_publish = now + interval

      if not state.have_position:
        logger.debug("Waiting for GNSS fix before first publish")
        continue

      include_pose = (publish_count % args.pose_every_n) == 0
      # First message must carry pose; later ones may omit it for cache reuse.
      if publish_count == 0:
        include_pose = True

      payload = build_payload(
        state, source_id, category, args.publish_self, include_pose=include_pose)
      # Skip empty updates that neither refresh pose nor report objects.
      if "pose" not in payload and not payload["objects"]:
        continue

      pubsub.publish(topic, json.dumps(payload))
      publish_count += 1
      if publish_count == 1 or publish_count % max(1, int(args.publish_hz * 5)) == 0:
        logger.info(
          "Published #%s pose=%s objects=%s lla=%s",
          publish_count,
          "yes" if "pose" in payload else "cache",
          len(payload["objects"]),
          payload.get("pose", {}).get("lat_long_alt"))
  except KeyboardInterrupt:
    logger.info("Interrupted; exiting")
  finally:
    try:
      pubsub.loopStop()
    except Exception:
      pass
  return 0


if __name__ == "__main__":
  sys.exit(main())
