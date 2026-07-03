#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Publishes PointPillars detections in SceneScape camera detection format
with an in-publisher LiDAR -> scene coordinate pre-transform.

Coordinate transform (pre-applied before publishing):
  Uses the V2X virtuallidar_to_world calibration rotation matrix R_calib
  to properly project LiDAR detections into scene (map) coordinates.

  The scene image (LidarIntersection.png) is 1000x1000 px at 6.667 px/m covering
  150x150 m. The image is rotated so the LiDAR forward direction (SE) points UP.
  The LiDAR sensor sits near the bottom of the image at scene (75, 127) in metres.
  Scene X increases to the right (world east); scene Y increases downward
  (world south, i.e. world Y is flipped).  Therefore:

    [sx, sy, sz] = R_calib @ [x_l, y_l, z_l],  then  sy = -sy  (Y-flip)
    i.e.:
      scene_x =  R[0,0]*x_l + R[0,1]*y_l + R[0,2]*z_l
      scene_y = -(R[1,0]*x_l + R[1,1]*y_l + R[1,2]*z_l)
      scene_z =  R[2,0]*x_l + R[2,1]*y_l + R[2,2]*z_l

  These are offset coordinates relative to the LiDAR sensor origin. The
  SceneScape controller adds the DB camera pose translation [75, 127, 2.52]
  to produce the final scene position in metres.

  Calibration is loaded from the file pointed to by LIDAR_CALIB_FILE (a
  virtuallidar_to_world JSON from the V2X dataset). If the file is absent the
  publisher falls back to the legacy (-y, -x) axis swap with a warning.

Required lidar1 camera pose in SceneScape database:
  transform_type: euler
  rotation:       [0, 0, -148.97]   (pure Z rotation = -ROT_ANGLE to undo map rotation)
  translation:    [75, 127, 2.52]   (sensor at scene (75m, 127m), 2.52 m mount height)
  scale:          [1, 1, 1]

  Map: 1000×1000 px, 6.667 px/m, sensor-forward direction points UP.
  Coverage: ±75 m to sides, 23 m behind, 127 m in front of LiDAR.
  LiDAR pixel position: col=500, row=847 (85% from top).

bbox_3d.z from PointPillars is the bbox BOTTOM in LiDAR Z (verified from
bbox3d2corners: Z corners are [0, 1.0]*h, not [-0.5, 0.5]*h).
The box spans [z_lidar, z_lidar + h] in LiDAR Z.
So translation z sent to SceneScape = z_lidar directly (no h/2 adjustment).
The JS assetmanager.js::plot() calls translateZ(h/2) to shift the mesh origin
from the box BOTTOM to the box CENTRE, which is exactly what we need.

Heading transform:
  PointPillars theta = yaw in LiDAR frame, but the box layout convention
  (verified from bbox3d2corners in pointpillars/utils/process.py) places the
  LENGTH dimension along the LOCAL Y axis.  At theta=0 the object heading is
  along LiDAR +Y (not +X).  The actual heading unit vector is:
    h_lidar = [-sin(theta), cos(theta), 0]
  After applying the calibration rotation and the scene Y-flip the scene
  heading is:
    scene_heading = phi_calib - theta - pi/2
  where phi_calib = atan2(R[0][1], R[0][0]) (≈ +59° for the V2X intersection
  sensor).  The -pi/2 offset corrects for PointPillars' Y-forward (not X-forward)
  box convention.
  Published as Z-axis quaternion [0, 0, sin(h/2), cos(h/2)].

Z translation convention (SceneScape 3D renderer):
  assetmanager.js::plot() calls translateZ(size.z / 2) after position.set(),
  so it treats translation.z as the BOTTOM of the bounding box.
  PointPillars bbox_3d.z IS the box bottom (Z corners span [0, h] not
  [-h/2, +h/2] — see bbox3d2corners in pointpillars/utils/process.py).
  Therefore: publish sz = z_lidar directly.  The JS translateZ(h/2) then
  correctly lifts the mesh origin to the box centre.

Point cloud range / spatial coverage:
  Controlled exclusively via the model config JSON
  (LIDAR_MODEL_CONFIG, default pointpillars_ov_config.json).
  g3dlidarparse does NOT accept range properties -- it reads the range
  from the model config JSON that g3dinference also uses, so the clip
  boundary and voxelisation boundary are always consistent by design.

  Current config (verified at startup):
    point_cloud_range: [0, -39.68, -3, 69.12, 39.68, 1]
    voxel_size:        [0.16, 0.16, 4]
    max_num_points:    32
    max_voxels:        16000

  To change the range: edit the model config JSON only.
  The LIDAR_PC_* env vars are kept for banner display and validation
  cross-checking but are NOT passed to the pipeline.

Score threshold:
  Default 0.20 (reduced from 0.30) to recover partially occluded and
  distant objects. Increase LIDAR_SCORE_THRESHOLD if false-positive rate
  is too high for the deployment scene.

Tensor data (set LIDAR_ADD_TENSOR_DATA env var):
  false (default) -- gvametaconvert omits raw inference tensors.
                     Reduces FIFO payload by 10-100x; recommended for
                     production.
  true            -- include tensors (useful for offline debugging only).

Logging levels (set LOG_LEVEL env var):
  DEBUG   -- every frame: full per-object detail + transform check
  INFO    -- every 50 frames: one representative object summary (default)
  SUMMARY -- every 100 frames: counts + timing + stats only
  SILENT  -- periodic summary only, no per-frame object lines
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
from collections import defaultdict, deque
from datetime import datetime, timezone
from statistics import mean, stdev

import paho.mqtt.client as mqtt

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"

# ── LiDAR pipeline ────────────────────────────────────────────────────────────
SENSOR_ID   = os.environ.get("LIDAR_SENSOR_ID", "lidar1")
DATA_PATH   = os.environ.get(
    "LIDAR_DATA_PATH",
    "/home/pipeline-server/videos/velodyne_bin/%06d.bin",
)
START_INDEX = int(os.environ.get("LIDAR_START_INDEX", "10699"))

_STOP_RAW  = os.environ.get("LIDAR_STOP_INDEX")
STOP_INDEX = int(_STOP_RAW.strip()) if _STOP_RAW and _STOP_RAW.strip() else None

LOOP            = os.environ.get("LIDAR_LOOP", "true").lower() not in ("0", "false", "no")
FRAME_RATE      = int(os.environ.get("LIDAR_FRAME_RATE", "10"))
SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.20"))
MODEL_CONFIG    = os.environ.get(
    "LIDAR_MODEL_CONFIG",
    "/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json",
)

# DEVICE is validated against an allowlist before use in the shell command.
_DEVICE_RAW = os.environ.get("LIDAR_DEVICE", "CPU").strip().upper()
_ALLOWED_DEVICES = {
    "CPU", "GPU", "MYRIAD",
    "HETERO:CPU,GPU", "HETERO:GPU,CPU",
    "MULTI:CPU,GPU", "MULTI:GPU,CPU",
}
if _DEVICE_RAW not in _ALLOWED_DEVICES:
    raise ValueError(
        f"LIDAR_DEVICE={_DEVICE_RAW!r} is not in the allowed set "
        f"{sorted(_ALLOWED_DEVICES)}. Set LIDAR_DEVICE to one of those values."
    )
DEVICE = _DEVICE_RAW

# Tensor data: default false — tensors are not consumed by this publisher and
# their serialisation is the primary cause of the observed throughput gap.
ADD_TENSOR_DATA = os.environ.get("LIDAR_ADD_TENSOR_DATA", "false").lower()
if ADD_TENSOR_DATA not in ("true", "false"):
    ADD_TENSOR_DATA = "false"

# ── PointPillars spatial config (display / validation only) ───────────────────
# These values are used for banner display and cross-checking against the
# model config JSON.  They are NOT passed to the pipeline — g3dlidarparse
# reads the range from the model config JSON directly.
# Defaults match the manually updated config JSON.
PC_X_MIN = float(os.environ.get("LIDAR_PC_X_MIN", "0"))
PC_X_MAX = float(os.environ.get("LIDAR_PC_X_MAX",  "69.12"))
PC_Y_MIN = float(os.environ.get("LIDAR_PC_Y_MIN", "-39.68"))
PC_Y_MAX = float(os.environ.get("LIDAR_PC_Y_MAX",  "39.68"))
PC_Z_MIN = float(os.environ.get("LIDAR_PC_Z_MIN",  "-3"))
PC_Z_MAX = float(os.environ.get("LIDAR_PC_Z_MAX",   "1"))

# Derived — must equal z_max - z_min for single-layer PointPillars.
_VOXEL_Z_SIZE = round(PC_Z_MAX - PC_Z_MIN, 6)

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_LEVELS = ("DEBUG", "INFO", "SUMMARY", "SILENT")
LOG_LEVEL   = os.environ.get("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in _LOG_LEVELS:
    LOG_LEVEL = "INFO"

# ── Topics ────────────────────────────────────────────────────────────────────
CAMERA_TOPIC = f"scenescape/data/camera/{SENSOR_ID}"
FIFO         = "/tmp/lidar_detections.fifo"

# ── Raw detections passthrough ────────────────────────────────────────────────
# Set LIDAR_PUBLISH_RAW=true to mirror every raw gvametaconvert JSON line to a
# separate MQTT topic.  Useful for comparing raw PointPillars output against
# the processed SceneScape detections (object counts, coordinates, confidence).
# Default off — raw payloads can be large when tensor data is included.
PUBLISH_RAW = os.environ.get("LIDAR_PUBLISH_RAW", "false").lower() not in ("0", "false", "no")
RAW_TOPIC   = os.environ.get("LIDAR_RAW_TOPIC", f"scenescape/data/camera/{SENSOR_ID}-raw")

# ── Calibration (virtuallidar_to_world) ──────────────────────────────────────
# Path to the virtuallidar_to_world JSON file from the V2X dataset.  The file
# contains the 3x3 rotation matrix and translation that maps LiDAR sensor
# coordinates to the world (UTM-like) coordinate frame.  All frames in the
# V2X dataset share the same static calibration (verified across 010699-010703).
LIDAR_CALIB_FILE = os.environ.get(
    "LIDAR_CALIB_FILE",
    "/home/pipeline-server/data/calib/virtuallidar_to_world/010699.json",
)


def _load_calib_rotation() -> list[list[float]] | None:
    """
    Load R_calib (3x3, row-major) from LIDAR_CALIB_FILE.

    Returns the rotation matrix on success, None on failure (caller falls back
    to legacy transform with a warning).
    """
    try:
        with open(LIDAR_CALIB_FILE) as fh:
            calib = json.load(fh)
        R = calib["rotation"]  # 3x3 row-major
        if len(R) != 3 or any(len(row) != 3 for row in R):
            raise ValueError(f"Unexpected rotation shape in {LIDAR_CALIB_FILE}")
        det = (
            R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1])
            - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
            + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0])
        )
        if abs(det - 1.0) > 0.01:
            raise ValueError(
                f"det(R_calib)={det:.4f}, expected 1.0 — not a proper rotation"
            )
        print(
            f"[lidar-publisher] ✅ Calibration loaded: {LIDAR_CALIB_FILE}  "
            f"det(R)={det:.6f}  "
            f"sensor_yaw={math.degrees(math.atan2(-R[1][0], R[0][0])):.1f}° "
            f"(world frame, Y-up convention)",
            flush=True,
        )
        return R
    except FileNotFoundError:
        print(
            f"[lidar-publisher] ⚠️  Calibration file not found: {LIDAR_CALIB_FILE}\n"
            f"  Falling back to LEGACY (-y, -x) transform — positions will be\n"
            f"  incorrect unless the LiDAR forward axis aligns with scene -Y.\n"
            f"  Set LIDAR_CALIB_FILE to the virtuallidar_to_world JSON.",
            flush=True,
        )
        return None
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        print(
            f"[lidar-publisher] ⚠️  Calibration load error: {exc}\n"
            f"  Falling back to LEGACY (-y, -x) transform.",
            flush=True,
        )
        return None


_R_CALIB = _load_calib_rotation()

# Precomputed sensor yaw in the scene frame:
#   phi_calib = atan2(R[0][1], R[0][0])
# For V2X yizhuang09 intersection sensor: phi_calib ≈ +59° (south-east).
# scene_heading = phi_calib - theta
# Legacy fallback phi_calib = -pi/2 reproduces the old -(theta+pi/2) formula.
_CALIB_YAW: float = (
    math.atan2(_R_CALIB[0][1], _R_CALIB[0][0])
    if _R_CALIB is not None
    else -math.pi / 2.0
)

# ── GStreamer clock → wall-clock conversion ───────────────────────────────────
# exit_source_timestamp from gvametaconvert is a GStreamer monotonic clock value
# in nanoseconds.  On the first frame we compute the offset between the GST
# clock and the system wall clock; subsequent frames use the GST delta so the
# published timestamp reflects true capture time, not processing latency.
_gst_wall_offset: float | None = None


def _gst_to_wall(gst_ns: int) -> float:
    """
    Convert a GStreamer monotonic timestamp (nanoseconds) to a POSIX wall-clock
    timestamp (seconds since Unix epoch).

    On the first call the offset is computed as:  wall - gst_s.
    Subsequent calls use the fixed offset so inter-frame deltas come from the
    GStreamer clock (which is tied to the sensor capture rate) rather than OS
    scheduling jitter.
    """
    global _gst_wall_offset
    gst_s = gst_ns / 1e9
    if _gst_wall_offset is None:
        _gst_wall_offset = time.time() - gst_s
        print(
            f"[lidar-publisher] GST clock anchored: offset={_gst_wall_offset:.3f} s "
            f"(gst={gst_s:.3f} s)",
            flush=True,
        )
    return gst_s + _gst_wall_offset

# ── KITTI label map ───────────────────────────────────────────────────────────
# Matches the class order used in the OpenVINO PointPillars model training
# (see openvino_contrib/modules/3d/pointPillars/pointpillars/dataset/kitti.py).
KITTI_LABELS: dict[int, str] = {
    0: "Pedestrian",
    1: "Cyclist",
    2: "Car",
}

# ── Stats window ──────────────────────────────────────────────────────────────
_WINDOW = 100

# ── EMA smoothing for FPS ─────────────────────────────────────────────────────
# 0.1 → reacts in ~2 frames; keeps alerts responsive.
_FPS_EMA_SMOOTHING = 0.1

# ── Throughput alert thresholds ───────────────────────────────────────────────
_FPS_WARN_RATIO     = 0.75
_FPS_CRITICAL_RATIO = 0.50

# -- SceneScape camera pose reminder ---------------------------------------------
# Printed in the startup banner.  DB must match the new 150m rotated map:
#   translation [75, 127, 2.52]  (sensor at scene metres, 2.52 m mount height)
#   rotation    [0, 0, -148.97]  (pure Z rotation = -ROT_ANGLE undoes map rotation)
_LIDAR1_DB_ROTATION = [0.0, 0.0, -148.97]  # euler XYZ degrees — pure Z rotation


# ═══════════════════════════════════════════════════════════════════════════════
# Model config validation
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_model_config() -> None:
    """
    Read the installed model config JSON and warn if its spatial parameters
    do not match the LIDAR_PC_* env vars.

    This is a read-only check — the file is never modified.
    Mismatches are warnings, not errors.  The model config JSON is the
    authoritative source for both g3dlidarparse and g3dinference; the
    env vars are used only for display and this cross-check.
    """
    try:
        with open(MODEL_CONFIG) as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        print(
            f"[lidar-publisher] ⚠️  Model config not found at {MODEL_CONFIG} — "
            f"g3dinference will fail to start.",
            flush=True,
        )
        return
    except json.JSONDecodeError as exc:
        print(
            f"[lidar-publisher] ⚠️  Model config JSON parse error: {exc}",
            flush=True,
        )
        return

    vp = cfg.get("voxel_params", {})

    # Check point_cloud_range
    cfg_range = vp.get("point_cloud_range", [])
    env_range = [PC_X_MIN, PC_Y_MIN, PC_Z_MIN, PC_X_MAX, PC_Y_MAX, PC_Z_MAX]
    if cfg_range != env_range:
        print(
            f"[lidar-publisher] ⚠️  point_cloud_range MISMATCH\n"
            f"  config JSON : {cfg_range}\n"
            f"  env vars    : {env_range}\n"
            f"  The model config JSON is authoritative. Update the\n"
            f"  LIDAR_PC_* env vars to match if this is intentional.",
            flush=True,
        )
    else:
        print(
            f"[lidar-publisher] ✅ point_cloud_range consistent: {cfg_range}",
            flush=True,
        )

    # Check voxel_size Z component
    cfg_voxel = vp.get("voxel_size", [])
    if len(cfg_voxel) == 3:
        cfg_z = round(cfg_voxel[2], 6)
        if abs(cfg_z - _VOXEL_Z_SIZE) > 1e-4:
            print(
                f"[lidar-publisher] ⚠️  voxel_size Z MISMATCH\n"
                f"  config JSON : {cfg_z}\n"
                f"  derived     : {_VOXEL_Z_SIZE} (z_max - z_min)\n"
                f"  These must be equal for single-layer PointPillars.",
                flush=True,
            )
        else:
            print(
                f"[lidar-publisher] ✅ voxel_size Z consistent: {cfg_z}",
                flush=True,
            )

    print(
        f"[lidar-publisher]    max_voxels={vp.get('max_voxels')}  "
        f"max_num_points={vp.get('max_num_points')}",
        flush=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Label resolution
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_label(obj: dict) -> tuple[str, str]:
    """
    Return (label, source) where source is one of:
      "label_str"        — came from obj["label"] string field
      "label_id"         — came from obj["label_id"] int via KITTI_LABELS
      "label_id_unknown" — label_id present but not in KITTI_LABELS
      "fallback"         — neither field present or recognised
    """
    label_str = obj.get("label")
    if label_str and isinstance(label_str, str) and label_str.strip():
        return label_str.strip(), "label_str"

    label_id = obj.get("label_id")
    if label_id is not None:
        try:
            lid = int(label_id)
            if lid in KITTI_LABELS:
                return KITTI_LABELS[lid], "label_id"
            return f"unknown_{lid}", "label_id_unknown"
        except (ValueError, TypeError):
            pass

    return "object", "fallback"


# ═══════════════════════════════════════════════════════════════════════════════
# Rolling statistics collector
# ═══════════════════════════════════════════════════════════════════════════════

class FrameStats:
    """
    Collects per-frame metrics over a rolling window and produces
    a structured summary string on demand.

    Tracks:
      - fps (rolling window for mean + stdev)
      - object counts per class
      - confidence per class
      - timing breakdown (parse / build / publish ms)
      - zero-object frame count
      - publish / json error counts
      - payload size bytes
      - label source distribution
      - per-class count history across summary windows (change detection)
    """

    def __init__(self, window: int = _WINDOW):
        self._w = window

        self.fps_samples:   deque[float] = deque(maxlen=window)
        self.parse_ms:      deque[float] = deque(maxlen=window)
        self.build_ms:      deque[float] = deque(maxlen=window)
        self.publish_ms:    deque[float] = deque(maxlen=window)
        self.payload_bytes: deque[int]   = deque(maxlen=window)
        self.object_counts: deque[int]   = deque(maxlen=window)

        self.conf_samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=window)
        )
        self.class_counts: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=window)
        )

        # Per-class rolling history of summary-window averages.
        # Used for change-detection alerts across summary windows.
        # Keeps the last 10 summary averages (~1000 frames at window=100).
        self._class_avg_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=10)
        )

        # Label source counters — reset each summary window so the summary
        # reflects the most recent window rather than lifetime totals.
        self.label_sources: dict[str, int] = defaultdict(int)

        # Cumulative counters
        self.total_frames:          int = 0
        self.total_objects:         int = 0
        self.zero_object_frames:    int = 0
        self.publish_failures:      int = 0
        self.json_errors:           int = 0

        self._consecutive_zeros:    int = 0
        self.max_consecutive_zeros: int = 0

    @property
    def consecutive_zeros(self) -> int:
        return self._consecutive_zeros

    def record_frame(
        self,
        fps: float,
        objects: dict,
        parse_ms: float,
        build_ms: float,
        publish_ms: float,
        payload_bytes: int,
        label_sources: dict[str, int],
    ) -> None:
        self.total_frames += 1
        self.fps_samples.append(fps)
        self.parse_ms.append(parse_ms)
        self.build_ms.append(build_ms)
        self.publish_ms.append(publish_ms)
        self.payload_bytes.append(payload_bytes)

        total = sum(len(v) for v in objects.values())
        self.object_counts.append(total)
        self.total_objects += total

        if total == 0:
            self.zero_object_frames += 1
            self._consecutive_zeros += 1
            self.max_consecutive_zeros = max(
                self.max_consecutive_zeros, self._consecutive_zeros
            )
        else:
            self._consecutive_zeros = 0

        for label, objs in objects.items():
            self.class_counts[label].append(len(objs))
            for o in objs:
                self.conf_samples[label].append(o.get("confidence", 0.0))

        for src, cnt in label_sources.items():
            self.label_sources[src] += cnt

    def record_publish_failure(self) -> None:
        self.publish_failures += 1

    def record_json_error(self) -> None:
        self.json_errors += 1

    @staticmethod
    def _fmt(d: deque, unit: str = "", fmt: str = ".1f") -> str:
        if not d:
            return "n/a"
        vals = list(d)
        mn   = min(vals)
        mx   = max(vals)
        avg  = mean(vals)
        sd   = stdev(vals) if len(vals) > 1 else 0.0
        return f"{avg:{fmt}}{unit} ±{sd:{fmt}} [{mn:{fmt}}–{mx:{fmt}}]"

    def summary(self) -> str:
        """
        Produce a human-readable summary of the current rolling window.

        Side-effect: snapshots per-class averages into _class_avg_history
        for change-detection in alert_check(), then resets label_sources
        so the next window reflects only new data.
        """
        lines = []

        lines.append(
            f"  throughput : {self._fmt(self.fps_samples, 'Hz')}  "
            f"total_frames={self.total_frames:,}"
        )
        lines.append(
            f"  objects    : {self._fmt(self.object_counts, '/frame', '.0f')}  "
            f"total={self.total_objects:,}  "
            f"zero_frames={self.zero_object_frames} "
            f"(max_consec={self.max_consecutive_zeros})"
        )

        for label in sorted(self.class_counts):
            counts = self.class_counts[label]
            confs  = self.conf_samples[label]
            avg_c  = mean(list(counts)) if counts else 0.0
            avg_f  = mean(list(confs))  if confs  else 0.0
            min_f  = min(list(confs))   if confs  else 0.0
            max_f  = max(list(confs))   if confs  else 0.0
            lines.append(
                f"  {label:<14}: avg={avg_c:.1f}/frame  "
                f"conf avg={avg_f:.3f} [{min_f:.3f}–{max_f:.3f}]"
            )
            self._class_avg_history[label].append(avg_c)

        if self.label_sources:
            src_str = "  ".join(
                f"{k}={v}" for k, v in sorted(self.label_sources.items())
            )
            lines.append(f"  label_src  : {src_str}")

        lines.append(
            f"  timing     : parse={self._fmt(self.parse_ms, 'ms')}  "
            f"build={self._fmt(self.build_ms, 'ms')}  "
            f"publish={self._fmt(self.publish_ms, 'ms')}"
        )
        lines.append(
            f"  payload    : {self._fmt(self.payload_bytes, 'B', '.0f')}"
        )
        lines.append(
            f"  health     : publish_failures={self.publish_failures}  "
            f"json_errors={self.json_errors}"
        )

        # Reset so the next summary window shows only new label source data.
        self.label_sources = defaultdict(int)

        return "\n".join(lines)

    def alert_check(self) -> list[str]:
        """
        Return a list of human-readable alert strings.
        Empty list means all clear.

        FPS alerts use two thresholds (warn 75%, critical 50%).
        Class-count alerts use change detection against a rolling baseline
        of recent summary-window averages — avoids false positives in scenes
        that legitimately have many objects of one class.
        """
        alerts = []

        # ── throughput ────────────────────────────────────────────────────────
        if self.fps_samples:
            current_fps = list(self.fps_samples)[-1]
            if current_fps < FRAME_RATE * _FPS_CRITICAL_RATIO:
                alerts.append(
                    f"FPS {current_fps:.1f} < {_FPS_CRITICAL_RATIO*100:.0f}% "
                    f"of configured {FRAME_RATE} Hz — severe throughput loss. "
                    f"Check LIDAR_ADD_TENSOR_DATA and LIDAR_DEVICE."
                )
            elif current_fps < FRAME_RATE * _FPS_WARN_RATIO:
                alerts.append(
                    f"FPS {current_fps:.1f} < {_FPS_WARN_RATIO*100:.0f}% "
                    f"of configured {FRAME_RATE} Hz — sustained throughput gap. "
                    f"Consider LIDAR_ADD_TENSOR_DATA=false or LIDAR_DEVICE=GPU."
                )

        # ── consecutive zero-object frames ────────────────────────────────────
        if self._consecutive_zeros >= 5:
            alerts.append(
                f"{self._consecutive_zeros} consecutive frames with 0 objects"
            )

        # ── confidence near threshold ─────────────────────────────────────────
        for label, confs in self.conf_samples.items():
            if confs:
                avg_conf = mean(list(confs))
                if avg_conf < SCORE_THRESHOLD + 0.05:
                    alerts.append(
                        f"{label} avg confidence {avg_conf:.3f} near "
                        f"threshold {SCORE_THRESHOLD}"
                    )

        # ── publish health ────────────────────────────────────────────────────
        if self.publish_failures > 0:
            alerts.append(
                f"{self.publish_failures} cumulative publish failures"
            )

        # ── payload size ──────────────────────────────────────────────────────
        if self.payload_bytes:
            max_bytes = max(self.payload_bytes)
            if max_bytes > 65536:
                alerts.append(
                    f"Payload spike {max_bytes:,} B — tensor data may be "
                    f"included. Set LIDAR_ADD_TENSOR_DATA=false."
                )

        # ── per-class change detection ────────────────────────────────────────
        # Requires at least 3 prior summary windows to establish a baseline.
        for label, history in self._class_avg_history.items():
            hist_list = list(history)
            if len(hist_list) < 3:
                continue
            baseline = mean(hist_list[:-1])
            current  = hist_list[-1]
            if baseline < 0.1:
                continue
            ratio = current / baseline
            if ratio > 1.5:
                alerts.append(
                    f"{label} count {current:.1f}/frame is "
                    f"{(ratio - 1) * 100:.0f}% above recent baseline "
                    f"{baseline:.1f}/frame — possible misclassification or "
                    f"scene change"
                )
            elif ratio < 0.5:
                alerts.append(
                    f"{label} count {current:.1f}/frame is "
                    f"{(1 - ratio) * 100:.0f}% below recent baseline "
                    f"{baseline:.1f}/frame — possible occlusion or scene change"
                )

        # ── label resolution health ───────────────────────────────────────────
        fallback_count = self.label_sources.get("fallback", 0)
        if fallback_count > 0:
            alerts.append(
                f"{fallback_count} objects used fallback label — "
                f"label and label_id both missing or unrecognised"
            )

        unknown_count = self.label_sources.get("label_id_unknown", 0)
        if unknown_count > 0:
            alerts.append(
                f"{unknown_count} objects had label_id not in KITTI_LABELS"
            )

        return alerts


# ═══════════════════════════════════════════════════════════════════════════════
# GStreamer pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pipeline() -> str:
    """
    Build the gst-launch-1.0 command string.

    g3dlidarparse does not accept range properties — it reads the
    point_cloud_range from the model config JSON that g3dinference also
    uses.  No range arguments are passed here; the model config JSON is
    the single authoritative source for spatial parameters.

    All environment-derived string values are passed through shlex.quote().
    DEVICE is validated against an allowlist at module load time.
    Numeric parameters cannot carry shell metacharacters.
    """
    location  = shlex.quote(DATA_PATH)
    config    = shlex.quote(MODEL_CONFIG)
    fifo_path = shlex.quote(FIFO)
    device_q  = shlex.quote(DEVICE)

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
        # g3dlidarparse reads point_cloud_range from the model config JSON.
        # Do not pass range properties here — the element does not support them.
        f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE}",
        "! g3dinference",
        f"config={config}",
        f"device={device_q}",
        f"score-threshold={SCORE_THRESHOLD}",
        f"! gvametaconvert add-tensor-data={ADD_TENSOR_DATA} format=json",
        f"! gvametapublish method=file file-format=json-lines"
        f" file-path={fifo_path}",
        "! fakesink",
    ]
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Raw frame → SceneScape message
# ═══════════════════════════════════════════════════════════════════════════════

def _lidar_to_scene_offset(
    x_l: float, y_l: float, z_l: float
) -> tuple[float, float, float]:
    """
    Apply the calibration rotation and the scene Y-flip to a LiDAR point,
    returning the scene-frame offset relative to the sensor origin.

    The SceneScape controller will add the DB camera pose translation
    [200, 200, 2.52] to produce the final scene position in metres.

    If _R_CALIB is None (calibration file missing) the legacy (-y, -x) axis
    swap is used as a fallback.
    """
    if _R_CALIB is not None:
        R = _R_CALIB
        sx =   R[0][0] * x_l + R[0][1] * y_l + R[0][2] * z_l
        sy = -(R[1][0] * x_l + R[1][1] * y_l + R[1][2] * z_l)
        sz =   R[2][0] * x_l + R[2][1] * y_l + R[2][2] * z_l
    else:
        sx = -y_l
        sy = -x_l
        sz =  z_l
    return sx, sy, sz


def bbox3d_to_quaternion(theta: float) -> list[float]:
    """
    Convert PointPillars yaw to unit quaternion [qx, qy, qz, qw] in the
    SceneScape scene frame.

    theta -- yaw in LiDAR frame (radians).

    PointPillars box layout (from bbox3d2corners in pointpillars/utils/process.py):
      - dim[0] = w  → X extent of the unrotated box  (side-to-side)
      - dim[1] = l  → Y extent of the unrotated box  (front-to-back)
      - rotation rotates the box around Z
      → at theta=0, the FRONT of the box points toward LiDAR +Y (left/north)
      → the heading unit vector is h_lidar = [-sin(theta), cos(theta), 0]

    After calibration rotation (R_calib) and scene Y-flip:
      h_world_x =  R[0,0]*(-sin θ) + R[0,1]*cos θ  = sin(φ - θ)  where φ = phi_calib
      h_world_y =  R[1,0]*(-sin θ) + R[1,1]*cos θ  = cos(φ - θ)
      scene_heading = atan2(-h_world_y, h_world_x)
                    = atan2(-cos(φ-θ), sin(φ-θ))
                    = (φ - θ) - π/2
                    = _CALIB_YAW - theta - pi/2

    Published as Z-axis rotation quaternion [0, 0, sin(h/2), cos(h/2)].
    Canonical form: qw >= 0.
    """
    scene_heading = _CALIB_YAW - theta - math.pi / 2
    half = scene_heading / 2.0
    qz   = math.sin(half)
    qw   = math.cos(half)
    if qw < 0.0:
        qz, qw = -qz, -qw
    EPS = 1e-6
    qz  = max(-1.0 + EPS, min(1.0 - EPS, qz))
    qw  = max(-1.0 + EPS, min(1.0 - EPS, qw))
    return [0.0, 0.0, qz, qw]


def _make_timestamp(now: float) -> str:
    """
    Format a UTC timestamp as ISO-8601 with millisecond precision.

    Uses explicit integer arithmetic rather than string slicing so the
    result is correct on all platforms regardless of strftime %f width.
    """
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def build_camera_message(
    raw: dict,
    sensor_id: str,
    fps: float,
) -> tuple[dict, list[str], dict[str, int]]:
    """
    Wrap gvametaconvert detections in SceneScape camera message format.

    Returns:
      (message_dict, debug_lines, label_source_counts)

    Coordinate pre-transform applied here via _lidar_to_scene_offset():
      [sx, sy, sz] = R_calib @ [x_l, y_l, z_l]  with  sy = -sy  (Y-flip)
    Heading: scene_heading = phi_calib - theta - pi/2, encoded as Z-axis quaternion.
    The SceneScape controller adds the DB camera pose translation [200, 200, 2.52].

    Timestamp is derived exclusively from raw["lidar_frame"]["exit_source_timestamp"]
    via _gst_to_wall().  If the field is absent a fallback to time.time() is used
    with a one-time warning so the message is never silently timestamped wrong.
    """
    objects:       dict[str, list] = {}
    debug_lines:   list[str]       = []
    label_sources: dict[str, int]  = defaultdict(int)

    # Timestamp comes exclusively from the source frame, not the publishing clock.
    _gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
    if _gst_ns is not None:
        _ts = _make_timestamp(_gst_to_wall(int(_gst_ns)))
    else:
        _ts = _make_timestamp(time.time())
        print(
            "[lidar-publisher] ⚠️  exit_source_timestamp missing — "
            "falling back to wall clock for this frame",
            flush=True,
        )

    for i, obj in enumerate(raw.get("objects", [])):
        bbox = obj.get("bbox_3d")
        if not isinstance(bbox, dict):
            if LOG_LEVEL == "DEBUG":
                debug_lines.append(f"  [obj {i}] SKIP — no bbox_3d")
            continue

        try:
            label, source = resolve_label(obj)
            label_sources[source] += 1

            x_l   = bbox.get("x", 0.0)   # LiDAR X = forward
            y_l   = bbox.get("y", 0.0)   # LiDAR Y = left
            z_l   = bbox.get("z", 0.0)   # bbox centre in LiDAR frame
            w     = bbox.get("w", 0.0)
            l     = bbox.get("l", 0.0)
            h     = bbox.get("h", 0.0)
            theta = bbox.get("theta", 0.0)
            conf  = obj.get("confidence", 0.0)
            rot   = bbox3d_to_quaternion(theta)

            # Apply calibration rotation + scene Y-flip.
            # sz includes the tilt correction (R[2,0]*x + R[2,1]*y) which
            # amounts to ~0.4 m at 50 m range for the V2X sensor.
            sx, sy, sz = _lidar_to_scene_offset(x_l, y_l, z_l)
            # z_l IS the box bottom (PointPillars Z corners span [0,h], not
            # [-h/2,+h/2]). Send sz directly; assetmanager.js translateZ(h/2)
            # then lifts the origin to the box centre.

            det = {
                "id":          i + 1,
                "category":    label,
                "confidence":  conf,
                "translation": [sx, sy, sz],
                "size":        [l, w, h],
                "rotation":    rot,
            }
            objects.setdefault(label, []).append(det)

            if LOG_LEVEL == "DEBUG":
                debug_lines.append(
                    f"  [obj {i:02d}] {label:<14} src={source:<16} "
                    f"lidar=({x_l:7.2f},{y_l:7.2f},{z_l:7.2f}) "
                    f"scene=({sx:7.2f},{sy:7.2f},{sz:7.2f}) "
                    f"lwh=({l:.2f},{w:.2f},{h:.2f}) "
                    f"theta={theta:+.3f} "
                    f"rot=[{rot[2]:+.3f},{rot[3]:+.3f}] "
                    f"conf={conf:.3f} "
                    f"raw_label={obj.get('label')!r} "
                    f"raw_label_id={obj.get('label_id')!r}"
                )

        except (KeyError, TypeError, ValueError) as exc:
            debug_lines.append(f"  [obj {i}] ERROR — {exc}")
            continue

    msg = {
        "id":        sensor_id,
        "timestamp": _ts,
        "rate":      round(fps, 2),
        "objects":   objects,
    }
    return msg, debug_lines, dict(label_sources)


# ═══════════════════════════════════════════════════════════════════════════════
# Logging helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _log_frame_debug(
    raw: dict,
    msg: dict,
    debug_lines: list[str],
    published: int,
    fps: float,
) -> None:
    obj_count = sum(len(v) for v in msg["objects"].values())
    print(
        f"\n[DEBUG frame={published:,} ts={msg['timestamp']} "
        f"fps={fps:.1f} objects={obj_count}]",
        flush=True,
    )
    for line in debug_lines:
        print(line, flush=True)

    for cat, objs in msg["objects"].items():
        if not objs:
            continue
        o = objs[0]
        raw_obj = next(
            (
                x for x in raw.get("objects", [])
                if resolve_label(x)[0] == cat
                and isinstance(x.get("bbox_3d"), dict)
            ),
            None,
        )
        if raw_obj:
            b  = raw_obj["bbox_3d"]
            t  = o["translation"]
            exp_sx, exp_sy, exp_sz = _lidar_to_scene_offset(
                b.get("x", 0), b.get("y", 0), b.get("z", 0)
            )
            ok = (
                abs(t[0] - exp_sx) < 1e-4
                and abs(t[1] - exp_sy) < 1e-4
                and abs(t[2] - exp_sz) < 1e-4
            )
            print(
                f"  transform={'✅ OK' if ok else '⚠️  MISMATCH'} "
                f"lidar=({b.get('x',0):.3f},{b.get('y',0):.3f},{b.get('z',0):.3f}) "
                f"→ scene=({exp_sx:.3f},{exp_sy:.3f},{exp_sz:.3f}) [bottom]"
                f"  pub=({t[0]:.3f},{t[1]:.3f},{t[2]:.3f})",
                flush=True,
            )
        break


def _log_frame_info(
    raw: dict,
    msg: dict,
    published: int,
    fps: float,
) -> None:
    for cat, objs in msg["objects"].items():
        if not objs:
            continue
        o = objs[0]
        raw_obj = next(
            (
                x for x in raw.get("objects", [])
                if resolve_label(x)[0] == cat
                and isinstance(x.get("bbox_3d"), dict)
            ),
            None,
        )
        if raw_obj is None:
            continue
        b  = raw_obj["bbox_3d"]
        t  = o["translation"]
        exp_sx, exp_sy, exp_sz = _lidar_to_scene_offset(
            b.get("x", 0), b.get("y", 0), b.get("z", 0)
        )
        ok = (
            abs(t[0] - exp_sx) < 1e-4
            and abs(t[1] - exp_sy) < 1e-4
            and abs(t[2] - exp_sz) < 1e-4
        )
        _, src = resolve_label(raw_obj)
        print(
            f"[frame={published:,} fps={fps:.1f}] {cat} "
            f"{'✅' if ok else '⚠️ MISMATCH'} "
            f"src={src} "
            f"lidar=({b.get('x',0):.2f},{b.get('y',0):.2f},{b.get('z',0):.2f}) "
            f"→ scene=({exp_sx:.2f},{exp_sy:.2f},{exp_sz:.2f}) [bottom] "
            f"h={b.get('h',0):.2f} theta={b.get('theta',0):.3f} "
            f"pub_t=({t[0]:.2f},{t[1]:.2f},{t[2]:.2f}) "
            f"rot={[round(v,3) for v in o['rotation']]} "
            f"conf={o['confidence']:.2f}",
            flush=True,
        )
        break


def _log_zero_frame(published: int, fps: float, consecutive: int) -> None:
    print(
        f"[lidar-publisher] ⚠️  ZERO OBJECTS "
        f"frame={published:,} fps={fps:.1f} consecutive={consecutive}",
        flush=True,
    )


def _log_summary(published: int, stats: FrameStats) -> None:
    alerts    = stats.alert_check()
    alert_str = (
        "\n  " + "\n  ".join(f"⚠️  ALERT: {a}" for a in alerts)
        if alerts else ""
    )
    print(
        f"\n[lidar-publisher] ── SUMMARY frames={published:,} ──\n"
        f"{stats.summary()}"
        f"{alert_str}",
        flush=True,
    )


def _log_throughput_warning(avg_fps: float) -> None:
    print(
        f"[lidar-publisher] ⚠️  Sustained throughput {avg_fps:.1f} Hz is below "
        f"80% of target {FRAME_RATE} Hz after first summary window.\n"
        f"  Recommended actions:\n"
        f"    1. Ensure LIDAR_ADD_TENSOR_DATA=false (current: {ADD_TENSOR_DATA})\n"
        f"    2. Consider LIDAR_DEVICE=GPU if a GPU is available "
        f"(current: {DEVICE})\n"
        f"    3. Reduce LIDAR_FRAME_RATE if the source cannot sustain "
        f"{FRAME_RATE} Hz",
        flush=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MQTT helpers
# ═══════════════════════════════════════════════════════════════════════════════

class _MqttState:
    """
    Holds the current MQTT client so the atexit handler always disconnects
    the current client even after reconnects inside safe_publish().
    """

    def __init__(self) -> None:
        self.client: mqtt.Client | None = None

    def set(self, client: mqtt.Client) -> None:
        self.client = client

    def shutdown(self) -> None:
        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self.client = None


_mqtt_state = _MqttState()


def connect_mqtt() -> mqtt.Client:
    client_id = f"lidar-raw-publisher-{uuid.uuid4().hex[:8]}"
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
            _mqtt_state.set(client)
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
    stats: FrameStats,
) -> mqtt.Client:
    """
    Publish payload, reconnecting once on failure.

    Both the initial publish and the retry are checked for errors.
    Returns the (possibly new) client so the caller can update its reference.
    """
    result = client.publish(topic, payload, qos=0)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        stats.record_publish_failure()
        print(
            f"[lidar-publisher] ⚠️  Publish failed rc={result.rc}, "
            f"reconnecting…",
            flush=True,
        )
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        client       = connect_mqtt()
        retry_result = client.publish(topic, payload, qos=0)
        if retry_result.rc != mqtt.MQTT_ERR_SUCCESS:
            stats.record_publish_failure()
            print(
                f"[lidar-publisher] ⚠️  Retry publish also failed "
                f"rc={retry_result.rc} — message dropped",
                flush=True,
            )
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# FIFO lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

def _make_fifo() -> None:
    if os.path.exists(FIFO):
        os.remove(FIFO)
    os.mkfifo(FIFO)


def _open_fifo_background(result: list) -> threading.Thread:
    def _worker():
        result[0] = open(FIFO, "r")
    t = threading.Thread(target=_worker, daemon=True, name="fifo-opener")
    t.start()
    return t


# ═══════════════════════════════════════════════════════════════════════════════
# Startup banner
# ═══════════════════════════════════════════════════════════════════════════════

def _print_banner() -> None:
    range_str = (
        f"[{PC_X_MIN}, {PC_Y_MIN}, {PC_Z_MIN}, "
        f"{PC_X_MAX}, {PC_Y_MAX}, {PC_Z_MAX}]"
    )
    coverage = "360°" if PC_X_MIN < 0 else "front hemisphere only"
    print(
        f"\n{'='*60}\n"
        f"  lidar-publisher startup\n"
        f"{'='*60}\n"
        f"  sensor_id      : {SENSOR_ID}\n"
        f"  mqtt_broker    : {BROKER}:{PORT}\n"
        f"  topic          : {CAMERA_TOPIC}\n"
        f"  data_path      : {DATA_PATH}\n"
        f"  start_index    : {START_INDEX}\n"
        f"  stop_index     : "
        f"{STOP_INDEX if STOP_INDEX is not None else 'none (run to end)'}\n"
        f"  loop           : {LOOP}\n"
        f"  frame_rate     : {FRAME_RATE} Hz\n"
        f"  device         : {DEVICE}\n"
        f"  score_thresh   : {SCORE_THRESHOLD}\n"
        f"  model_config   : {MODEL_CONFIG}  (read-only — managed externally)\n"
        f"  add_tensor_data: {ADD_TENSOR_DATA}"
        f"{'  ← set LIDAR_ADD_TENSOR_DATA=false for production' if ADD_TENSOR_DATA == 'true' else ''}\n"
        f"  log_level      : {LOG_LEVEL}\n"
        f"  publish_raw    : {PUBLISH_RAW}"
        f"{'  topic: ' + RAW_TOPIC if PUBLISH_RAW else '  (set LIDAR_PUBLISH_RAW=true to enable)'}\n"
        f"  coordinate     : calibration-based R_calib @ p_lidar (Y-flipped)\n"
        f"  calib_file     : {LIDAR_CALIB_FILE}\n"
        f"  calib_yaw      : {math.degrees(_CALIB_YAW):.2f}° "
        f"({'loaded from file' if _R_CALIB is not None else 'LEGACY FALLBACK -90°'})\n"
        f"  heading_formula: scene_heading = calib_yaw - theta - 90°  "
        f"(PointPillars Y-forward: theta=0 → heading along LiDAR +Y)\n"
        f"  z_convention   : publisher sends z_lidar directly  "
        f"(PointPillars Z is box bottom; JS translateZ(h/2) lifts to centre)\n"
        f"  lidar1_DB_rot  : {_LIDAR1_DB_ROTATION} euler  "
        f"(identity -- rotation done in publisher)\n"
        f"  point_cloud    : {range_str}  ({coverage})\n"
        f"  voxel_z_size   : {_VOXEL_Z_SIZE}  (derived: z_max - z_min)\n"
        f"  range_source   : model config JSON (g3dlidarparse has no range props)\n"
        f"  tls            : "
        f"{'yes' if os.path.exists(ROOT_CA) else 'no (no CA cert found)'}\n"
        f"  kitti_labels   : {KITTI_LABELS}\n"
        f"  fps_ema        : smoothing={_FPS_EMA_SMOOTHING} "
        f"warn={_FPS_WARN_RATIO*100:.0f}% "
        f"critical={_FPS_CRITICAL_RATIO*100:.0f}%\n"
        f"{'='*60}\n",
        flush=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    _print_banner()

    # Read-only validation: warn if env vars and model config JSON disagree.
    _validate_model_config()

    _make_fifo()

    # Start the pipeline before connecting to MQTT so that the GStreamer
    # process is already writing to the FIFO by the time we open it for
    # reading.  This prevents the 30-second FIFO-open timeout from being
    # consumed by MQTT connection retries.
    pipeline_cmd = _build_pipeline()
    print(f"[lidar-publisher] Pipeline:\n  {pipeline_cmd}\n", flush=True)
    proc = subprocess.Popen(pipeline_cmd, shell=True, stderr=sys.stderr)
    print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

    # Open the FIFO for reading in a background thread (blocks until the
    # pipeline writes its first byte).
    fifo_result: list = [None]
    fifo_thread = _open_fifo_background(fifo_result)

    # Connect to MQTT after the pipeline is running so MQTT retry delays
    # do not eat into the FIFO-open timeout.
    client = connect_mqtt()
    stats  = FrameStats(window=_WINDOW)

    @atexit.register
    def _cleanup():
        if stats.total_frames > 0:
            print(
                f"\n[lidar-publisher] ── FINAL SUMMARY ──\n{stats.summary()}",
                flush=True,
            )
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
        # Always disconnect the current client via _mqtt_state, which is
        # updated on every reconnect inside connect_mqtt().
        _mqtt_state.shutdown()

    fifo_thread.join(timeout=30.0)
    if fifo_result[0] is None:
        raise RuntimeError(
            "FIFO was not opened within 30 s — pipeline likely failed to start"
        )

    published  = 0
    fps        = float(FRAME_RATE)
    last_ts: float | None = None

    # Track whether we have already emitted the one-time throughput warning.
    _throughput_warned = False

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

            t0 = time.perf_counter()
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                stats.record_json_error()
                print(
                    f"[lidar-publisher] ⚠️  JSON error frame={published}: {exc}",
                    flush=True,
                )
                continue

            now = time.time()  # fallback if lidar_frame is missing
            gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
            if gst_ns is not None:
                now = _gst_to_wall(int(gst_ns))
            if last_ts is not None:
                instant = 1.0 / max(now - last_ts, 0.001)
                fps = fps * _FPS_EMA_SMOOTHING + (1.0 - _FPS_EMA_SMOOTHING) * instant
            last_ts = now

            t1 = time.perf_counter()
            msg, debug_lines, frame_label_sources = build_camera_message(
                raw, SENSOR_ID, fps
            )
            t2 = time.perf_counter()

            total_objs = sum(len(v) for v in msg["objects"].values())

            if total_objs > 0:
                payload     = json.dumps(msg)
                payload_len = len(payload.encode())
                client      = safe_publish(client, CAMERA_TOPIC, payload, stats)

                if PUBLISH_RAW:
                    client = safe_publish(client, RAW_TOPIC, line, stats)
            else:
                payload_len = 0

            t3          = time.perf_counter()

            stats.record_frame(
                fps           = fps,
                objects       = msg["objects"],
                parse_ms      = 1000 * (t1 - t0),
                build_ms      = 1000 * (t2 - t1),
                publish_ms    = 1000 * (t3 - t2),
                payload_bytes = payload_len,
                label_sources = frame_label_sources,
            )
            published += 1

            if total_objs == 0 and LOG_LEVEL != "SILENT":
                _log_zero_frame(published, fps, stats.consecutive_zeros)

            if LOG_LEVEL == "DEBUG":
                _log_frame_debug(raw, msg, debug_lines, published, fps)
            elif LOG_LEVEL == "INFO" and published % 50 == 0:
                _log_frame_info(raw, msg, published, fps)

            if published % 100 == 0:
                _log_summary(published, stats)

                # One-time throughput warning after the first full summary
                # window, so we have enough samples for a reliable average.
                if not _throughput_warned and stats.fps_samples:
                    avg_fps = mean(list(stats.fps_samples))
                    if avg_fps < FRAME_RATE * 0.8:
                        _log_throughput_warning(avg_fps)
                        _throughput_warned = True

    print(
        f"[lidar-publisher] FIFO closed — pipeline finished "
        f"(published={published:,} frames)",
        flush=True,
    )

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print(
            "[lidar-publisher] Pipeline did not exit; terminating.",
            flush=True,
        )
        proc.terminate()


if __name__ == "__main__":
    main()
