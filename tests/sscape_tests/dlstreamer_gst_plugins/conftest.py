# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test bootstrap for dlstreamer-pipeline-server/user_scripts/gstplugins.

The GstBase-based elements under test are normally only importable inside the
DLStreamer Pipeline Server container, which ships a full PyGObject/GStreamer
runtime. For host-side unit testing, minimal stand-ins for the `gi`,
`gi.repository` (Gst/GstBase/GObject) and `gstgva` modules are installed
before the module under test is imported, so its pure-Python logic (FPS
smoothing, NTP offset handling, timestamp formatting, property get/set) can
be exercised without a real GStreamer installation.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_gstplugins_src = (
  Path(__file__).resolve().parents[3] / "dlstreamer-pipeline-server" / "user_scripts" / "gstplugins"
)
if str(_gstplugins_src) not in sys.path:
  sys.path.insert(0, str(_gstplugins_src))


class FakeBaseTransform:
  """Minimal, subclassable stand-in for GstBase.BaseTransform.

  A MagicMock *instance* cannot be used as a base class, so real elements
  need a real (if trivial) class here to subclass and call super().__init__()
  and the setters they rely on.
  """

  def __init__(self, *args, **kwargs):
    pass

  def set_in_place(self, value):
    pass

  def set_passthrough(self, value):
    pass


class FakeVideoFrame:
  """Stand-in for gstgva.video_frame.VideoFrame; records add_message() calls."""

  def __init__(self, buffer, caps=None):
    self.buffer = buffer
    self.caps = caps
    self.messages = []

  def add_message(self, payload):
    self.messages.append(payload)


def _install_fake_gi():
  if getattr(sys.modules.get("gi"), "_sscape_fake", False):
    return

  gi_module = types.ModuleType("gi")
  gi_module._sscape_fake = True
  gi_module.require_version = MagicMock()

  # Gst/GstBase/GObject: MagicMock auto-vivifies attributes and calls
  # (Gst.Caps.new_any(), Gst.PadTemplate.new(...), GObject.type_register(...),
  # etc.) so only the pieces that need real, deterministic values or need to
  # be subclassable are overridden explicitly below.
  gst_module = MagicMock(name="Gst")
  gst_module.FlowReturn.OK = "FLOW_OK"

  gstbase_module = MagicMock(name="GstBase")
  gstbase_module.BaseTransform = FakeBaseTransform

  gobject_module = MagicMock(name="GObject")
  gobject_module.ParamFlags.READWRITE = "READWRITE"

  repository_module = types.ModuleType("gi.repository")
  repository_module.Gst = gst_module
  repository_module.GstBase = gstbase_module
  repository_module.GObject = gobject_module
  gi_module.repository = repository_module

  sys.modules["gi"] = gi_module
  sys.modules["gi.repository"] = repository_module

  gstgva_module = types.ModuleType("gstgva")
  video_frame_module = types.ModuleType("gstgva.video_frame")
  video_frame_module.VideoFrame = FakeVideoFrame
  gstgva_module.video_frame = video_frame_module

  sys.modules["gstgva"] = gstgva_module
  sys.modules["gstgva.video_frame"] = video_frame_module


_install_fake_gi()
