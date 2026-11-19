# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SceneScape custom GStreamer element that detects AprilTags in decoded frames."""

from typing import Optional

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

from sscape_gst_log import GstCategoryLogger  # noqa: E402  pylint: disable=wrong-import-position


# Frame formats the element knows how to reduce to single-channel grayscale.
GRAY_CONVERSION_MAP = {
  "GST_VIDEO_FORMAT_BGR": cv2.COLOR_BGR2GRAY,
  "GST_VIDEO_FORMAT_BGRA": cv2.COLOR_BGRA2GRAY,
  "GST_VIDEO_FORMAT_BGRx": cv2.COLOR_BGRA2GRAY,
  "GST_VIDEO_FORMAT_RGB": cv2.COLOR_RGB2GRAY,
  "GST_VIDEO_FORMAT_RGBA": cv2.COLOR_RGBA2GRAY,
  "GST_VIDEO_FORMAT_RGBx": cv2.COLOR_RGBA2GRAY,
  "GST_VIDEO_FORMAT_NV12": cv2.COLOR_YUV2GRAY_NV12,
  "GST_VIDEO_FORMAT_I420": cv2.COLOR_YUV2GRAY_I420,
}

_GST_LOG = GstCategoryLogger(
  "sscape_apriltag_detector",
  "SceneScape AprilTag detection element",
)

# cv2.aruco's predefined dictionaries that decode AprilTag families.
APRILTAG_DICTIONARIES = {
  "tag16h5": cv2.aruco.DICT_APRILTAG_16h5,
  "tag25h9": cv2.aruco.DICT_APRILTAG_25h9,
  "tag36h10": cv2.aruco.DICT_APRILTAG_36h10,
  "tag36h11": cv2.aruco.DICT_APRILTAG_36h11,
}



class SscapeApriltagDetect(GstBase.BaseTransform):
  """Detect AprilTags and attach them as GVA regions of interest."""

  __gstmetadata__ = (
    "SceneScape AprilTag Detector",
    "Filter/Analyzer/Video",
    "Detect AprilTags and publish them as GVA regions of interest",
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
    "tag-family": (
      str,
      "AprilTag family",
      "AprilTag family to detect, one of: "
      "\"tag16h5\", \"tag25h9\", \"tag36h10\", \"tag36h11\". "
      "cv2.aruco decodes a single family per detector.",
      "tag36h11",
      GObject.ParamFlags.READWRITE,
    ),
    "quad-decimate": (
      float,
      "Quad decimation factor",
      "Downsample factor applied before quad detection. Higher is faster "
      "but misses small tags. 1.0 disables decimation.",
      1.0, 8.0, 1.0,
      GObject.ParamFlags.READWRITE,
    ),
    "category": (
      str,
      "Detection category",
      "GVA region category assigned to every detected tag. All tags share "
      "this one category; the tag's own id/family ride along as tensor "
      "attributes so the controller tracks AprilTags with a single tracker.",
      "apriltag",
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = _GST_LOG

    # Properties (defaults)
    self._tag_family: str = "tag36h11"
    self._quad_decimate: float = 1.0
    self._category: str = "apriltag"

    # Runtime state
    self._detector = None
    self._sink_caps: Optional[Gst.Caps] = None
    self._unsupported_format_logged: bool = False

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "tag-family":
      return self._tag_family
    if name == "quad-decimate":
      return self._quad_decimate
    if name == "category":
      return self._category
    raise AttributeError(f"Unknown property {name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    name = prop.name
    if name == "tag-family":
      self._tag_family = value or "tag36h11"
    elif name == "quad-decimate":
      self._quad_decimate = float(value)
    elif name == "category":
      self._category = value or "apriltag"
    else:
      raise AttributeError(f"Unknown property {name}")
    # Detector caches its construction args; rebuild on the next buffer.
    self._detector = None

  def do_set_caps(self, incaps, _outcaps):  # pylint: disable=arguments-differ
    self._sink_caps = incaps
    return True

  def do_stop(self):  # pylint: disable=arguments-differ
    self._detector = None
    return True

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    try:
      self._detect_and_attach(buffer)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("AprilTag detection failed")
    return Gst.FlowReturn.OK

  def _ensure_detector(self):
    if self._detector is not None:
      return self._detector
    dict_id = APRILTAG_DICTIONARIES.get(self._tag_family)
    if dict_id is None:
      raise ValueError(f"Unsupported AprilTag family '{self._tag_family}'")

    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
    params.aprilTagQuadDecimate = self._quad_decimate
    self._detector = cv2.aruco.ArucoDetector(
      cv2.aruco.getPredefinedDictionary(dict_id), params
    )
    self._log.info(
      f"AprilTag detector ready family={self._tag_family} "
      f"quad_decimate={self._quad_decimate}"
    )
    return self._detector

  def _to_grayscale(self, raw_frame, video_meta) -> Optional[np.ndarray]:
    if raw_frame.ndim == 2:
      gray = raw_frame
    else:
      video_format = video_meta.format.value_name
      conversion = GRAY_CONVERSION_MAP.get(video_format)
      if conversion is None:
        if not self._unsupported_format_logged:
          self._log.warning(
            f"Unsupported frame format {video_format} for AprilTag detection"
          )
          self._unsupported_format_logged = True
        return None
      gray = cv2.cvtColor(raw_frame, conversion)
    # cv2.aruco requires a contiguous uint8 buffer it can borrow.
    return np.ascontiguousarray(gray, dtype=np.uint8)

  def _detect_and_attach(self, buffer: Gst.Buffer) -> None:
    frame = VideoFrame(buffer, caps=self._sink_caps)
    with frame.data() as img:
      gray = self._to_grayscale(img, frame.video_meta())
    if gray is None:
      return

    corners_list, ids, _ = self._ensure_detector().detectMarkers(gray)
    height, width = gray.shape[:2]
    attached = 0

    for marker_corners, marker_id in zip(corners_list, [] if ids is None else ids.flatten()):
      corners = marker_corners.reshape(-1, 2)
      x0, y0 = corners.min(axis=0)
      x1, y1 = corners.max(axis=0)
      # Clamp to the frame; GVA rejects regions that fall outside it.
      x = int(max(0, min(x0, width - 1)))
      y = int(max(0, min(y0, height - 1)))
      w = int(max(1, min(x1, width) - x))
      h = int(max(1, min(y1, height) - y))
      # Every tag shares one category; extra_params carries its identity
      # through gvametaconvert instead of a separately-built GVA tensor.
      frame.add_region(
        x, y, w, h, self._category, 1.0, False,
        extra_params={"tag_id": int(marker_id), "tag_family": self._tag_family},
      )
      attached += 1

    if attached:
      self._log.debug(f"attached {attached} AprilTag region(s)")


GObject.type_register(SscapeApriltagDetect)
__gstelementfactory__ = (
  "sscape_apriltag_detector",
  Gst.Rank.NONE,
  SscapeApriltagDetect,
)
