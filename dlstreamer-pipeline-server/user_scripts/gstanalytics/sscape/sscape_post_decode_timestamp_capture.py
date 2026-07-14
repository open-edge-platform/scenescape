# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import time
from datetime import datetime
from uuid import getnode as get_mac
from typing import Optional

import ntplib
from gi.repository import Gst
from gstgva.video_frame import VideoFrame
from pytz import timezone

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
gi.require_version("GstAnalytics", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
    Gst,
    GstBase,
    GObject,
    GLib,
    GstAnalytics,
)

Gst.init_python()

ROOT_CA = os.environ.get("ROOT_CA", "/run/secrets/certs/scenescape-ca.pem")
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
TIMEZONE = "UTC"

class AgeLogger(GstBase.BaseTransform):
  """DLStreamer custom element to log detected ages from classification metadata."""

    # Age-group labels produced by the fairface age model, e.g. "0-2", "3-9",
    # "20-29", "more than 70". Used to skip ClsMtd produced by other classifier
    # stages in the same pipeline (e.g. gender: "Male"/"Female").
    _AGE_LABEL_RE = re.compile(r"^(\d+-\d+|more than \d+)$")

    __gstmetadata__ = (
        "GVA Age Logger Python",
        "Transform",
        "Log detected ages from classification metadata to a file",
        "Intel DLStreamer",
    )

    __gsttemplates__ = (
        Gst.PadTemplate.new(
            "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        ),
        Gst.PadTemplate.new(
            "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        ),
    )

    # Element properties: default values and setters/getters
    _log_file_path = os.path.join(tempfile.gettempdir(), "age_log.txt")

    @GObject.Property(type=str)
    def log_file_path(self):
        "Path to the log file for age values."
        return self._log_file_path

    @log_file_path.setter
    def log_file_path(self, value):
        self._log_file_path = value

    def __init__(self):
        super().__init__()
        self._log_file = None

    def do_start(self):  # pylint: disable=arguments-differ
        """Open log file when element starts."""
        self._log_file = open(  # pylint: disable=consider-using-with
            self._log_file_path, "a", encoding="utf-8"
        )
        return True

    def do_stop(self):  # pylint: disable=arguments-differ
        """Close log file when element stops."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        return True

    def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
        """Read classification metadata and log age values to file."""
        rmeta = GstAnalytics.buffer_get_analytics_relation_meta(buffer)
        if not rmeta:
            return Gst.FlowReturn.OK

        for mtd in rmeta:
            if isinstance(mtd, GstAnalytics.ClsMtd):
                # Pick the top-1 class only (highest confidence) to avoid
                # logging every candidate label for the same ROI.
                if mtd.get_length() == 0:
                    continue
                quark = mtd.get_quark(0)
                if not quark:
                    continue
                label = GLib.quark_to_string(quark)
                # The fairface age model emits age-group labels such as
                # "0-2", "3-9", ..., "20-29", "more than 70". Filter out
                # ClsMtd from other classifier stages (e.g. gender) by
                # matching the expected age-group format.
                if label and self._AGE_LABEL_RE.match(label):
                    self._log_file.write(label + "\n")

        return Gst.FlowReturn.OK


GObject.type_register(AgeLogger)
__gstelementfactory__ = ("sscape_timestamp_capture", Gst.Rank.NONE, AgeLogger)

class PostDecodeTimestampCapture:
  def __init__(self, ntpServer=None, useFrameNtpTimestamp=False):
    self.log = logging.getLogger('SSCAPE_ADAPTER')
    self.log.setLevel(logging.INFO)
    self.ntpClient = ntplib.NTPClient()
    self.ntpServer = ntpServer
    self.use_frame_ntp_timestamp = useFrameNtpTimestamp
    self.lastTimeSync = None
    self.timeOffset = 0
    self.timestamp_for_next_block = None
    self.fps = 5.0
    self.fps_alpha = 0.75 # for weighted average
    self.last_calculated_fps_ts = None
    self.fps_calc_interval = 1 # calculate fps every 1s
    self.frame_cnt = 0
    self._ntp_caps = Gst.Caps.from_string("timestamp/x-ntp")
    if not self._ntp_caps:
      self.log.error("Failed to create caps for timestamp/x-ntp")
      return None

  def _extract_ntp_timestamp(self, frame: VideoFrame) -> Optional[str]:
    """Extract the NTP timestamp embedded in the video frame's GStreamer reference metadata.

    Retrieves the NTP reference timestamp attached by rtspsrc (via
    add-reference-timestamp-meta=true) and converts it to a UTC ISO 8601
    string. Returns None when the metadata is absent or cannot be parsed,
    allowing the caller to fall back to an alternative timestamp source.

    Args:
        frame: GVA VideoFrame whose underlying GstBuffer may carry
               a GstReferenceTimestampMeta with caps matching _NTP_CAPS ("timestamp/x-ntp").

    Returns:
        str: UTC ISO 8601 timestamp string (e.g. "2026-05-13T06:35:01.123Z"),
             or None if the NTP metadata is missing or invalid.
    """
    # gstgva.VideoFrame has no public API to retrieve the underlying Gst.Buffer.
    # The buffer is stored only as the name-mangled private attribute __buffer.
    # getattr with a None default ensures graceful fallback if the internal name
    # changes in a future gstgva release.
    gst_buffer = getattr(frame, "_VideoFrame__buffer", None)

    if not gst_buffer:
      self.log.debug("No GstBuffer found in frame, using fallback timestamp")
      return None

    if not self._ntp_caps:
      return None

    ntp_meta = gst_buffer.get_reference_timestamp_meta(self._ntp_caps)
    if not ntp_meta:
      self.log.debug("No NTP timestamp metadata found, using fallback timestamp")
      return None

    # Convert NTP timestamp (nanoseconds) to system time
    ntp_timestamp_seconds = ntp_meta.timestamp / 1e9
    system_timestamp = ntplib.ntp_to_system_time(ntp_timestamp_seconds)
    ntp_datetime_utc = datetime.fromtimestamp(system_timestamp)
    ntp_datetime_local = ntp_datetime_utc.astimezone(timezone(TIMEZONE))
    self.log.debug(f"NTP={ntp_datetime_utc}, delta={time.time() - system_timestamp}, raw_ts={ntp_timestamp_seconds}")
    return f"{ntp_datetime_local.strftime(DATETIME_FORMAT)[:-3]}Z"

  def processFrame(self, frame: VideoFrame) -> bool:
    now = time.time()
    self.frame_cnt += 1
    if not self.last_calculated_fps_ts:
      self.last_calculated_fps_ts = now
    if (now - self.last_calculated_fps_ts) > self.fps_calc_interval:
      self.fps = self.fps * self.fps_alpha + (1 - self.fps_alpha) * (self.frame_cnt / (now - self.last_calculated_fps_ts))
      self.last_calculated_fps_ts = now
      self.frame_cnt = 0

    if self.ntpServer:
      # if ntpServer is available, check if it is time to recalibrate
      if not self.lastTimeSync or now - self.lastTimeSync > 1000 :
        response = self.ntpClient.request(host=self.ntpServer, port=123)
        self.timeOffset = response.offset
        self.lastTimeSync = now

    now += self.timeOffset
    self.timestamp_for_next_block = now

    postdecode_timestamp = f"{datetime.fromtimestamp(now, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z"
    if self.use_frame_ntp_timestamp:
      extracted_ntp_timestamp = self._extract_ntp_timestamp(frame)
      if extracted_ntp_timestamp:
        postdecode_timestamp = extracted_ntp_timestamp

    frame.add_message(json.dumps({
      'postdecode_timestamp': postdecode_timestamp,
      'timestamp_for_next_block': now,
      'fps': self.fps
    }))
    return True