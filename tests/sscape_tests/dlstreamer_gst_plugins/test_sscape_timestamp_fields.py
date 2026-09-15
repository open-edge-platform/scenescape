# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for MQTT timestamp field names and source selection."""

from sscape_timestamp_fields import (
  TS_POST_DECODE,
  TS_RTCP,
  format_epoch_ms_iso,
  format_unix_iso,
  normalize_timestamp_source,
  select_timestamp,
)


class TestNormalizeTimestampSource:

  def test_canonical_names_pass_through(self):
    assert normalize_timestamp_source(TS_RTCP) == TS_RTCP
    assert normalize_timestamp_source(TS_POST_DECODE) == TS_POST_DECODE

  def test_aliases_map_to_canonical_fields(self):
    assert normalize_timestamp_source("early") == TS_RTCP
    assert normalize_timestamp_source("rtcp") == TS_RTCP
    assert normalize_timestamp_source(True) == TS_RTCP
    assert normalize_timestamp_source("late") == TS_POST_DECODE
    assert normalize_timestamp_source("post-decode") == TS_POST_DECODE
    assert normalize_timestamp_source(False) == TS_POST_DECODE

  def test_unknown_or_empty_falls_back_to_default(self):
    assert normalize_timestamp_source("bogus") == TS_POST_DECODE
    assert normalize_timestamp_source("") == TS_POST_DECODE
    assert normalize_timestamp_source(None) == TS_POST_DECODE
    assert normalize_timestamp_source("bogus", default=TS_RTCP) == TS_RTCP


class TestSelectTimestamp:

  def test_selects_requested_clock(self):
    clocks = {TS_RTCP: "rtcp-iso", TS_POST_DECODE: "late-iso"}
    assert select_timestamp(clocks, TS_RTCP) == ("rtcp-iso", TS_RTCP)
    assert select_timestamp(clocks, "late") == ("late-iso", TS_POST_DECODE)

  def test_missing_rtcp_falls_back_and_tags_post_decode(self):
    clocks = {TS_RTCP: None, TS_POST_DECODE: "late-iso"}
    selected, source = select_timestamp(clocks, TS_RTCP)
    assert selected == "late-iso"
    assert source == TS_POST_DECODE

  def test_empty_rtcp_string_is_treated_as_missing(self):
    clocks = {TS_RTCP: "", TS_POST_DECODE: "late-iso"}
    selected, source = select_timestamp(clocks, "early")
    assert selected == "late-iso"
    assert source == TS_POST_DECODE

  def test_empty_clocks_return_empty_post_decode(self):
    selected, source = select_timestamp({}, TS_RTCP)
    assert selected == ""
    assert source == TS_POST_DECODE


class TestFormatters:

  def test_format_unix_iso_is_utc_with_millis_and_z(self):
    assert format_unix_iso(1700000000) == "2023-11-14T22:13:20.000Z"

  def test_format_epoch_ms_iso_round_trips(self):
    assert format_epoch_ms_iso(1700000000000) == "2023-11-14T22:13:20.000Z"

  def test_format_epoch_ms_iso_rejects_unusable_values(self):
    assert format_epoch_ms_iso(None) is None
    assert format_epoch_ms_iso("not-a-number") is None
