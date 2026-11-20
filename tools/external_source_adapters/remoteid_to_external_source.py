# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Drone Remote ID → Scenescape external_source MQTT adapter.

Listens for drones broadcasting ASTM F3411 / EN 4709-002 Remote ID over Wi-Fi
(beacon and NAN) on a monitor-mode interface, or replays a pcap capture, and
publishes every aircraft heard as its own external source on
scenescape/external/{publisher_id}/{thing_type}. publisher_id is
SCENESCAPE_SOURCE_PREFIX plus the transmitter's MAC address.

Decoding and the per-transmitter trust verdict (authenticated, plausible,
suspicious, spoofed) come from the `remoteid` package. The verdict, its score
and reasons, and the broadcast UAS ID travel in the object's semantic metadata.

Contract fields and examples:
  docs/user-guide/microservices/controller/data_formats.md
  (External Source Input Message Format)

How-to:
  docs/user-guide/how-to-guides/publish-external-source-adapter.md
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import socket
import struct
import sys
import time

import remoteid

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

logger = logging.getLogger(__name__)

IDENTITY_QUAT = [0.0, 0.0, 0.0, 1.0]
# Scene-data schema requires a numeric [L,W,H]; same default as the MAVLink adapter.
DEFAULT_VEHICLE_SIZE = [0.6, 0.6, 0.3]
MODEL_NAME = "remoteid"
ETH_P_ALL = 0x0003
MAX_TRACKED_SOURCES = 4096

# Classic pcap magic -> (struct byte order, seconds per timestamp fraction unit)
PCAP_MAGIC = {
  b"\xd4\xc3\xb2\xa1": ("<", 1e-6),
  b"\xa1\xb2\xc3\xd4": (">", 1e-6),
  b"\x4d\x3c\xb2\xa1": ("<", 1e-9),
  b"\xa1\xb2\x3c\x4d": (">", 1e-9),
}
# pcap link type -> remoteid transport
PCAP_LINKTYPES = {105: "wifi_frame", 127: "radiotap"}


def _env(name, default=None, required=False):
  """Read an environment variable, optionally failing when it is unset."""
  value = os.environ.get(name, default)
  if required and (value is None or value == ""):
    raise SystemExit(f"Missing required environment variable: {name}")
  return value


def _parse_size_env(name, default):
  """Parse an L,W,H size in metres from an environment variable."""
  raw = _env(name, default="")
  if not raw:
    return list(default)
  parts = [float(x.strip()) for x in raw.split(",")]
  if len(parts) != 3 or not all(math.isfinite(v) and v > 0 for v in parts):
    raise SystemExit(f"{name} must be three comma-separated numbers > 0 (L,W,H metres)")
  return parts


def _wait_mqtt_connected(pubsub, timeout_s=15):
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    if pubsub.isConnected():
      return True
    time.sleep(0.1)
  return False


def source_id_for(prefix, address):
  """Persistent publisher id from the transmitter MAC (topic-safe characters only)."""
  return prefix + re.sub(r"[^0-9A-Za-z]", "", str(address)).lower()


def build_payload(verdict, source_id, category, object_size=None):
  """Build an external_source dict for one Remote ID transmitter.

  Returns None until the aircraft has broadcast a position with geodetic
  (WGS84 ellipsoid) altitude, which is what the wgs84 pose requires.
  """
  if verdict.latitude is None or verdict.longitude is None or verdict.altitude_m is None:
    return None
  metadata = {
    "remote_id_trust": {
      "label": verdict.verdict,
      "confidence": float(verdict.score),
      "model_name": MODEL_NAME,
    },
    "remote_id_reasons": {"label": list(verdict.reasons), "model_name": MODEL_NAME},
  }
  if verdict.uas_id:
    metadata["remote_id_uas_id"] = {"label": verdict.uas_id, "model_name": MODEL_NAME}
  return {
    "timestamp": get_iso_time(),
    "source_id": source_id,
    "objects": [{
      "id": source_id,
      "category": category,
      "translation": [0.0, 0.0, 0.0],
      "rotation": list(IDENTITY_QUAT),
      "size": list(object_size or DEFAULT_VEHICLE_SIZE),
      "metadata": metadata,
    }],
    "pose": {
      "reference_frame": "wgs84",
      "lat_long_alt": [verdict.latitude, verdict.longitude, verdict.altitude_m],
      "rotation": list(IDENTITY_QUAT),
      "provider": "remote_id",
    },
  }


class RemoteIdPublisher:
  """Feeds frames to a remoteid.Tracker and rate-limits payloads per transmitter."""

  def __init__(self, tracker, prefix, category, object_size, interval_ms):
    self.tracker = tracker
    self.prefix = prefix
    self.category = category
    self.object_size = object_size
    self.interval_ms = interval_ms
    self.last_publish = {}

  def ingest(self, now_ms, transport, frame):
    """Return (source_id, payload) when this frame makes a publish due, else None."""
    try:
      verdict = self.tracker.ingest(frame, transport, now_ms=now_ms)
    except ValueError:
      return None  # not Remote ID: most beacons are ordinary access points
    source_id = source_id_for(self.prefix, verdict.address)
    last = self.last_publish.get(source_id)
    if last is not None and now_ms - last < self.interval_ms:
      return None
    payload = build_payload(verdict, source_id, self.category, self.object_size)
    if payload is None:
      return None
    if len(self.last_publish) >= MAX_TRACKED_SOURCES:
      self.last_publish = {k: v for k, v in self.last_publish.items()
                           if now_ms - v < 60_000}
    self.last_publish[source_id] = now_ms
    return source_id, payload


def read_pcap(stream):
  """Yield (time_ms, transport, frame) from a classic pcap of 802.11 frames."""
  header = stream.read(24)
  if len(header) < 24 or header[:4] not in PCAP_MAGIC:
    raise SystemExit("Not a classic pcap file (convert pcapng with: editcap -F pcap in out)")
  endian, unit = PCAP_MAGIC[header[:4]]
  linktype = struct.unpack(endian + "I", header[20:24])[0] & 0x0FFFFFFF
  transport = PCAP_LINKTYPES.get(linktype)
  if transport is None:
    raise SystemExit(
      f"Unsupported pcap link type {linktype}; expected 802.11 (105) or radiotap (127)")
  while True:
    record = stream.read(16)
    if len(record) < 16:
      return
    sec, frac, caplen, _ = struct.unpack(endian + "IIII", record)
    frame = stream.read(caplen)
    if len(frame) < caplen:
      return
    yield int(sec * 1000 + frac * unit * 1000), transport, frame


def read_pcap_file(path):
  """Yield (time_ms, transport, frame) from a classic pcap file on disk."""
  with open(path, "rb") as stream:
    yield from read_pcap(stream)


def read_interface(name):
  """Yield (time_ms, transport, frame) from a Linux monitor-mode interface."""
  if not hasattr(socket, "AF_PACKET"):
    raise SystemExit("--interface needs Linux (AF_PACKET); use --pcap elsewhere")
  sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(ETH_P_ALL))
  sock.bind((name, 0))
  while True:
    frame = sock.recv(65535)
    yield int(time.monotonic() * 1000), "wifi_frame", frame


def paced(frames):
  """Replay capture frames at their recorded spacing."""
  start = first_ms = None
  for time_ms, transport, frame in frames:
    if start is None:
      start, first_ms = time.monotonic(), time_ms
    delay = start + (time_ms - first_ms) / 1000.0 - time.monotonic()
    if delay > 0:
      time.sleep(delay)
    yield time_ms, transport, frame


def parse_args(argv=None):
  parser = argparse.ArgumentParser(
    description="Publish Wi-Fi Remote ID drones as Scenescape external_source MQTT messages.")
  source = parser.add_mutually_exclusive_group()
  source.add_argument(
    "--interface", default=_env("REMOTEID_INTERFACE", ""),
    help="Linux Wi-Fi interface in monitor mode (or REMOTEID_INTERFACE)")
  source.add_argument(
    "--pcap", default=_env("REMOTEID_PCAP", ""),
    help="Replay a classic pcap (802.11 or radiotap) at recorded speed (or REMOTEID_PCAP)")
  parser.add_argument(
    "--publish-hz", type=float, default=float(_env("PUBLISH_HZ", "1")),
    help="Maximum MQTT publish rate per aircraft in Hz")
  parser.add_argument(
    "--system-clock", action="store_true",
    default=_env("REMOTEID_SYSTEM_CLOCK", "false").lower() in ("1", "true", "yes"),
    help="Use the UTC clock for timestamp and DRIP checks (NTP/GNSS-synced hosts only)")
  args = parser.parse_args(argv)
  if bool(args.interface) == bool(args.pcap):
    parser.error("give exactly one of --interface or --pcap")
  if args.publish_hz <= 0:
    parser.error("--publish-hz must be > 0")
  return args


def main(argv=None):
  logging.basicConfig(
    level=getattr(logging, _env("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

  args = parse_args(argv)

  prefix = _env("SCENESCAPE_SOURCE_PREFIX", "rid-")
  thing_type = _env("SCENESCAPE_THING_TYPE", "vehicle")
  category = _env("SCENESCAPE_OBJECT_CATEGORY", thing_type)
  object_size = _parse_size_env("SCENESCAPE_OBJECT_SIZE", DEFAULT_VEHICLE_SIZE)
  broker = _env("SCENESCAPE_BROKER", "localhost")
  broker_port = int(_env("SCENESCAPE_BROKER_PORT", "1883"))
  mqtt_auth = _env("SCENESCAPE_MQTT_AUTH", required=True)
  root_cert = _env("SCENESCAPE_ROOT_CERT", required=True)
  mqtt_insecure = _env("SCENESCAPE_MQTT_INSECURE", "").lower() in ("1", "true", "yes")

  pubsub = PubSub(mqtt_auth, None, root_cert, broker, port=broker_port,
                  insecure=mqtt_insecure)
  pubsub.connect()
  pubsub.loopStart()
  if not _wait_mqtt_connected(pubsub, timeout_s=15):
    raise SystemExit(f"MQTT broker {broker}:{broker_port} did not connect")

  publisher = RemoteIdPublisher(
    remoteid.Tracker(use_system_clock=args.system_clock), prefix, category,
    object_size, interval_ms=1000.0 / args.publish_hz)

  if args.pcap:
    frames = paced(read_pcap_file(args.pcap))
    logger.info("Replaying %s", args.pcap)
  else:
    frames = read_interface(args.interface)
    logger.info("Listening on %s", args.interface)

  last_trust = {}
  try:
    for time_ms, transport, frame in frames:
      due = publisher.ingest(time_ms, transport, frame)
      if due is None:
        continue
      source_id, payload = due
      topic = PubSub.formatTopic(
        PubSub.DATA_EXTERNAL, scene_id=source_id, thing_type=thing_type)
      pubsub.publish(topic, json.dumps(payload))
      trust = payload["objects"][0]["metadata"]["remote_id_trust"]["label"]
      if source_id not in last_trust:
        logger.info("New aircraft %s (%s) on %s", source_id, trust, topic)
      elif trust != last_trust[source_id] and trust in ("suspicious", "spoofed"):
        logger.warning("Aircraft %s is now %s: %s", source_id, trust,
                       payload["objects"][0]["metadata"]["remote_id_reasons"]["label"])
      if len(last_trust) >= MAX_TRACKED_SOURCES:
        last_trust.clear()
      last_trust[source_id] = trust
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
