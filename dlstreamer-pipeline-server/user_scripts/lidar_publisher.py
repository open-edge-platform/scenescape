#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Runs the LiDAR GStreamer pipeline and republishes each JSON frame to MQTT.
gvametapublish method=file writes one JSON object per line to stdout.
This script reads those lines and publishes them to the broker with TLS.
"""

import json
import os
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt

BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC   = "scenescape/data/lidar/lidar1"
ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"
FIFO    = "/tmp/lidar_detections.fifo"

PIPELINE = (
  "gst-launch-1.0 "
  "multifilesrc "
    "location=/home/pipeline-server/videos/velodyne_bin/%06d.bin "
    "start-index=10699 loop=true caps=application/octet-stream "
  "! g3dlidarparse stride=1 frame-rate=10 "
  "! g3dinference "
    "config=/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json "
    "device=CPU score-threshold=0.3 "
  "! gvametaconvert add-tensor-data=true format=json "
  f"! gvametapublish method=file file-format=json-lines file-path={FIFO} "
  "! fakesink"
)


def connect_mqtt():
  client = mqtt.Client(client_id="lidar-stream-publisher")
  if os.path.exists(ROOT_CA):
    client.tls_set(ca_certs=ROOT_CA)
  for attempt in range(10):
    try:
      client.connect(BROKER, PORT, keepalive=60)
      client.loop_start()
      print(f"[lidar-publisher] Connected to {BROKER}:{PORT}", flush=True)
      return client
    except Exception as e:
      print(f"[lidar-publisher] Connect attempt {attempt + 1} failed: {e}", flush=True)
      time.sleep(2)
  raise RuntimeError("Could not connect to MQTT broker")


def main():
  # Create FIFO for unbuffered communication with gst-launch-1.0
  if os.path.exists(FIFO):
    os.remove(FIFO)
  os.mkfifo(FIFO)

  client = connect_mqtt()

  proc = subprocess.Popen(
    PIPELINE,
    shell=True,
    stderr=sys.stderr,
  )
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid}), reading from {FIFO}", flush=True)

  published = 0
  with open(FIFO, "r") as fifo:
    for line in fifo:
      line = line.strip()
      if not line:
        continue
      try:
        json.loads(line)  # validate
        client.publish(TOPIC, line, qos=0)
        published += 1
        if published % 100 == 0:
          print(f"[lidar-publisher] Published {published} frames", flush=True)
      except json.JSONDecodeError:
        pass

  proc.wait()
  client.loop_stop()
  client.disconnect()


if __name__ == "__main__":
  main()
