# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test bootstrap for tools/detection_replay.

Puts the tool, its GStreamer elements and the SceneScape elements they import
on sys.path, and reuses the gi/gstgva stand-ins of the DL Streamer plugin
tests so the replay element can be unit tested without GStreamer.
"""

import sys
from pathlib import Path

from tests.sscape_tests.dlstreamer_gst_plugins.conftest import (
  FakeBaseTransform,
  _install_fake_gi,
)

_repo = Path(__file__).resolve().parents[3]
for _path in (
  _repo / "tools" / "detection_replay",
  _repo / "tools" / "detection_replay" / "gstplugins",
  _repo / "dlstreamer-pipeline-server" / "user_scripts" / "gstplugins",
):
  if str(_path) not in sys.path:
    sys.path.insert(0, str(_path))

_install_fake_gi()

# The shared stand-in has no sink event handling; the element chains up to it.
FakeBaseTransform.do_sink_event = lambda self, event: True
