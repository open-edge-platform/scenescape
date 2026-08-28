#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Publish clustered radar tracks on scenescape/data/radar/{radar_id}.

Reads live (N, 5) frames from a .npy/.npz replay directory (one file per frame)
or from stdin as JSON arrays. Always publishes frames, including empty objects.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

from radar_frame import as_frame
from radar_perception import RadarPerception

try:
  from scene_common.mqtt import PubSub
  from scene_common.timestamp import get_iso_time
except ImportError:
  PubSub = None
  get_iso_time = None

logger = logging.getLogger("radar_publisher")


def _env(name, default=None, required=False):
  value = os.environ.get(name, default)
  if required and (value is None or value == ""):
    raise SystemExit(f"Missing required environment variable: {name}")
  return value


def load_frame_files(directory: Path) -> list[Path]:
  files = sorted(
    list(directory.glob("*.npy")) + list(directory.glob("*.npz"))
  )
  if not files:
    raise SystemExit(f"No .npy/.npz frames in {directory}")
  return files


def read_frame(path: Path) -> np.ndarray:
  if path.suffix == ".npy":
    return as_frame(np.load(path))
  return as_frame(np.loadtxt(path, delimiter=",", ndmin=2))


def build_message(radar_id: str, objects: dict, rate: float) -> dict:
  ts = get_iso_time() if get_iso_time else time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
  return {
    "id": radar_id,
    "timestamp": ts,
    "rate": float(rate),
    "objects": objects,
  }


def connect_pubsub(broker, port, auth, rootcert):
  if PubSub is None:
    raise SystemExit("scene_common is required to publish MQTT")
  client = PubSub(auth, None, rootcert, broker, port=int(port))
  client.connect()
  client.loopStart()
  return client


def publish_loop(args):
  perception = RadarPerception(
    cluster_distance_m=args.cluster_distance,
    track_distance_m=args.track_distance,
    category=args.category,
  )
  auth = None
  if args.user or args.password:
    auth = f"{args.user}:{args.password}"
  client = connect_pubsub(args.broker, args.port, auth, args.rootcert)
  topic = PubSub.formatTopic(PubSub.DATA_RADAR, radar_id=args.radar_id)
  logger.info("Publishing to %s at %.2f Hz", topic, args.rate)

  if args.frames_dir:
    files = load_frame_files(Path(args.frames_dir))
    idx = 0
    while True:
      frame = read_frame(files[idx % len(files)])
      objects = perception.process(frame)
      payload = build_message(args.radar_id, objects, args.rate)
      client.publish(topic, json.dumps(payload))
      idx += 1
      if not args.loop and idx >= len(files):
        break
      time.sleep(1.0 / args.rate)
  else:
    for line in sys.stdin:
      line = line.strip()
      if not line:
        objects = perception.process(np.zeros((0, 5)))
      else:
        objects = perception.process(json.loads(line))
      payload = build_message(args.radar_id, objects, args.rate)
      client.publish(topic, json.dumps(payload))
  return


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--radar-id", default=_env("RADAR_SENSOR_ID", "radar1"))
  parser.add_argument("--frames-dir", default=_env("RADAR_FRAMES_DIR"))
  parser.add_argument("--broker", default=_env("MQTT_HOST", "localhost"))
  parser.add_argument("--port", type=int, default=int(_env("MQTT_PORT", "1883")))
  parser.add_argument("--user", default=_env("MQTT_USER", ""))
  parser.add_argument("--password", default=_env("MQTT_PASS", ""))
  parser.add_argument(
    "--rootcert",
    default=_env("MQTT_ROOTCERT", "/run/secrets/certs/scenescape-ca.pem"),
  )
  parser.add_argument("--rate", type=float, default=float(_env("RADAR_FRAME_RATE", "10")))
  parser.add_argument("--loop", action="store_true", default=_env("RADAR_LOOP", "true").lower() not in ("0", "false", "no"))
  parser.add_argument("--cluster-distance", type=float, default=2.5)
  parser.add_argument("--track-distance", type=float, default=5.0)
  parser.add_argument("--category", default=_env("RADAR_CATEGORY", "vehicle"))
  return parser.parse_args(argv)


def main(argv=None):
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  args = parse_args(argv)
  if not args.frames_dir and sys.stdin.isatty():
    raise SystemExit("Provide --frames-dir or pipe JSON frames on stdin")
  publish_loop(args)


if __name__ == "__main__":
  main()
