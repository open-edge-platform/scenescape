# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SceneScape demo GStreamer element that simulates a moving drone camera.

Warps each decoded BGR frame with the deterministic flight profile from
sample_data/drone_sim/drone_cam_sim.py (gimbal yaw/pitch/roll + zoom around
the original camera's optical center) and attaches the matching
external-source pose, camera mount, and virtual intrinsics as GstGVAJSONMeta
for the downstream sscape_external_source_publish element.

Place before gvadetect, e.g.:
  ... ! sscape_drone_motion_sim config=... ! gvadetect ...
"""

import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

import cv2
from gstgva.video_frame import VideoFrame

DEFAULT_CONFIG = "/home/dronesim/drone_sim_config.json"
DRONE_SIM_META_KEY = "drone_sim"

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("sscape_drone_sim")


def _load_simulator(config_path: str):
  """Import DroneCamSimulator from the directory holding the config file."""
  config = Path(config_path)
  module_dir = str(config.resolve().parent)
  if module_dir not in sys.path:
    sys.path.insert(0, module_dir)
  from drone_cam_sim import DroneCamSimulator  # pylint: disable=import-outside-toplevel
  return DroneCamSimulator.from_config_file(config)


class DroneMotionSim(GstBase.BaseTransform):
  """Warp frames into a simulated drone view and attach the matching pose."""

  __gstmetadata__ = (
    "SceneScape Drone Motion Simulator",
    "Filter/Effect/Video",
    "Simulate a moving drone camera from a fixed camera stream and attach "
    "the matching external-source pose, mount, and intrinsics as GVA JSON",
    "Intel SceneScape",
  )

  __gsttemplates__ = (
    Gst.PadTemplate.new(
      "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS,
      Gst.Caps.from_string("video/x-raw,format=BGR"),
    ),
    Gst.PadTemplate.new(
      "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS,
      Gst.Caps.from_string("video/x-raw,format=BGR"),
    ),
  )

  __gproperties__ = {
    "config": (
      str,
      "Simulation config file",
      "Path to the drone simulation JSON configuration "
      "(see sample_data/drone_sim/drone_sim_config.json).",
      DEFAULT_CONFIG,
      GObject.ParamFlags.READWRITE,
    ),
    "show-hud": (
      bool,
      "Show HUD overlay",
      "Draw the current yaw/pitch/roll/zoom onto each warped frame "
      "(demo visualization only; the overlay is seen by the detector).",
      False,
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = _LOG
    self._config_path: str = DEFAULT_CONFIG
    self._show_hud: bool = False
    self._simulator = None
    self._sink_caps: Optional[Gst.Caps] = None

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    if prop.name == "config":
      return self._config_path
    if prop.name == "show-hud":
      return self._show_hud
    raise AttributeError(f"Unknown property {prop.name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    if prop.name == "config":
      self._config_path = value or DEFAULT_CONFIG
    elif prop.name == "show-hud":
      self._show_hud = bool(value)
    else:
      raise AttributeError(f"Unknown property {prop.name}")

  # ------------------------------------------------------------------
  # BaseTransform overrides
  # ------------------------------------------------------------------

  def do_start(self):  # pylint: disable=arguments-differ
    try:
      self._simulator = _load_simulator(self._config_path)
    except Exception:  # pylint: disable=broad-except
      self._log.exception(f"Failed to load drone simulation from {self._config_path}")
      return False
    self._log.info(
      f"Drone simulation loaded: source_id={self._simulator.source_id} "
      f"camera={self._simulator.camera_id} period={self._simulator.period_s}s"
    )
    return True

  def do_set_caps(self, incaps, _outcaps):  # pylint: disable=arguments-differ
    self._sink_caps = incaps
    structure = incaps.get_structure(0)
    size = (structure.get_value("width"), structure.get_value("height"))
    if self._simulator and tuple(self._simulator.resolution) != size:
      self._log.error(
        f"Stream resolution {size} does not match simulation config "
        f"resolution {tuple(self._simulator.resolution)}"
      )
      return False
    return True

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    try:
      self._process(buffer)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to apply drone motion simulation")
    return Gst.FlowReturn.OK

  # ------------------------------------------------------------------
  # Core logic
  # ------------------------------------------------------------------

  def _frame_time(self, frame: VideoFrame) -> float:
    """Frame acquisition time in epoch seconds.

    Uses the post-decode wall clock; if Scenescape's optional
    sscape_timestamp_capture element is placed upstream, its NTP-corrected
    per-frame timestamp is preferred. Either way the same instant drives the
    warp and the attached pose, so they always match.
    """
    for message in frame.messages():
      try:
        timestamp = json.loads(message).get("timestamp_for_next_block")
      except (ValueError, AttributeError):
        continue
      if isinstance(timestamp, (int, float)):
        return float(timestamp)
    return time.time()

  def _draw_hud(self, image, time_s: float) -> None:
    state = self._simulator.state(time_s)
    text = (f"drone sim yaw={math.degrees(state['yaw']):+5.2f} "
            f"pitch={math.degrees(state['pitch']):+5.2f} "
            f"roll={math.degrees(state['roll']):+5.2f} zoom={state['zoom']:.2f}")
    cv2.putText(image, text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

  def _process(self, buffer: Gst.Buffer) -> None:
    frame = VideoFrame(buffer, caps=self._sink_caps)
    time_s = self._frame_time(frame)

    with frame.data(Gst.MapFlags.READ | Gst.MapFlags.WRITE) as image:
      warped = self._simulator.warp_frame(image, time_s)
      if self._show_hud:
        self._draw_hud(warped, time_s)
      image[:] = warped

    payload = json.dumps({
      DRONE_SIM_META_KEY: {
        "source_id": self._simulator.source_id,
        "camera_id": self._simulator.camera_id,
        "sim_time": time_s,
        "pose": self._simulator.body_pose(time_s),
        "mount": self._simulator.camera_mount(),
        "intrinsics": self._simulator.virtual_intrinsics(time_s),
      },
    })
    frame.add_message(payload)
    self._log.debug(f"warped frame at t={time_s:.3f}")


GObject.type_register(DroneMotionSim)
__gstelementfactory__ = (
  "sscape_drone_motion_sim",
  Gst.Rank.NONE,
  DroneMotionSim,
)
