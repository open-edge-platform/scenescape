# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SceneScape GStreamer element that stands in for an inference element: it
attaches recorded detections to each video frame as GVA regions of interest,
so downstream gvametaconvert and sscape_post_inference_data_publish publish
them as if a detection model had produced them.
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

from gstgva.video_frame import VideoFrame

from detection_timeline import (  # noqa: E402  pylint: disable=wrong-import-position
  SYNC_MODES,
  DetectionTimeline,
)
from sscape_gst_log import (  # noqa: E402  pylint: disable=wrong-import-position
  GstCategoryLogger,
)

# `GST_DEBUG=sscape_detection_replay:5` logs the record used for each frame.
_GST_LOG = GstCategoryLogger(
  "sscape_detection_replay",
  "SceneScape recorded detection replay element",
)


class SscapeDetectionReplay(GstBase.BaseTransform):
  """Attach recorded detections to video frames in place of inference."""

  __gstmetadata__ = (
    "SceneScape Detection Replay",
    "Filter/Metadata/Video",
    "Attach recorded detections as GVA regions of interest",
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
    "metadata": (
      str,
      "Detection metadata",
      "JSON Lines file with one SceneScape camera message per frame.",
      None,
      GObject.ParamFlags.READWRITE,
    ),
    "sync-mode": (
      str,
      "Sync mode",
      "How video frames select records: 'time' (first record at or after "
      "the frame's stream time) or 'frame' (record at the frame's position "
      "in the file, counted from the start of each loop).",
      "time",
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)
    self._log = _GST_LOG
    self._metadata = None
    self._sync_mode = "time"
    self._timeline = None
    self._caps = None
    self._frame = 0

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    if prop.name == "metadata":
      return self._metadata
    if prop.name == "sync-mode":
      return self._sync_mode
    raise AttributeError(f"Unknown property {prop.name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    if prop.name == "metadata":
      self._metadata = value
    elif prop.name == "sync-mode":
      if value not in SYNC_MODES:
        raise ValueError(f"Unknown sync-mode '{value}'. Valid: {SYNC_MODES}")
      self._sync_mode = value
    else:
      raise AttributeError(f"Unknown property {prop.name}")

  def do_start(self):  # pylint: disable=arguments-differ
    if not self._metadata:
      self._log.error("The 'metadata' property is not set")
      return False
    try:
      self._timeline = DetectionTimeline.from_jsonl(self._metadata)
    except (OSError, ValueError) as error:
      self._log.error(f"Cannot load detection metadata: {error}")
      return False
    self._log.info(f"Loaded {len(self._timeline)} records from {self._metadata}")
    self._frame = 0
    return True

  def do_set_caps(self, incaps, _outcaps):  # pylint: disable=arguments-differ
    self._caps = incaps
    return True

  def do_sink_event(self, event):  # pylint: disable=arguments-differ
    # A new segment starts the file again (initially and on each loop).
    if event.type == Gst.EventType.SEGMENT:
      self._frame = 0
    return GstBase.BaseTransform.do_sink_event(self, event)

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    frame_index = self._frame
    self._frame += 1
    # Stream time restarts at 0 on every loop of the file.
    stream_time = self.segment.to_stream_time(Gst.Format.TIME, buffer.pts)
    has_time = stream_time != Gst.CLOCK_TIME_NONE
    # Only time mode needs a timestamp; frame mode looks up by buffer count.
    if not has_time and self._sync_mode == "time":
      return Gst.FlowReturn.OK
    seconds = stream_time / Gst.SECOND if has_time else 0.0
    detections = self._timeline.lookup(self._sync_mode, seconds, frame_index)
    if not detections:
      return Gst.FlowReturn.OK
    frame = VideoFrame(buffer, caps=self._caps)
    for det in detections:
      frame.add_region(det.x, det.y, det.width, det.height,
                       label=det.label, confidence=det.confidence)
    time_text = f"{seconds:.3f}s" if has_time else "n/a"
    self._log.debug(f"t={time_text} regions={len(detections)}")
    return Gst.FlowReturn.OK


GObject.type_register(SscapeDetectionReplay)
__gstelementfactory__ = (
  "sscape_detection_replay",
  Gst.Rank.NONE,
  SscapeDetectionReplay,
)
