# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests proving that PostDecodeTimestampCapture's own logic (FPS
smoothing, NTP offset handling, timestamp formatting, GObject property
plumbing) is testable on the host by stubbing out gi/GstBase/gstgva
(see conftest.py), without a real PyGObject/GStreamer installation and
without any production code changes.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sscape_post_decode_timestamp_capture import PostDecodeTimestampCapture
import sscape_post_decode_timestamp_capture as tsmod


def make_prop(name):
  return SimpleNamespace(name=name)


@pytest.fixture
def element():
  return PostDecodeTimestampCapture()


class TestProperties:

  def test_defaults(self, element):
    assert element.do_get_property(make_prop("ntp-server")) is None
    assert element.do_get_property(make_prop("use-frame-ntp-timestamp")) is False
    assert element.do_get_property(make_prop("timestamp-source")) == "timestamp_post_decode"
    assert element.do_get_property(make_prop("fps-alpha")) == 0.75
    assert element.do_get_property(make_prop("fps-calc-interval")) == 1.0

  def test_set_and_get_ntp_server(self, element):
    element.do_set_property(make_prop("ntp-server"), "ntpserv")
    assert element.do_get_property(make_prop("ntp-server")) == "ntpserv"

  def test_set_ntp_server_empty_string_becomes_none(self, element):
    element.do_set_property(make_prop("ntp-server"), "ntpserv")
    element.do_set_property(make_prop("ntp-server"), "")
    assert element.do_get_property(make_prop("ntp-server")) is None

  def test_set_and_get_use_frame_ntp_timestamp(self, element):
    element.do_set_property(make_prop("use-frame-ntp-timestamp"), True)
    assert element.do_get_property(make_prop("use-frame-ntp-timestamp")) is True
    assert element.do_get_property(make_prop("timestamp-source")) == "timestamp_rtcp"

  def test_timestamp_source_aliases_use_frame_ntp(self, element):
    element.do_set_property(make_prop("timestamp-source"), "timestamp_rtcp")
    assert element.do_get_property(make_prop("use-frame-ntp-timestamp")) is True
    element.do_set_property(make_prop("timestamp-source"), "late")
    assert element.do_get_property(make_prop("timestamp-source")) == "timestamp_post_decode"
    assert element.do_get_property(make_prop("use-frame-ntp-timestamp")) is False

  def test_set_and_get_fps_alpha_coerces_to_float(self, element):
    element.do_set_property(make_prop("fps-alpha"), "0.5")
    assert element.do_get_property(make_prop("fps-alpha")) == 0.5

  def test_set_and_get_fps_calc_interval(self, element):
    element.do_set_property(make_prop("fps-calc-interval"), 2.5)
    assert element.do_get_property(make_prop("fps-calc-interval")) == 2.5

  def test_get_unknown_property_raises(self, element):
    with pytest.raises(AttributeError):
      element.do_get_property(make_prop("does-not-exist"))

  def test_set_unknown_property_raises(self, element):
    with pytest.raises(AttributeError):
      element.do_set_property(make_prop("does-not-exist"), 1)


class TestFpsSmoothing:

  def test_first_call_seeds_timestamp_without_changing_fps(self, element):
    element._update_fps(100.0)
    assert element._last_calc_ts == 100.0
    assert element._fps == 5.0
    assert element._frame_cnt == 1

  def test_no_update_before_interval_elapses(self, element):
    element._update_fps(100.0)
    element._update_fps(100.5)  # 0.5s < default 1.0s interval
    assert element._fps == 5.0
    assert element._frame_cnt == 2

  def test_weighted_average_applied_after_interval(self, element):
    element._fps_alpha = 0.5
    element._fps_calc_interval = 1.0
    element._update_fps(100.0)     # seeds last_calc_ts
    element._update_fps(100.5)     # frame_cnt=2, elapsed=0.5, no update
    element._update_fps(101.5)     # elapsed=1.5 > interval -> recompute
    instantaneous = 3 / 1.5        # 3 frames counted over 1.5s
    expected = 5.0 * 0.5 + 0.5 * instantaneous
    assert element._fps == pytest.approx(expected)
    assert element._frame_cnt == 0
    assert element._last_calc_ts == 101.5


class TestNtpSync:

  def test_sync_skipped_when_no_server_configured(self, element):
    element._ntp_client = MagicMock()
    element._sync_ntp_if_needed(100.0)
    element._ntp_client.request.assert_not_called()

  def test_first_sync_sets_offset_and_timestamp(self, element):
    element._ntp_server = "ntpserv"
    element._ntp_client = MagicMock()
    element._ntp_client.request.return_value = SimpleNamespace(offset=1.25)

    element._sync_ntp_if_needed(100.0)

    element._ntp_client.request.assert_called_once_with(
      host="ntpserv", port=123, timeout=tsmod.NTP_REQUEST_TIMEOUT_S,
    )
    assert element._time_offset == 1.25
    assert element._last_time_sync == 100.0

  def test_resync_skipped_within_interval(self, element):
    element._ntp_server = "ntpserv"
    element._ntp_client = MagicMock()
    element._ntp_client.request.return_value = SimpleNamespace(offset=1.0)
    element._sync_ntp_if_needed(0.0)

    element._sync_ntp_if_needed(500.0)  # < NTP_RESYNC_INTERVAL_S (1000)

    element._ntp_client.request.assert_called_once()

  def test_resync_happens_after_interval_elapses(self, element):
    element._ntp_server = "ntpserv"
    element._ntp_client = MagicMock()
    element._ntp_client.request.return_value = SimpleNamespace(offset=1.0)
    element._sync_ntp_if_needed(0.0)

    element._sync_ntp_if_needed(1500.0)  # > NTP_RESYNC_INTERVAL_S (1000)

    assert element._ntp_client.request.call_count == 2

  def test_failed_sync_is_caught_and_leaves_offset_unchanged(self, element):
    element._ntp_server = "ntpserv"
    element._time_offset = 0.42
    element._ntp_client = MagicMock()
    element._ntp_client.request.side_effect = OSError("unreachable")

    element._sync_ntp_if_needed(100.0)  # must not raise

    assert element._time_offset == 0.42

  def test_failed_sync_is_throttled_like_a_successful_one(self, element):
    """A persistently unreachable NTP host must not incur a blocking network
    call on every buffer. `_last_time_sync` is recorded before the request,
    so subsequent calls within NTP_RESYNC_INTERVAL_S are skipped just as
    they would be after a successful sync."""
    element._ntp_server = "ntpserv"
    element._ntp_client = MagicMock()
    element._ntp_client.request.side_effect = OSError("unreachable")

    element._sync_ntp_if_needed(100.0)
    element._sync_ntp_if_needed(100.1)
    element._sync_ntp_if_needed(100.2)

    assert element._ntp_client.request.call_count == 1
    assert element._last_time_sync == 100.0

  def test_failed_sync_retries_only_after_interval_elapses(self, element):
    element._ntp_server = "ntpserv"
    element._ntp_client = MagicMock()
    element._ntp_client.request.side_effect = OSError("unreachable")

    element._sync_ntp_if_needed(0.0)
    element._sync_ntp_if_needed(1500.0)  # > NTP_RESYNC_INTERVAL_S (1000)

    assert element._ntp_client.request.call_count == 2

class TestExtractNtpTimestamp:

  def test_returns_none_when_ntp_caps_unavailable(self, element):
    element._ntp_caps = None
    assert element._extract_ntp_timestamp(MagicMock()) is None

  def test_returns_none_when_meta_missing(self, element):
    buffer = MagicMock()
    buffer.get_reference_timestamp_meta.return_value = None
    assert element._extract_ntp_timestamp(buffer) is None

  def test_returns_formatted_utc_timestamp_when_meta_present(self, element):
    import ntplib
    buffer = MagicMock()
    # Unix time 1700000000 (2023-11-14), converted to raw NTP seconds and
    # expressed in nanoseconds, matching how rtspsrc/GstReferenceTimestampMeta
    # encode it.
    ntp_seconds = ntplib.system_to_ntp_time(1700000000)
    buffer.get_reference_timestamp_meta.return_value = SimpleNamespace(
      timestamp=int(ntp_seconds * 1_000_000_000)
    )

    result = element._extract_ntp_timestamp(buffer)

    assert result is not None
    assert result.endswith("Z")
    from datetime import datetime
    datetime.strptime(result, "%Y-%m-%dT%H:%M:%S.%fZ")  # raises if malformed

  def test_returns_utc_timestamp_regardless_of_host_local_timezone(self, element, monkeypatch):
    """Regression: `_extract_ntp_timestamp` used to construct a naive
    datetime and then `astimezone`, silently interpreting it as local time.
    On non-UTC hosts that produced a skewed result."""
    import os
    import time as _time
    import ntplib

    orig_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    if hasattr(_time, "tzset"):
      _time.tzset()

    try:
      buffer = MagicMock()
      unix_seconds = 1700000000  # 2023-11-14T22:13:20Z
      ntp_seconds = ntplib.system_to_ntp_time(unix_seconds)
      buffer.get_reference_timestamp_meta.return_value = SimpleNamespace(
        timestamp=int(ntp_seconds * 1_000_000_000)
      )

      result = element._extract_ntp_timestamp(buffer)

      assert result == "2023-11-14T22:13:20.000Z"
    finally:
      if orig_tz is None:
        monkeypatch.delenv("TZ", raising=False)
      else:
        monkeypatch.setenv("TZ", orig_tz)
      if hasattr(_time, "tzset"):
        _time.tzset()
class RecordingVideoFrame:
  """Test double that records every constructed instance and its messages,
  so assertions can inspect what do_transform_ip published downstream."""

  instances = []

  def __init__(self, buffer, caps=None):
    self.buffer = buffer
    self.caps = caps
    self.messages = []
    RecordingVideoFrame.instances.append(self)

  def add_message(self, payload):
    self.messages.append(payload)


class TestAttachMetadataAndTransform:

  @pytest.fixture(autouse=True)
  def _patch_video_frame(self, monkeypatch):
    RecordingVideoFrame.instances = []
    monkeypatch.setattr(tsmod, "VideoFrame", RecordingVideoFrame)

  def test_do_transform_ip_publishes_json_payload(self, element, monkeypatch):
    monkeypatch.setattr(tsmod.time, "time", lambda: 1000.0)
    buffer = MagicMock()
    buffer.get_reference_timestamp_meta.return_value = None

    result = element.do_transform_ip(buffer)

    assert result == tsmod.Gst.FlowReturn.OK
    assert len(RecordingVideoFrame.instances) == 1
    import json
    payload = json.loads(RecordingVideoFrame.instances[0].messages[0])
    assert payload["timestamp_for_next_block"] == pytest.approx(1000.0)
    assert payload["timestamp_post_decode"].endswith("Z")
    assert payload["timestamp"] == payload["timestamp_post_decode"]
    assert payload["timestamp_src"] == "timestamp_post_decode"
    assert payload["timestamp_rtcp"] is None
    assert payload["postdecode_timestamp"] == payload["timestamp_post_decode"]

  def test_do_transform_ip_never_raises_and_still_returns_ok(self, element, monkeypatch):
    monkeypatch.setattr(element, "_attach_metadata", MagicMock(side_effect=RuntimeError("boom")))

    result = element.do_transform_ip(MagicMock())

    assert result == tsmod.Gst.FlowReturn.OK
    assert len(RecordingVideoFrame.instances) == 0

  def test_use_frame_ntp_timestamp_overrides_system_clock(self, element, monkeypatch):
    import ntplib
    monkeypatch.setattr(tsmod.time, "time", lambda: 1000.0)
    element.do_set_property(make_prop("use-frame-ntp-timestamp"), True)
    buffer = MagicMock()
    ntp_seconds = ntplib.system_to_ntp_time(1700000000)
    buffer.get_reference_timestamp_meta.return_value = SimpleNamespace(
      timestamp=int(ntp_seconds * 1_000_000_000)
    )

    element.do_transform_ip(buffer)

    import json
    payload = json.loads(RecordingVideoFrame.instances[0].messages[0])
    from datetime import datetime
    selected = datetime.strptime(payload["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
    post = datetime.strptime(payload["timestamp_post_decode"], "%Y-%m-%dT%H:%M:%S.%fZ")
    assert selected.year == 2023  # 1700000000 (unix) corresponds to Nov 2023
    assert post.year == 1970  # host clock at unix 1000
    assert payload["timestamp_src"] == "timestamp_rtcp"
    assert payload["timestamp_rtcp"] == payload["timestamp"]
    assert payload["postdecode_timestamp"] == payload["timestamp_post_decode"]

  def test_rtcp_missing_falls_back_and_tags_post_decode(self, element, monkeypatch):
    monkeypatch.setattr(tsmod.time, "time", lambda: 1000.0)
    element.do_set_property(make_prop("timestamp-source"), "timestamp_rtcp")
    buffer = MagicMock()
    buffer.get_reference_timestamp_meta.return_value = None
    element.do_transform_ip(buffer)
    import json
    payload = json.loads(RecordingVideoFrame.instances[0].messages[0])
    assert payload["timestamp_src"] == "timestamp_post_decode"
    assert payload["timestamp"] == payload["timestamp_post_decode"]
    assert payload["timestamp_rtcp"] is None
