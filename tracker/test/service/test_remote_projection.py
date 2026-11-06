#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Service tests for experimental remote projection.

The tracker projects pixel-box detections with a mock projection service (mocks/projection)
over gRPC and feeds the returned measurement and noise covariance to the tracker:
- remote measurements drive the tracks; the tracker is fed centre-of-mass positions and
  publishes the footprint base;
- failed calls keep the local projection, are counted in tracker.remote_projection.failed_calls
  and logged, and the service keeps running;
- the cost of remote projection is measured from tracker.stage.transform_duration and the
  end-to-end MQTT latency, with and without remote projection.
"""

import json
import math
import re
import statistics
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from python_on_whales import DockerClient
from waiting import wait

from utils.docker import get_broker_host, get_container_logs, wait_for_readiness

SCENE_ID = "302cf49a-97ec-402d-a324-c5077b280b7b"
CAMERA_ID = "atag-qcam1"
# Both cameras of the scene (1280 x 720)
CAMERA_IDS = ("atag-qcam1", "atag-qcam2")
CATEGORY = "thing"
BBOX = {"x": 100, "y": 50, "width": 80, "height": 200}
# 50 boxes in a 10 x 5 grid inside the image
GRID_BOXES = tuple({"x": 40 + 120 * (k % 10), "y": 40 + 130 * (k // 10), "width": 40,
                    "height": 120} for k in range(50))
# Mock measurement for BBOX: centre (x / 20, y / 20, height / 2); tracks are at the base, z = 0.
REMOTE_POSITION = (BBOX["x"] / 20.0, BBOX["y"] / 20.0, 0.0)
FAILED_CALLS_METRIC = "tracker.remote_projection.failed_calls"
TRANSFORM_METRIC = "tracker.stage.transform_duration"
# The same sensor-frame centre of mass sent as a 3D detection in two categories of different height.
CENTRE_TRANSLATION = [0.5, 0.2, 3.0]
TRANSLATION_HEIGHTS = {"tall": 1.8, "short": 0.2}


@contextmanager
def tracker_environment(tls_certs, name, remote=True, timeout_ms=50, mock_status="",
                        mock_delay_ms=0):
  """Start broker, collector, tracker and, with `remote`, the mock projection service."""
  service_dir = Path(__file__).parent
  project_name = f"tracker-{name}-{uuid.uuid4().hex[:8]}"
  env_file = tls_certs.temp_dir / f".env-{project_name}"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
      f"TRACKER_LOG_LEVEL=info\n"
      f"TRACKER_MQTT_INSECURE=true\n"
      f"TRACKER_SCENES_SOURCE=file\n"
      f"TRACKER_METRICS_ENABLED=true\n"
      f"TRACKER_METRICS_EXPORT_INTERVAL_S=1\n"
      f"TRACKER_EXPERIMENTAL_REMOTE_PROJECTION={'true' if remote else 'false'}\n"
      f"TRACKER_REMOTE_PROJECTION_HOST=mock-projection\n"
      f"TRACKER_REMOTE_PROJECTION_PORT=50051\n"
      f"TRACKER_REMOTE_PROJECTION_INSECURE=true\n"
      f"TRACKER_REMOTE_PROJECTION_TIMEOUT_MS={timeout_ms}\n"
      f"MOCK_PROJECTION_STATUS={mock_status}\n"
      f"MOCK_PROJECTION_DELAY_MS={mock_delay_ms}\n"
  )
  docker = DockerClient(
      compose_files=[service_dir / "compose.yml"],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
      compose_env_files=[str(env_file)],
      compose_profiles=["projection"] if remote else [],
  )
  try:
    print(f"\nStarting remote projection environment: {project_name}")
    if remote:
      docker.compose.up(services=["mock-projection"], build=True, detach=True, wait=True)
    docker.compose.up(services=["broker", "otel-collector", "tracker"], detach=True, wait=False)
    try:
      wait_for_readiness(docker, timeout=30)
    except Exception:
      print(get_container_logs(docker, "tracker"))
      raise
    yield docker
  finally:
    print(f"\nCleaning up: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)


@contextmanager
def scene_output_client(docker, categories=(CATEGORY,)):
  """MQTT client subscribed to the scene output; yields (client, received) with receive times."""
  host, port = get_broker_host(docker, port=1883)
  received = []
  subscribed = threading.Event()

  def on_message(_client, _userdata, msg):
    received.append((time.monotonic(), json.loads(msg.payload.decode())))

  def on_subscribe(_client, _userdata, _mid, _reason_codes, _properties):
    subscribed.set()

  client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                       client_id=f"test-remote-projection-{uuid.uuid4().hex[:8]}")
  client.on_message = on_message
  client.on_subscribe = on_subscribe
  client.connect(host, port, keepalive=60)
  client.loop_start()
  try:
    client.subscribe([(f"scenescape/data/scene/{SCENE_ID}/{category}", 1)
                      for category in categories])
    assert subscribed.wait(timeout=5), "Scene output subscription was not acknowledged"
    yield client, received
  finally:
    client.loop_stop()
    client.disconnect()


def send_detections(client, count, interval_s, cameras=(CAMERA_ID,), boxes=(BBOX,),
                    other_objects=None):
  """Publish `count` frames from each camera with `boxes`; return {timestamp: send time}.

  The cameras of one frame share its timestamp, which the scene output of the frame carries.
  `other_objects` maps further categories to their detections.
  """
  objects = {CATEGORY: [{"id": k + 1, "bounding_box_px": box} for k, box in enumerate(boxes)],
             **(other_objects or {})}
  sent = {}
  for _ in range(count):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    sent[timestamp] = time.monotonic()
    for camera_id in cameras:
      message = {"id": camera_id, "timestamp": timestamp, "objects": objects}
      client.publish(f"scenescape/data/camera/{camera_id}", json.dumps(message),
                     qos=1).wait_for_publish()
    time.sleep(interval_s)
  return sent


def last_objects(received, category=CATEGORY):
  for _, message in reversed(received):
    objects = [obj for obj in message.get("objects", []) if obj["category"] == category]
    if objects:
      return objects
  return []


def last_track(received, category=CATEGORY):
  objects = last_objects(received, category)
  return objects[0] if objects else None


def latencies_ms(sent, received):
  """End-to-end latency of each frame whose output carries its timestamp."""
  latencies = {}
  for receive_time, message in received:
    timestamp = message.get("timestamp")
    if timestamp in sent and timestamp not in latencies:
      latencies[timestamp] = (receive_time - sent[timestamp]) * 1000.0
  return list(latencies.values())


def histogram_mean_ms(collector_logs, metric_name):
  """Mean of the last exported cumulative histogram `metric_name` (count, mean ms)."""
  start = collector_logs.rfind(f"-> Name: {metric_name}")
  if start < 0:
    return 0, math.nan
  block = collector_logs[start:]
  count = re.search(r"Count: (\d+)", block)
  total = re.search(r"Sum: ([0-9.eE+-]+)", block)
  if not count or not total or int(count.group(1)) == 0:
    return 0, math.nan
  return int(count.group(1)), float(total.group(1)) / int(count.group(1))


def distance(a, b):
  return math.dist(a[:2], b[:2])


def test_remote_projection_measurements_drive_tracks(tls_certs):
  """Remote measurements become track positions; the request identifies scene, camera, mode.

  The tracker is fed centre-of-mass positions and publishes the footprint base: the mock's centre
  z = HEIGHT_M / 2 is published at z = 0, and a 3D detection at z = centre - height / 2.
  """
  other_objects = {category: [{"id": 1, "translation": CENTRE_TRANSLATION,
                               "size": [0.5, 0.5, height]}]
                   for category, height in TRANSLATION_HEIGHTS.items()}
  categories = (CATEGORY, *TRANSLATION_HEIGHTS)
  with tracker_environment(tls_certs, "remote-ok") as docker:
    with scene_output_client(docker, categories) as (client, received):
      send_detections(client, count=30, interval_s=0.067, other_objects=other_objects)
      wait(lambda: all(last_track(received, category) for category in categories),
           timeout_seconds=10, sleep_seconds=0.1)

    track = last_track(received)
    for actual, expected in zip(track["translation"], REMOTE_POSITION):
      assert actual == pytest.approx(expected, abs=0.05), track["translation"]
    tall, short = (last_track(received, category)["translation"] for category in TRANSLATION_HEIGHTS)
    assert distance(tall, short) < 0.01, (tall, short)
    assert tall[2] - short[2] == pytest.approx(
        -(TRANSLATION_HEIGHTS["tall"] - TRANSLATION_HEIGHTS["short"]) / 2, abs=0.01), (tall, short)

    mock_logs = get_container_logs(docker, "mock-projection")
    assert (f"scene={SCENE_ID} camera={CAMERA_ID} mode=CONDITIONING_MODE_AUTO detections=1 "
            f"categories={CATEGORY}") in mock_logs
    tracker_logs = get_container_logs(docker, "tracker")
    assert "Experimental remote projection enabled: mock-projection:50051" in tracker_logs
    assert "Remote projection failed" not in tracker_logs


@pytest.mark.parametrize("failure", [
    {"mock_status": "UNAVAILABLE", "reason": "UNAVAILABLE"},
    {"mock_delay_ms": 300, "timeout_ms": 30, "reason": "DEADLINE_EXCEEDED"},
], ids=["unavailable", "deadline"])
def test_remote_projection_failure_keeps_local_projection(tls_certs, failure):
  """Failed calls keep the local projection, are counted and logged; the tracker keeps running.

  The local projection is still fed at its centre of mass and published at its base (z = 0).
  """
  reason = failure["reason"]
  options = {key: value for key, value in failure.items() if key != "reason"}
  with tracker_environment(tls_certs, "remote-fail", **options) as docker:
    with scene_output_client(docker) as (client, received):
      send_detections(client, count=30, interval_s=0.067)
      wait(lambda: last_track(received) is not None, timeout_seconds=10, sleep_seconds=0.1)

    track = last_track(received)
    assert distance(track["translation"], REMOTE_POSITION) > 0.5, \
        f"Expected the local projection, got the remote position {track['translation']}"
    assert abs(track["translation"][2]) < 0.01, track["translation"]

    def failure_exported():
      logs = get_container_logs(docker, "otel-collector")
      return FAILED_CALLS_METRIC in logs and f"Str({reason})" in logs

    wait(failure_exported, timeout_seconds=15, sleep_seconds=0.5)
    tracker_logs = get_container_logs(docker, "tracker")
    assert f"Remote projection failed for scope {SCENE_ID}/{CATEGORY}, camera '{CAMERA_ID}' " \
        f"({reason})" in tracker_logs
    assert docker.compose.ps(services=["tracker"])[0].state.running


WORKLOADS = {
    "1x1": (CAMERA_IDS[:1], (BBOX,)),
    "2x50": (CAMERA_IDS, GRID_BOXES),
}


def remote_fraction(objects, boxes):
  """Fraction of tracks at a mock remote position (x / 20, y / 20) of one of `boxes`."""
  positions = [(box["x"] / 20.0, box["y"] / 20.0) for box in boxes]
  near = sum(1 for obj in objects
             if min(distance(obj["translation"], position) for position in positions) < 0.05)
  return near / len(objects) if objects else 0.0


@pytest.mark.parametrize("workload", list(WORKLOADS))
def test_remote_projection_latency_impact(tls_certs, workload):
  """Measure the transform stage and end-to-end latency with and without remote projection.

  Workloads: one camera with one detection per frame, and two cameras with 50 detections each.
  """
  cameras, boxes = WORKLOADS[workload]
  configurations = [
      ("local projection", {"remote": False}),
      ("remote, mock 0 ms", {"remote": True, "timeout_ms": 100}),
      ("remote, mock 20 ms", {"remote": True, "timeout_ms": 100, "mock_delay_ms": 20}),
  ]
  frames = 100
  # 77 ms is not a multiple of the 66.7 ms chunk interval, so frames arrive at all chunk phases.
  interval_s = 0.077
  results = {}
  for label, options in configurations:
    with tracker_environment(tls_certs, "remote-latency", **options) as docker:
      with scene_output_client(docker) as (client, received):
        sent = send_detections(client, count=frames, interval_s=interval_s, cameras=cameras,
                               boxes=boxes)
        time.sleep(1.0)
      latencies = latencies_ms(sent, received)
      wait(lambda: TRANSFORM_METRIC in get_container_logs(docker, "otel-collector"),
           timeout_seconds=15, sleep_seconds=0.5)
      time.sleep(2.0)  # let the final cumulative export include every frame
      count, transform_mean = histogram_mean_ms(get_container_logs(docker, "otel-collector"),
                                                TRANSFORM_METRIC)
      results[label] = {
          "objects": last_objects(received),
          "frames_out": len(latencies),
          "transform_count": count,
          "transform_mean_ms": transform_mean,
          "e2e_median_ms": statistics.median(latencies) if latencies else math.nan,
          "e2e_p95_ms": (statistics.quantiles(latencies, n=20)[-1]
                         if len(latencies) >= 20 else math.nan),
          "remote_failed": "Remote projection failed" in get_container_logs(docker, "tracker"),
      }

  print(f"\nRemote projection impact ({len(cameras)} camera(s) x {len(boxes)} detection(s) per "
        f"frame, {frames} frames at {1 / interval_s:.1f} fps):")
  print(f"{'configuration':<22}{'frames out':>11}{'tracks':>8}{'transform mean ms':>19}"
        f"{'e2e median ms':>15}{'e2e p95 ms':>12}")
  for label, result in results.items():
    print(f"{label:<22}{result['frames_out']:>11}{len(result['objects']):>8}"
          f"{result['transform_mean_ms']:>19.2f}{result['e2e_median_ms']:>15.1f}"
          f"{result['e2e_p95_ms']:>12.1f}")

  for label, result in results.items():
    assert result["objects"], f"{label}: no tracks"
    assert result["frames_out"] >= frames * 0.8, f"{label}: too few frames out"
    assert result["transform_count"] > 0, f"{label}: no transform stage samples"
  local = results["local projection"]
  remote = results["remote, mock 0 ms"]
  delayed = results["remote, mock 20 ms"]
  assert remote_fraction(local["objects"], boxes) < 0.5, "local tracks are not at mock positions"
  for result in (remote, delayed):
    assert remote_fraction(result["objects"], boxes) == 1.0, "tracks follow the mock measurements"
    assert len(result["objects"]) >= 0.9 * len(boxes), "the cameras' detections fuse into tracks"
    assert not result["remote_failed"], "no call failed or timed out"
  assert remote["transform_mean_ms"] < 100.0, "the call deadline bounds the transform stage"
  assert 20.0 <= delayed["transform_mean_ms"] < 100.0, \
      "the projection call is on the transform stage path"
