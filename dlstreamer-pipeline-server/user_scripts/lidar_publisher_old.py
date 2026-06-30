#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Runs the LiDAR GStreamer inference pipeline and republishes each frame to MQTT
in the SceneScape camera detection format so the controller can track objects.

Fixes applied:
  [F01] FIFO deadlock      — open FIFO in background thread before pipeline starts
  [F02] Silent failure     — poll proc.returncode inside read loop
  [F03] STOP_INDEX         — use None sentinel; strip() before int()
  [F04] Missing bbox       — guard all bbox key accesses with .get()
  [F05] Shell inject       — shlex.quote all env-var paths
  [F06] Publish error      — check MQTTMessageInfo.rc; reconnect on failure
  [F07] FIFO cleanup       — atexit handler removes FIFO and terminates pipeline
  [F08] FPS init           — seed fps from FRAME_RATE instead of 0.0
  [F09] Client ID          — append uuid4 suffix to avoid broker session clash
  [F10] Debug object       — correlate RAW log by label, not first-bbox-found
  [F11] Quaternion         — enforce qw >= 0 canonical form
  [F12] Z calibration      — derive mount height from Car detections (median)
  [F13] Theta smooth       — per-object EMA with pi-ambiguity resolution
  [F14] Timing log         — per-frame parse/convert/publish timing every 100 frames
  [F15] Pipeline poll      — check proc exit code; raise on non-zero
  [F16] Z smooth           — per-object EMA on bbox centre z to reduce height jitter
  [F17] Z smoother seed    — warm-start from per-label median z instead of first
                             raw observation to avoid outlier anchor
"""

import atexit
import json
import math
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from statistics import median

import paho.mqtt.client as mqtt

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"

# ── LiDAR pipeline ────────────────────────────────────────────────────────────
SENSOR_ID       = os.environ.get("LIDAR_SENSOR_ID", "lidar1")
DATA_PATH       = os.environ.get(
    "LIDAR_DATA_PATH",
    "/home/pipeline-server/videos/velodyne_bin/%06d.bin",
)
START_INDEX     = int(os.environ.get("LIDAR_START_INDEX", "10699"))

_STOP_RAW  = os.environ.get("LIDAR_STOP_INDEX")
STOP_INDEX = int(_STOP_RAW.strip()) if _STOP_RAW and _STOP_RAW.strip() else None

LOOP            = os.environ.get("LIDAR_LOOP", "true").lower() not in ("0", "false", "no")
FRAME_RATE      = int(os.environ.get("LIDAR_FRAME_RATE", "10"))
DEVICE          = os.environ.get("LIDAR_DEVICE", "CPU")
SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.3"))
MODEL_CONFIG    = os.environ.get(
    "LIDAR_MODEL_CONFIG",
    "/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json",
)

# ── Calibration constants ─────────────────────────────────────────────────────
_Z_OFFSET_FALLBACK = 2.0
_CAR_H_MIN         = 1.3
_CAR_H_MAX         = 1.8
_CALIB_MIN_SAMPLES = 10
_CALIB_WINDOW      = 200

# ── Smoothing alphas (lower = smoother, more lag) ─────────────────────────────
_THETA_ALPHA = 0.30
_Z_ALPHA     = 0.25

# ── [F17] Per-label warm-start z priors (metres, bbox centre in LiDAR frame) ──
# Derived from log analysis:
#   Car        bottom_z ≈ -2.30  h ≈ 1.50  → centre_z ≈ -1.55
#   Pedestrian bottom_z ≈ -2.52  h ≈ 1.76  → centre_z ≈ -1.64
#   Cyclist    bottom_z ≈ -2.52  h ≈ 1.82  → centre_z ≈ -1.61
# These are used only until the per-object smoother has seen enough frames
# to converge on its own.  They prevent a single outlier first observation
# from anchoring the EMA at a wrong level.
_Z_PRIOR: dict[str, float] = {
    "Car":        -1.55,
    "Pedestrian": -1.64,
    "Cyclist":    -1.61,
    "object":     -1.60,   # generic fallback
}

# ── Misc ──────────────────────────────────────────────────────────────────────
CAMERA_TOPIC = f"scenescape/data/camera/{SENSOR_ID}"
FIFO         = "/tmp/lidar_detections.fifo"
KITTI_LABELS = {0: "Pedestrian", 1: "Cyclist", 2: "Car"}


# ═══════════════════════════════════════════════════════════════════════════════
# [F12] Dynamic mount-height calibration from Car detections
# ═══════════════════════════════════════════════════════════════════════════════

class MountHeightCalibrator:
    """
    Estimates LiDAR mount height above ground using Car detections.

    PointPillars reports bbox centre z.  The bottom of the car is:
        bottom_z = bbox_z - h/2
    Because the LiDAR is mounted above the ground plane, bottom_z is negative.
    Mount height = -bottom_z (positive metres).

    Rolling window median resists outliers.
    """

    def __init__(
        self,
        fallback: float  = _Z_OFFSET_FALLBACK,
        h_min: float     = _CAR_H_MIN,
        h_max: float     = _CAR_H_MAX,
        min_samples: int = _CALIB_MIN_SAMPLES,
        window: int      = _CALIB_WINDOW,
    ):
        self._fallback    = fallback
        self._h_min       = h_min
        self._h_max       = h_max
        self._min_samples = min_samples
        self._samples: deque[float] = deque(maxlen=window)

    def update(self, label: str, bbox: dict) -> None:
        if label != "Car":
            return
        h = bbox.get("h", 0.0)
        if not (self._h_min < h < self._h_max):
            return
        z            = bbox.get("z", 0.0)
        bottom_z     = z - h / 2.0
        mount_height = -bottom_z
        self._samples.append(mount_height)

    @property
    def mount_height(self) -> float:
        if len(self._samples) < self._min_samples:
            return self._fallback
        return median(self._samples)

    @property
    def sample_count(self) -> int:
        return len(self._samples)


# ═══════════════════════════════════════════════════════════════════════════════
# [F13] Per-object theta smoother
# ═══════════════════════════════════════════════════════════════════════════════

class ThetaSmoother:
    """
    EMA on PointPillars heading angle with pi-ambiguity resolution.

    PointPillars predicts heading modulo pi (front/back symmetric), so the raw
    theta can flip by ±pi between frames for the same physical object.  Before
    blending we pick whichever of {theta, theta+pi, theta-pi} is closest to
    the previous smoothed value.
    """

    def __init__(self, alpha: float = _THETA_ALPHA):
        self._alpha  = alpha
        self._state: dict[str, float] = {}

    @staticmethod
    def _resolve_ambiguity(theta: float, prev: float) -> float:
        candidates = [theta, theta + math.pi, theta - math.pi]
        return min(candidates, key=lambda t: abs(t - prev))

    def smooth(self, key: str, theta: float) -> float:
        if key not in self._state:
            self._state[key] = theta
            return theta
        prev     = self._state[key]
        resolved = self._resolve_ambiguity(theta, prev)
        smoothed = self._alpha * resolved + (1.0 - self._alpha) * prev
        self._state[key] = smoothed
        return smoothed


# ═══════════════════════════════════════════════════════════════════════════════
# [F16 + F17] Per-object z smoother with warm-start prior
# ═══════════════════════════════════════════════════════════════════════════════

class ZSmoother:
    """
    EMA on bbox centre z to suppress PointPillars height jitter.

    [F17] Warm-start fix
    ───────────────────
    The previous version seeded the EMA from the first raw observation.
    Log analysis showed that first observation is often an outlier
    (e.g. z=-2.53 instead of the converged -2.62), which anchors the
    smoother at a wrong level for several frames before it recovers.

    Fix: seed from a per-label prior derived from log statistics instead
    of from the first raw value.  The prior is only used for the very
    first observation of each grid key; subsequent frames use the EMA
    as normal.

    Prior derivation (from logs, mount_h ≈ 2.52m):
      Car:        median z_pp ≈ -1.55m
      Pedestrian: median z_pp ≈ -1.64m
      Cyclist:    median z_pp ≈ -1.61m
    """

    def __init__(
        self,
        alpha: float             = _Z_ALPHA,
        priors: dict[str, float] = _Z_PRIOR,
    ):
        self._alpha  = alpha
        self._priors = priors
        self._state: dict[str, float] = {}

    def smooth(self, key: str, z: float, label: str = "object") -> float:
        """
        Return smoothed z for *key*.

        On first call the EMA is initialised from the per-label prior
        (not from *z*), then immediately blended with *z* so the output
        is already close to the true value rather than jumping from the
        prior to the observation over many frames.
        """
        if key not in self._state:
            prior            = self._priors.get(label, self._priors["object"])
            # Blend prior with first observation so we start near the truth
            # rather than sitting at the prior for alpha/(1-alpha) frames.
            self._state[key] = self._alpha * z + (1.0 - self._alpha) * prior
            return self._state[key]

        smoothed         = self._alpha * z + (1.0 - self._alpha) * self._state[key]
        self._state[key] = smoothed
        return smoothed


# ═══════════════════════════════════════════════════════════════════════════════
# GStreamer pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pipeline() -> str:
    location  = shlex.quote(DATA_PATH)
    config    = shlex.quote(MODEL_CONFIG)
    fifo_path = shlex.quote(FIFO)

    parts = [
        "gst-launch-1.0",
        f"multifilesrc location={location}",
        f"start-index={START_INDEX}",
    ]
    if STOP_INDEX is not None:
        parts.append(f"stop-index={STOP_INDEX}")
    if LOOP:
        parts.append("loop=true")
    parts += [
        "caps=application/octet-stream",
        f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE}",
        "! g3dinference",
        f"config={config}",
        f"device={DEVICE}",
        f"score-threshold={SCORE_THRESHOLD}",
        "! gvametaconvert add-tensor-data=true format=json",
        f"! gvametapublish method=file file-format=json-lines file-path={fifo_path}",
        "! fakesink",
    ]
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Coordinate conversion
# ═══════════════════════════════════════════════════════════════════════════════

def yaw_to_quaternion(theta: float) -> list[float]:
    """
    Convert PointPillars yaw to SceneScape quaternion [qx, qy, qz, qw].

    scene_heading = -(theta + pi)

    [F11] Enforce canonical form qw >= 0.
    """
    scene_heading = -(theta + math.pi)
    half          = scene_heading / 2.0
    qz            = math.sin(half)
    qw            = math.cos(half)

    if qw < 0.0:
        qz, qw = -qz, -qw

    EPS = 1e-6
    qz  = max(-1.0 + EPS, min(1.0 - EPS, qz))
    qw  = max(-1.0 + EPS, min(1.0 - EPS, qw))
    return [0.0, 0.0, qz, qw]


def convert_frame(
    raw: dict,
    calibrator: MountHeightCalibrator,
    theta_smoother: ThetaSmoother,
    z_smoother: ZSmoother,
    frame_id: int,
) -> dict[str, list]:
    """
    Convert gvametaconvert JSON-lines frame to SceneScape camera detection format.
    """
    objects: dict[str, list] = {}

    for i, obj in enumerate(raw.get("objects", [])):
        bbox = obj.get("bbox_3d")
        if not isinstance(bbox, dict):
            continue

        try:
            label = (
                obj.get("label")
                or KITTI_LABELS.get(obj.get("label_id", -1), "object")
            )

            calibrator.update(label, bbox)
            mount_height = calibrator.mount_height

            x     = bbox.get("x", 0.0)
            y     = bbox.get("y", 0.0)
            z_raw = bbox.get("z", 0.0)
            w     = bbox.get("w", 0.0)
            l     = bbox.get("l", 0.0)
            h     = bbox.get("h", 0.0)
            theta = bbox.get("theta", 0.0)

            # Shared spatial grid key for both smoothers
            grid_key = f"{label}_{round(x):d}_{round(y):d}"

            # [F13] Smooth heading
            theta_s = theta_smoother.smooth(grid_key, theta)

            # [F16 + F17] Smooth z with warm-start prior
            z_s = z_smoother.smooth(grid_key, z_raw, label=label)

            det = {
                "id":         i + 1,
                "category":   label,
                "confidence": obj.get("confidence", 0.0),
                "translation": [
                    -y,
                    -x,
                    z_s + h / 2.0 + mount_height,
                ],
                "size":     [l, w, h],
                "rotation": yaw_to_quaternion(theta_s),
            }
            objects.setdefault(label, []).append(det)

        except (KeyError, TypeError, ValueError) as exc:
            print(
                f"[lidar-publisher] Skipping malformed object {i} "
                f"in frame {frame_id}: {exc}",
                flush=True,
            )
            continue

    return objects


# ═══════════════════════════════════════════════════════════════════════════════
# Debug logging
# ═══════════════════════════════════════════════════════════════════════════════

def _debug_log(
    raw: dict,
    objects: dict,
    calibrator: MountHeightCalibrator,
) -> None:
    """Log one representative object per frame. [F10] Correlate by label."""
    for cat, objs in objects.items():
        if not objs:
            continue
        o = objs[0]

        raw_obj = next(
            (
                x for x in raw.get("objects", [])
                if (
                    x.get("label")
                    or KITTI_LABELS.get(x.get("label_id", -1), "object")
                ) == cat
                and isinstance(x.get("bbox_3d"), dict)
            ),
            None,
        )
        if raw_obj is None:
            continue

        b = raw_obj["bbox_3d"]
        t = o["translation"]
        print(
            f"[RAW]   {cat} "
            f"pp=({b.get('x', 0):.1f},{b.get('y', 0):.1f},{b.get('z', 0):.2f}) "
            f"theta={b.get('theta', 0):.3f} h={b.get('h', 0):.2f} "
            f"[mount_h={calibrator.mount_height:.3f}m "
            f"n={calibrator.sample_count}]",
            flush=True,
        )
        print(
            f"[SCENE] {cat} "
            f"scene=({t[0]:.1f},{t[1]:.1f},{t[2]:.2f}) "
            f"rot={[round(v, 3) for v in o['rotation']]}",
            flush=True,
        )
        break


# ═══════════════════════════════════════════════════════════════════════════════
# MQTT helpers
# ═══════════════════════════════════════════════════════════════════════════════

def connect_mqtt() -> mqtt.Client:
    client_id = f"lidar-stream-publisher-{uuid.uuid4().hex[:8]}"
    client    = mqtt.Client(client_id=client_id)
    if os.path.exists(ROOT_CA):
        client.tls_set(ca_certs=ROOT_CA)

    for attempt in range(10):
        try:
            client.connect(BROKER, PORT, keepalive=60)
            client.loop_start()
            print(
                f"[lidar-publisher] Connected to {BROKER}:{PORT} "
                f"(client_id={client_id})",
                flush=True,
            )
            return client
        except Exception as exc:
            print(
                f"[lidar-publisher] Connect attempt {attempt + 1}/10 failed: {exc}",
                flush=True,
            )
            time.sleep(2)

    raise RuntimeError("Could not connect to MQTT broker after 10 attempts")


def safe_publish(
    client: mqtt.Client,
    topic: str,
    payload: str,
) -> mqtt.Client:
    result = client.publish(topic, payload, qos=0)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        print(
            f"[lidar-publisher] Publish failed rc={result.rc}, reconnecting…",
            flush=True,
        )
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        client = connect_mqtt()
        client.publish(topic, payload, qos=0)
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# FIFO lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

def _make_fifo() -> None:
    if os.path.exists(FIFO):
        os.remove(FIFO)
    os.mkfifo(FIFO)


def _open_fifo_background(result: list) -> threading.Thread:
    """
    Open the FIFO in a daemon thread so the main thread is not blocked
    if the pipeline never starts writing.
    result[0] will hold the open file object on success.
    """
    def _worker():
        result[0] = open(FIFO, "r")

    t = threading.Thread(target=_worker, daemon=True, name="fifo-opener")
    t.start()
    return t


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # ── FIFO ──────────────────────────────────────────────────────────────────
    _make_fifo()
    fifo_result: list = [None]
    fifo_thread = _open_fifo_background(fifo_result)

    # ── MQTT ──────────────────────────────────────────────────────────────────
    client = connect_mqtt()

    # ── Pipeline ──────────────────────────────────────────────────────────────
    pipeline_cmd = _build_pipeline()
    print(f"[lidar-publisher] Pipeline command:\n  {pipeline_cmd}", flush=True)
    proc = subprocess.Popen(pipeline_cmd, shell=True, stderr=sys.stderr)
    print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    @atexit.register
    def _cleanup():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            os.remove(FIFO)
        except FileNotFoundError:
            pass
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    # ── Wait for FIFO ─────────────────────────────────────────────────────────
    fifo_thread.join(timeout=30.0)
    if fifo_result[0] is None:
        raise RuntimeError(
            "FIFO was not opened within 30 s — pipeline likely failed to start"
        )

    # ── Per-frame state ───────────────────────────────────────────────────────
    calibrator     = MountHeightCalibrator()
    theta_smoother = ThetaSmoother()
    z_smoother     = ZSmoother()

    published  = 0
    fps_alpha  = 0.75
    fps        = float(FRAME_RATE)
    last_ts: float | None = None

    # ── Read loop ─────────────────────────────────────────────────────────────
    with fifo_result[0] as fifo:
        for line in fifo:

            rc = proc.poll()
            if rc is not None and rc != 0:
                raise RuntimeError(
                    f"GStreamer pipeline exited with non-zero code {rc}"
                )

            line = line.strip()
            if not line:
                continue

            t_parse_start = time.perf_counter()
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[lidar-publisher] JSON decode error: {exc}", flush=True)
                continue
            t_parse_end = time.perf_counter()

            now = time.time()
            if last_ts is not None:
                instant = 1.0 / max(now - last_ts, 0.001)
                fps = fps * fps_alpha + (1.0 - fps_alpha) * instant
            last_ts = now

            t_convert_start = time.perf_counter()
            objects = convert_frame(
                raw, calibrator, theta_smoother, z_smoother, published
            )
            t_convert_end = time.perf_counter()

            if published % 50 == 0:
                _debug_log(raw, objects, calibrator)

            msg = {
                "id": SENSOR_ID,
                "timestamp": (
                    datetime.fromtimestamp(now, tz=timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                    + "Z"
                ),
                "rate":    round(fps, 2),
                "objects": objects,
            }
            payload = json.dumps(msg)

            t_pub_start = time.perf_counter()
            client = safe_publish(client, CAMERA_TOPIC, payload)
            t_pub_end = time.perf_counter()

            published += 1

            if published % 100 == 0:
                obj_count  = sum(len(v) for v in objects.values())
                ms_parse   = 1000 * (t_parse_end   - t_parse_start)
                ms_convert = 1000 * (t_convert_end - t_convert_start)
                ms_pub     = 1000 * (t_pub_end     - t_pub_start)
                print(
                    f"[lidar-publisher] frames={published:,} "
                    f"objects={obj_count} "
                    f"fps={fps:.1f} "
                    f"mount_h={calibrator.mount_height:.3f}m "
                    f"(n={calibrator.sample_count}) "
                    f"| parse={ms_parse:.1f}ms "
                    f"convert={ms_convert:.1f}ms "
                    f"publish={ms_pub:.1f}ms",
                    flush=True,
                )

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print("[lidar-publisher] Pipeline did not exit; terminating.", flush=True)
        proc.terminate()


if __name__ == "__main__":
    main()
