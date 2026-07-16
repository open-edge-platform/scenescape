# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SceneScape custom GStreamer element that captures post-decode timestamps.
Designed to be used in a DLStreamer pipeline after a decoder element. It attaches post-decode timestamps and FPS metadata to each buffer, which can be consumed by downstream elements or applications.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

import ntplib
from pytz import timezone
from gstgva.video_frame import VideoFrame

Gst.init_python()

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
TIMEZONE = "UTC"
NTP_RESYNC_INTERVAL_S = 1000
NTP_CAPS_STRING = "timestamp/x-ntp"


class PostDecodeTimestampCapture(GstBase.BaseTransform):
  """Attach post-decode timestamp and FPS metadata to each buffer."""

  __gstmetadata__ = (
    "SceneScape Post-Decode Timestamp Capture",
    "Filter/Metadata/Video",
    "Capture post-decode timestamp and FPS; publish as GVA JSON message",
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
    "ntp-server": (
      str,
      "NTP server host",
      "Hostname of an NTP server used to periodically recompute the "
      "system-clock offset. Unset or empty disables NTP correction.",
      None,
      GObject.ParamFlags.READWRITE,
    ),
    "use-frame-ntp-timestamp": (
      bool,
      "Use frame NTP timestamp",
      "When true, use the NTP timestamp from GstReferenceTimestampMeta "
      "attached by rtspsrc (add-reference-timestamp-meta=true). If the "
      "meta is missing, fall back to post-decode system time.",
      False,
      GObject.ParamFlags.READWRITE,
    ),
    "fps-alpha": (
      float,
      "FPS smoothing factor",
      "Weight for the previous FPS estimate in the running average "
      "(0.0 = no smoothing, closer to 1.0 = heavier smoothing).",
      0.0, 1.0, 0.75,
      GObject.ParamFlags.READWRITE,
    ),
    "fps-calc-interval": (
      float,
      "FPS calculation interval (seconds)",
      "Minimum elapsed wall-clock time between FPS recomputations.",
      0.01, 60.0, 1.0,
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = logging.getLogger("SSCAPE_TS_CAPTURE")

    # Properties (defaults)
    self._ntp_server: Optional[str] = None
    self._use_frame_ntp: bool = False
    self._fps_alpha: float = 0.75
    self._fps_calc_interval: float = 1.0

    # Runtime state
    self._ntp_client = ntplib.NTPClient()
    self._last_time_sync: Optional[float] = None
    self._time_offset: float = 0.0

    self._fps: float = 5.0
    self._last_calc_ts: Optional[float] = None
    self._frame_cnt: int = 0

    self._sink_caps: Optional[Gst.Caps] = None
    self._ntp_caps = Gst.Caps.from_string(NTP_CAPS_STRING)
    if not self._ntp_caps:
      self._log.error("Failed to build caps for %s", NTP_CAPS_STRING)

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "ntp-server":
      return self._ntp_server
    if name == "use-frame-ntp-timestamp":
      return self._use_frame_ntp
    if name == "fps-alpha":
      return self._fps_alpha
    if name == "fps-calc-interval":
      return self._fps_calc_interval
    raise AttributeError(f"Unknown property {name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "ntp-server":
      self._ntp_server = value or None
    elif name == "use-frame-ntp-timestamp":
      self._use_frame_ntp = bool(value)
    elif name == "fps-alpha":
      self._fps_alpha = float(value)
    elif name == "fps-calc-interval":
      self._fps_calc_interval = float(value)
    else:
      raise AttributeError(f"Unknown property {name}")

  # ------------------------------------------------------------------
  # BaseTransform overrides
  # ------------------------------------------------------------------

  def do_set_caps(self, incaps, outcaps):  # pylint: disable=arguments-differ
    self._sink_caps = incaps
    return True

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    try:
      self._attach_metadata(buffer)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to attach post-decode timestamp metadata")
    return Gst.FlowReturn.OK

  # ------------------------------------------------------------------
  # Core logic
  # ------------------------------------------------------------------

  def _extract_ntp_timestamp(self, buffer: Gst.Buffer) -> Optional[str]:
    """Read GstReferenceTimestampMeta with caps=timestamp/x-ntp."""
    if not self._ntp_caps:
      return None
    ntp_meta = buffer.get_reference_timestamp_meta(self._ntp_caps)
    if not ntp_meta:
      self._log.debug("No NTP reference-timestamp meta on buffer")
      return None
    ntp_seconds = ntp_meta.timestamp / 1e9
    system_ts = ntplib.ntp_to_system_time(ntp_seconds)
    dt_utc = datetime.fromtimestamp(system_ts)
    dt_local = dt_utc.astimezone(timezone(TIMEZONE))
    self._log.debug(
      "NTP=%s delta=%s raw=%s",
      dt_utc, time.time() - system_ts, ntp_seconds,
    )
    return f"{dt_local.strftime(DATETIME_FORMAT)[:-3]}Z"

  def _update_fps(self, now: float) -> None:
    self._frame_cnt += 1
    if self._last_calc_ts is None:
      self._last_calc_ts = now
      return
    elapsed = now - self._last_calc_ts
    if elapsed > self._fps_calc_interval:
      instant = self._frame_cnt / elapsed
      self._fps = (
        self._fps * self._fps_alpha
        + (1.0 - self._fps_alpha) * instant
      )
      self._last_calc_ts = now
      self._frame_cnt = 0

  def _maybe_sync_ntp(self, now: float) -> None:
    if not self._ntp_server:
      return
    if (
      self._last_time_sync is not None
      and now - self._last_time_sync <= NTP_RESYNC_INTERVAL_S
    ):
      return
    try:
      response = self._ntp_client.request(host=self._ntp_server, port=123)
      self._time_offset = response.offset
      self._last_time_sync = now
    except Exception as exc:  # pylint: disable=broad-except
      self._log.warning(
        "NTP sync with %s failed: %s", self._ntp_server, exc,
      )

  def _attach_metadata(self, buffer: Gst.Buffer) -> None:
    now = time.time()
    self._update_fps(now)
    self._maybe_sync_ntp(now)

    adjusted = now + self._time_offset
    postdecode_ts = (
      f"{datetime.fromtimestamp(adjusted, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z"
    )

    if self._use_frame_ntp:
      frame_ntp = self._extract_ntp_timestamp(buffer)
      if frame_ntp:
        postdecode_ts = frame_ntp

    payload = json.dumps({
      "postdecode_timestamp": postdecode_ts,
      "timestamp_for_next_block": adjusted,
      "fps": self._fps,
    })

    # Attach as GVA JSON message so downstream gvapython consumers
    frame = VideoFrame(buffer, caps=self._sink_caps)
    frame.add_message(payload)


GObject.type_register(PostDecodeTimestampCapture)
__gstelementfactory__ = (
  "sscape_timestamp_capture",
  Gst.Rank.NONE,
  PostDecodeTimestampCapture,
)
