# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for RTCP Sender Report → per-packet NTP mapping."""

from sscape_rtcp_ntp import (
  DEFAULT_CLOCK_RATE,
  NS_PER_SECOND,
  RtcpNtpMapper,
  ntp_32_32_to_ns,
  parse_rtcp_sender_reports,
  parse_rtp_header,
  signed_rtp_delta,
  unsigned_rtp_delta,
)

CLOCK_RATE = DEFAULT_CLOCK_RATE


def _sr_packet(ssrc: int, ntp_msw: int, ntp_lsw: int, rtp_ts: int) -> bytes:
  # V=2, RC=0, PT=200, length=6 (7 words: header + sender info)
  header = bytes([0x80, 200]) + (6).to_bytes(2, "big")
  body = (
    ssrc.to_bytes(4, "big")
    + ntp_msw.to_bytes(4, "big")
    + ntp_lsw.to_bytes(4, "big")
    + rtp_ts.to_bytes(4, "big")
    + (0).to_bytes(4, "big")  # packet count
    + (0).to_bytes(4, "big")  # octet count
  )
  return header + body


def _rtp_packet(rtp_ts: int, ssrc: int, seq: int = 1) -> bytes:
  header = bytes([0x80, 96]) + seq.to_bytes(2, "big")
  header += rtp_ts.to_bytes(4, "big")
  header += ssrc.to_bytes(4, "big")
  return header + b"\x00" * 8


class TestParsers:

  def test_rtp_header_extracts_timestamp_and_ssrc(self):
    packet = _rtp_packet(rtp_ts=0xAABBCCDD, ssrc=0x11223344, seq=9)
    assert parse_rtp_header(packet) == (0xAABBCCDD, 0x11223344)

  def test_rtp_header_rejects_truncated(self):
    assert parse_rtp_header(b"\x80\x60") is None

  def test_rtp_header_rejects_non_v2(self):
    packet = bytearray(_rtp_packet(1, 2))
    packet[0] = 0x40  # V=1
    assert parse_rtp_header(bytes(packet)) is None

  def test_rtcp_sr_parses_ntp_and_rtp(self):
    ntp_msw, ntp_lsw, rtp_ts, ssrc = 0xE0000001, 0x80000000, 90000, 7
    reports = parse_rtcp_sender_reports(_sr_packet(ssrc, ntp_msw, ntp_lsw, rtp_ts))
    assert len(reports) == 1
    got_ssrc, got_rtp, got_ntp_ns = reports[0]
    assert got_ssrc == ssrc
    assert got_rtp == rtp_ts
    assert got_ntp_ns == ntp_32_32_to_ns(ntp_msw, ntp_lsw)
    # 0.5s fraction from LSW 0x80000000
    assert got_ntp_ns == ntp_msw * NS_PER_SECOND + NS_PER_SECOND // 2

  def test_rtcp_compound_skips_sdes_keeps_sr(self):
    sr = _sr_packet(1, 10, 0, 100)
    # SDES: V=2, SC=1, PT=202, length=1 → 8 bytes (header + ssrc)
    sdes = bytes([0x81, 202]) + (1).to_bytes(2, "big") + (1).to_bytes(4, "big")
    reports = parse_rtcp_sender_reports(sr + sdes)
    assert len(reports) == 1
    assert reports[0][0] == 1

  def test_rtcp_truncated_returns_empty(self):
    assert parse_rtcp_sender_reports(b"\x80\xc8\x00") == []

  def test_rtcp_wrong_version_stops(self):
    packet = bytearray(_sr_packet(1, 1, 0, 1))
    packet[0] = 0x40
    assert parse_rtcp_sender_reports(bytes(packet)) == []


class TestRtpDelta:

  def test_signed_wrap(self):
    assert signed_rtp_delta(1, 0xFFFFFFFF) == 2

  def test_unsigned_rejects_backwards(self):
    assert unsigned_rtp_delta(10, 20) == 0
    assert unsigned_rtp_delta(20, 10) == 10


class TestMapper:

  def test_no_sr_returns_none(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    assert mapper.rtp_to_ntp_ns(0) is None
    assert mapper.has_lock() is False

  def test_single_sr_uses_nominal_clock_rate(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp0 = 1_700_000_000 * NS_PER_SECOND
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp0, ssrc=1)
    # 45000 ticks = 0.5 s at 90 kHz
    got = mapper.rtp_to_ntp_ns(45000, ssrc=1)
    assert got == ntp0 + NS_PER_SECOND // 2

  def test_two_srs_measure_rate_and_hit_endpoints(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp0 = 1_700_000_000 * NS_PER_SECOND
    # RTP clock running at 80 kHz vs NTP: 80000 ticks = 1 s
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp0, ssrc=9)
    mapper.observe_sr(rtp_ts=80000, ntp_ns=ntp0 + NS_PER_SECOND, ssrc=9)
    assert mapper.rtp_to_ntp_ns(0, ssrc=9) == ntp0
    assert mapper.rtp_to_ntp_ns(80000, ssrc=9) == ntp0 + NS_PER_SECOND
    assert mapper.rtp_to_ntp_ns(40000, ssrc=9) == ntp0 + NS_PER_SECOND // 2

  def test_new_sr_reanchors_so_error_does_not_accumulate(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp0 = 1_700_000_000 * NS_PER_SECOND
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp0, ssrc=1)
    # First mapping would put rtp=180000 at +2s (nominal 90 kHz).
    # A fresh SR at that RTP time reports only +1s of NTP — re-anchor.
    mapper.observe_sr(rtp_ts=180000, ntp_ns=ntp0 + NS_PER_SECOND, ssrc=1)
    got = mapper.rtp_to_ntp_ns(180000, ssrc=1)
    assert got == ntp0 + NS_PER_SECOND

  def test_rtp_wrap_between_sr_and_packet(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp0 = 1_700_000_000 * NS_PER_SECOND
    mapper.observe_sr(rtp_ts=0xFFFFFFFE, ntp_ns=ntp0, ssrc=1)
    # +2 ticks wraps to 0
    got = mapper.rtp_to_ntp_ns(0, ssrc=1)
    expected = ntp0 + (2 * NS_PER_SECOND) // CLOCK_RATE
    assert got == expected

  def test_insane_sr_rate_keeps_nominal_but_still_reanchors(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp0 = 1_700_000_000 * NS_PER_SECOND
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp0, ssrc=1)
    # 10 ticks claimed as 10 seconds — reject rate, keep 90 kHz, new origin
    mapper.observe_sr(rtp_ts=10, ntp_ns=ntp0 + 10 * NS_PER_SECOND, ssrc=1)
    got = mapper.rtp_to_ntp_ns(10 + CLOCK_RATE, ssrc=1)
    assert got == ntp0 + 10 * NS_PER_SECOND + NS_PER_SECOND

  def test_per_ssrc_locks_do_not_cross(self):
    mapper = RtcpNtpMapper(CLOCK_RATE)
    ntp_a = 1_700_000_000 * NS_PER_SECOND
    ntp_b = ntp_a + 5 * NS_PER_SECOND
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp_a, ssrc=1)
    mapper.observe_sr(rtp_ts=0, ntp_ns=ntp_b, ssrc=2)
    assert mapper.rtp_to_ntp_ns(0, ssrc=1) == ntp_a
    assert mapper.rtp_to_ntp_ns(0, ssrc=2) == ntp_b

  def test_zero_clock_rate_falls_back_to_default(self):
    mapper = RtcpNtpMapper(0)
    assert mapper.clock_rate == DEFAULT_CLOCK_RATE
