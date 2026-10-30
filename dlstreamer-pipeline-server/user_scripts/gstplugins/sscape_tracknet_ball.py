# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Fill missing basketball detections with TrackNet heatmap peaks.

When YOLO provides a basketball box, its size is remembered and used as-is.
When YOLO misses, TrackNet predicts a center from the last three BGR frames and
a square bbox is published using the **last detected size** (never stretched by
the tracker). After `max-miss` consecutive TrackNet-only frames, filling stops
until YOLO sees the ball again.
"""

from __future__ import annotations

import json
import os
from collections import deque

import cv2
import numpy as np

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

from gstgva.video_frame import VideoFrame

from sscape_gst_log import GstCategoryLogger  # noqa: E402

_GST_LOG = GstCategoryLogger(
  "sscape_tracknet_ball",
  "SceneScape TrackNet basketball fill element",
)


class SscapeTracknetBall(GstBase.BaseTransform):
  """Inject TrackNet basketball ROI into GVA JSON when YOLO misses."""

  __gstmetadata__ = (
    "SceneScape TrackNet Ball Fill",
    "Filter/Metadata/Video",
    "Fill missing basketball detections from a TrackNet OpenVINO heatmap",
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
    "model": (
      str,
      "TrackNet OpenVINO XML",
      "Path to tracknet_basketball.xml",
      None,
      GObject.ParamFlags.READWRITE,
    ),
    "device": (
      str,
      "OpenVINO device",
      "Inference device (GPU or CPU).",
      "GPU",
      GObject.ParamFlags.READWRITE,
    ),
    "threshold": (
      float,
      "Heatmap peak threshold",
      "Minimum sigmoid peak to accept a TrackNet ball center.",
      0.0, 1.0, 0.35,
      GObject.ParamFlags.READWRITE,
    ),
    "ball-label": (
      str,
      "Ball label",
      "Detection label to match / inject.",
      "basketball",
      GObject.ParamFlags.READWRITE,
    ),
    "max-miss": (
      int,
      "Max TrackNet-only frames",
      "Stop filling after this many consecutive frames without YOLO.",
      1, 120, 12,
      GObject.ParamFlags.READWRITE,
    ),
    "default-side": (
      float,
      "Default bbox side (px)",
      "Used only until the first YOLO basketball box is seen.",
      8.0, 512.0, 64.0,
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self._log = _GST_LOG
    self._model_path = None
    self._device = "GPU"
    self._threshold = 0.35
    self._ball_label = "basketball"
    self._max_miss = 12
    self._default_side = 64.0
    self._compiled = None
    self._in_h = 288
    self._in_w = 512
    self._frames = deque(maxlen=3)
    self._last_side = None
    self._miss = 0
    self._sink_caps = None

  def do_get_property(self, prop):
    if prop.name == "model":
      return self._model_path
    if prop.name == "device":
      return self._device
    if prop.name == "threshold":
      return self._threshold
    if prop.name == "ball-label":
      return self._ball_label
    if prop.name == "max-miss":
      return self._max_miss
    if prop.name == "default-side":
      return self._default_side
    raise AttributeError(f"unknown property {prop.name}")

  def do_set_property(self, prop, value):
    if prop.name == "model":
      self._model_path = value
      self._compiled = None
    elif prop.name == "device":
      self._device = value or "GPU"
      self._compiled = None
    elif prop.name == "threshold":
      self._threshold = float(value)
    elif prop.name == "ball-label":
      self._ball_label = value or "basketball"
    elif prop.name == "max-miss":
      self._max_miss = int(value)
    elif prop.name == "default-side":
      self._default_side = float(value)
    else:
      raise AttributeError(f"unknown property {prop.name}")

  def do_set_caps(self, incaps, _outcaps):
    self._sink_caps = incaps
    return True

  def _ensure_model(self):
    if self._compiled is not None:
      return True
    if not self._model_path or not os.path.isfile(self._model_path):
      self._log.warning(f"TrackNet model missing: {self._model_path}")
      return False
    try:
      from openvino import Core
      core = Core()
      device = self._device if self._device in core.available_devices else "CPU"
      model = core.read_model(self._model_path)
      self._compiled = core.compile_model(model, device)
      shape = list(model.input(0).partial_shape)
      # [N,C,H,W]
      if len(shape) == 4 and shape[2].is_static and shape[3].is_static:
        self._in_h = int(shape[2].get_length())
        self._in_w = int(shape[3].get_length())
      meta = os.path.join(os.path.dirname(self._model_path), "metadata.json")
      if os.path.isfile(meta):
        with open(meta, encoding="utf-8") as fh:
          data = json.load(fh)
        self._in_h = int(data.get("height", self._in_h))
        self._in_w = int(data.get("width", self._in_w))
      self._log.info(
        f"Loaded TrackNet {self._model_path} on {device} "
        f"({self._in_w}x{self._in_h})"
      )
      return True
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to load TrackNet model")
      return False

  @staticmethod
  def _frame_bgr(buffer, caps):
    frame = VideoFrame(buffer, caps=caps)
    with frame.data() as mat:
      img = np.array(mat, copy=True)
    # Expect BGR from upstream videoconvert.
    if img.ndim == 3 and img.shape[2] == 4:
      img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img, frame

  @staticmethod
  def _iter_messages(frame):
    for msg in frame.messages():
      try:
        data = json.loads(msg)
      except (TypeError, json.JSONDecodeError):
        continue
      if isinstance(data, dict):
        yield msg, data

  def _find_ball(self, objects):
    balls = []
    for det in objects or []:
      label = (det.get("detection") or {}).get("label")
      if label is None:
        label = det.get("label")
      if label != self._ball_label:
        continue
      w = float(det.get("w") or 0)
      h = float(det.get("h") or 0)
      if w <= 1 or h <= 1:
        continue
      balls.append(det)
    return balls

  def _predict_center(self, fh, fw):
    if len(self._frames) < 3 or self._compiled is None:
      return None, 0.0
    rgbs = []
    for bgr in self._frames:
      rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
      rgb = cv2.resize(rgb, (self._in_w, self._in_h), interpolation=cv2.INTER_AREA)
      rgbs.append(rgb.astype(np.float32) / 255.0)
    stacked = np.concatenate(rgbs, axis=2)
    tensor = np.transpose(stacked, (2, 0, 1))[None, ...]
    out = self._compiled([tensor])[self._compiled.output(0)]
    heat = np.array(out)[0, 0]
    # logits → sigmoid if outside [0,1]
    if heat.min() < 0.0 or heat.max() > 1.0:
      heat = 1.0 / (1.0 + np.exp(-np.clip(heat, -20, 20)))
    peak = float(heat.max())
    if peak < self._threshold:
      return None, peak
    iy, ix = np.unravel_index(int(np.argmax(heat)), heat.shape)
    cx = (ix + 0.5) * (fw / float(self._in_w))
    cy = (iy + 0.5) * (fh / float(self._in_h))
    return (cx, cy), peak

  def do_transform_ip(self, buffer):
    if not self._ensure_model():
      return Gst.FlowReturn.OK
    try:
      img, frame = self._frame_bgr(buffer, self._sink_caps)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to map frame")
      return Gst.FlowReturn.OK

    self._frames.append(img)
    fh, fw = img.shape[:2]

    messages = list(self._iter_messages(frame))
    if not messages:
      return Gst.FlowReturn.OK

    # Prefer the richest objects payload (gvametaconvert).
    target_msg = None
    target_data = None
    for msg, data in messages:
      if "objects" in data:
        target_msg = msg
        target_data = data
    if target_data is None:
      return Gst.FlowReturn.OK

    objects = list(target_data.get("objects") or [])
    balls = self._find_ball(objects)
    if balls:
      # YOLO hit: remember size, reset miss streak; leave boxes untouched.
      w = float(balls[0].get("w") or 0)
      h = float(balls[0].get("h") or 0)
      self._last_side = max(w, h)
      self._miss = 0
      return Gst.FlowReturn.OK

    self._miss += 1
    if self._miss > self._max_miss:
      return Gst.FlowReturn.OK

    center, peak = self._predict_center(fh, fw)
    if center is None:
      return Gst.FlowReturn.OK

    side = float(self._last_side or self._default_side)
    cx, cy = center
    x = max(0.0, cx - side / 2.0)
    y = max(0.0, cy - side / 2.0)
    w = min(side, fw - x)
    h = min(side, fh - y)
    if w < 4 or h < 4:
      return Gst.FlowReturn.OK

    objects.append({
      "x": x,
      "y": y,
      "w": w,
      "h": h,
      "detection": {
        "label": self._ball_label,
        "label_id": 1,
        "confidence": float(peak),
      },
      "id": 1,
    })
    target_data["objects"] = objects

    # Replace JSON message on the buffer.
    try:
      frame.remove_message(target_msg)
    except Exception:  # pylint: disable=broad-except
      pass
    frame.add_message(json.dumps(target_data))
    self._log.debug(
      f"TrackNet fill ball peak={peak:.3f} side={side:.1f} miss={self._miss}"
    )
    return Gst.FlowReturn.OK


GObject.type_register(SscapeTracknetBall)
__gstelementfactory__ = (
  "sscape_tracknet_ball",
  Gst.Rank.NONE,
  SscapeTracknetBall,
)
