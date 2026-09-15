# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Map RTP timestamps to NTP using RTCP Sender Reports.

A Sender Report is an (RTP timestamp, NTP time) sample of the sender media
clock. Each media packet is converted with the current mapping:

    ntp = anchor_ntp + (rtp - anchor_rtp) / clock_rate

The slope is the advertised clock rate (90000 for H.264) -- the RTP media
clock *is* that rate, so measuring it from noisy reports only adds jitter.
Only the offset is servoed: each report nudges the anchor a fraction of the
way to its (rtp, ntp) sample instead of stepping the whole way, so per-report
arrival noise is low-passed rather than jittering capture time every report. A
report that disagrees by more than ``REANCHOR_THRESHOLD_NS`` is a genuine
discontinuity (stream/clock restart) and re-anchors immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Optional

RTCP_SR = 200
RTP_VERSION = 2
NS_PER_SECOND = 1_000_000_000
DEFAULT_CLOCK_RATE = 90000
# Offset servo: apply this fraction of each report's error to the anchor, so
# per-report arrival noise is low-passed instead of stepped in whole. The time
# constant (~SLEW_DEN * SR interval) is kept longer than the cameras' NTP
# re-sync period so their periodic clock corrections are smoothed, not injected.
SLEW_NUM = 1
SLEW_DEN = 8
# Beyond this a report is genuinely discontinuous (stream/clock restart) and
# re-anchors immediately rather than slewing toward it over many reports.
REANCHOR_THRESHOLD_NS = 100_000_000


def signed_rtp_delta(later: int, earlier: int) -> int:
  """Signed 32-bit RTP timestamp difference (handles wrap)."""
  delta = (int(later) - int(earlier)) & 0xFFFFFFFF
  if delta >= 0x80000000:
    delta -= 0x100000000
  return delta


def unsigned_rtp_delta(later: int, earlier: int) -> int:
  """Forward RTP delta in (0, 2**31]; 0 if *later* is not ahead of *earlier*."""
  delta = signed_rtp_delta(later, earlier)
  return delta if delta > 0 else 0


def ntp_32_32_to_ns(msw: int, lsw: int) -> int:
  """Convert NTP 32.32 (seconds since 1900) to integer nanoseconds."""
  return int(msw) * NS_PER_SECOND + (int(lsw) * NS_PER_SECOND) // (1 << 32)


def parse_rtp_header(data: bytes) -> Optional[tuple[int, int]]:
  """Return ``(rtp_timestamp, ssrc)`` from an RTP packet, or None."""
  if len(data) < 12:
    return None
  if (data[0] >> 6) != RTP_VERSION:
    return None
  rtp_ts = int.from_bytes(data[4:8], "big")
  ssrc = int.from_bytes(data[8:12], "big")
  return rtp_ts, ssrc


def parse_rtcp_sender_reports(data: bytes) -> list[tuple[int, int, int]]:
  """Parse compound RTCP for Sender Reports.

  Returns a list of ``(ssrc, rtp_timestamp, ntp_ns)``. Truncated or
  non-version-2 input yields whatever complete SR packets were found.
  """
  reports: list[tuple[int, int, int]] = []
  offset = 0
  length = len(data)
  while offset + 4 <= length:
    version = data[offset] >> 6
    if version != RTP_VERSION:
      break
    packet_type = data[offset + 1]
    word_count = int.from_bytes(data[offset + 2:offset + 4], "big")
    size = (word_count + 1) * 4
    if size < 8 or offset + size > length:
      break
    if packet_type == RTCP_SR and size >= 28:
      ssrc = int.from_bytes(data[offset + 4:offset + 8], "big")
      ntp_msw = int.from_bytes(data[offset + 8:offset + 12], "big")
      ntp_lsw = int.from_bytes(data[offset + 12:offset + 16], "big")
      rtp_ts = int.from_bytes(data[offset + 16:offset + 20], "big")
      reports.append((ssrc, rtp_ts, ntp_32_32_to_ns(ntp_msw, ntp_lsw)))
    offset += size
  return reports


@dataclass
class _Anchor:
  ssrc: int
  rtp: int
  ntp_ns: int
  dntp_ns: int
  drtp: int


class RtcpNtpMapper:
  """Thread-safe per-SSRC RTP -> NTP mapping (advertised rate, servoed offset)."""

  def __init__(self, clock_rate: int = DEFAULT_CLOCK_RATE):
    self._lock = Lock()
    self._clock_rate = int(clock_rate) if int(clock_rate) > 0 else DEFAULT_CLOCK_RATE
    self._anchors: dict[int, _Anchor] = {}
    self._last_ssrc: Optional[int] = None

  @property
  def clock_rate(self) -> int:
    return self._clock_rate

  def set_clock_rate(self, clock_rate: int) -> None:
    rate = int(clock_rate)
    if rate <= 0:
      return
    with self._lock:
      self._clock_rate = rate

  def has_lock(self, ssrc: Optional[int] = None) -> bool:
    with self._lock:
      if ssrc is None:
        return bool(self._anchors)
      return ssrc in self._anchors

  def observe_sr(self, rtp_ts: int, ntp_ns: int, ssrc: int = 0) -> _Anchor:
    """Fold a Sender Report into the mapping for *ssrc*.

    The slope stays the advertised clock rate; only the offset is servoed
    toward the report, so a report's arrival noise is smoothed rather than
    stepping derived capture time every report. A report that disagrees by
    more than REANCHOR_THRESHOLD_NS re-anchors hard (stream/clock restart).
    """
    rtp_ts = int(rtp_ts) & 0xFFFFFFFF
    ntp_ns = int(ntp_ns)
    ssrc = int(ssrc)
    with self._lock:
      dntp_ns, drtp = self._nominal_rate()
      prev = self._anchors.get(ssrc)
      if prev is None:
        anchor = _Anchor(ssrc, rtp_ts, ntp_ns, dntp_ns, drtp)
        self._anchors[ssrc] = anchor
        self._last_ssrc = ssrc
        return anchor
      if ntp_ns < prev.ntp_ns:
        # A delayed/reordered SR must not move capture time backwards.
        return prev
      forward = unsigned_rtp_delta(rtp_ts, prev.rtp)
      if forward <= 0:
        return prev
      predicted = prev.ntp_ns + (forward * dntp_ns) // drtp
      error = ntp_ns - predicted
      if abs(error) > REANCHOR_THRESHOLD_NS:
        new_ntp = ntp_ns
      else:
        new_ntp = predicted + (error * SLEW_NUM) // SLEW_DEN
      anchor = _Anchor(ssrc, rtp_ts, new_ntp, dntp_ns, drtp)
      self._anchors[ssrc] = anchor
      self._last_ssrc = ssrc
      return anchor

  def rtp_to_ntp_ns(self, rtp_ts: int, ssrc: Optional[int] = None) -> Optional[int]:
    """NTP nanoseconds (1900 epoch) for this RTP timestamp, or None."""
    with self._lock:
      anchor = self._anchor_locked(ssrc)
      if anchor is None or anchor.drtp <= 0:
        return None
      delta = signed_rtp_delta(int(rtp_ts) & 0xFFFFFFFF, anchor.rtp)
      return anchor.ntp_ns + (delta * anchor.dntp_ns) // anchor.drtp

  def _anchor_locked(self, ssrc: Optional[int]) -> Optional[_Anchor]:
    if ssrc is not None:
      return self._anchors.get(ssrc)
    if self._last_ssrc is not None:
      return self._anchors.get(self._last_ssrc)
    return None

  def _nominal_rate(self) -> tuple[int, int]:
    return NS_PER_SECOND, self._clock_rate
