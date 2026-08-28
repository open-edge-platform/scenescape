# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""GStreamer element: per-packet NTP from RTCP Sender Reports.

Place immediately after ``rtspsrc`` (still RTP). Each buffer's RTP timestamp
is converted with the latest Sender Report and written as
``GstReferenceTimestampMeta`` (caps ``timestamp/x-ntp``). Downstream
``sscape_timestamp_capture use-frame-ntp-timestamp=true`` reads that meta.

GStreamer's ``add-reference-timestamp-meta`` interpolates from an SR using
the advertised clock-rate; this element re-anchors on every SR and uses the
measured RTP/NTP rate between reports so capture time stays sub-ms aligned
to the sender clock for the whole session.
"""

from __future__ import annotations

from typing import Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import (  # pylint: disable=no-name-in-module
  Gst,
  GstBase,
  GObject,
)

from sscape_gst_log import GstCategoryLogger
from sscape_rtcp_ntp import (
  DEFAULT_CLOCK_RATE,
  RtcpNtpMapper,
  parse_rtcp_sender_reports,
  parse_rtp_header,
)

NTP_CAPS_STRING = "timestamp/x-ntp"

_GST_LOG = GstCategoryLogger(
  "sscape_rtp_ntp",
  "SceneScape RTP/RTCP NTP timestamp mapping element",
)


def _iter_bin_elements(element):
  """Yield *element* and every descendant if it is a Gst.Bin."""
  yield element
  if not isinstance(element, Gst.Bin):
    return
  iterator = element.iterate_elements()
  while True:
    result, child = iterator.next()
    if result == Gst.IteratorResult.DONE:
      break
    if result == Gst.IteratorResult.RESYNC:
      iterator.resync()
      continue
    if result != Gst.IteratorResult.OK:
      break
    yield from _iter_bin_elements(child)


def _read_buffer_prefix(buffer: Gst.Buffer, nbytes: int) -> bytes:
  success, mapinfo = buffer.map(Gst.MapFlags.READ)
  if not success:
    return b""
  try:
    data = bytes(mapinfo.data[:nbytes])
  finally:
    buffer.unmap(mapinfo)
  return data


class RtpNtpTimestamp(GstBase.BaseTransform):
  """Rewrite NTP reference-timestamp meta from RTCP SR + per-packet RTP."""

  __gstmetadata__ = (
    "SceneScape RTP/RTCP NTP timestamp",
    "Filter/Network/RTP",
    "Map each RTP packet to NTP using RTCP Sender Reports",
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
    "clock-rate": (
      int,
      "RTP clock rate",
      "Media clock rate in Hz (overridden by caps clock-rate when present).",
      1, 1000000, DEFAULT_CLOCK_RATE,
      GObject.ParamFlags.READWRITE,
    ),
  }

  def __init__(self):
    super().__init__()
    self.set_in_place(True)
    self.set_passthrough(False)

    self._log = _GST_LOG
    self._mapper = RtcpNtpMapper(DEFAULT_CLOCK_RATE)
    self._ntp_caps = Gst.Caps.from_string(NTP_CAPS_STRING)
    self._rtcp_probe_ids: list[tuple] = []
    self._rtspsrc = None
    self._manager_handler_id = None
    self._sr_count = 0

  def do_get_property(self, prop):  # pylint: disable=arguments-differ
    if prop.name == "clock-rate":
      return self._mapper.clock_rate
    raise AttributeError(f"Unknown property {prop.name}")

  def do_set_property(self, prop, value):  # pylint: disable=arguments-differ
    if prop.name == "clock-rate":
      self._mapper.set_clock_rate(int(value))
      return
    raise AttributeError(f"Unknown property {prop.name}")

  def do_start(self):  # pylint: disable=arguments-differ
    self._attach_rtcp_probes()
    return True

  def do_stop(self):  # pylint: disable=arguments-differ
    self._detach_rtcp_probes()
    return True

  def do_set_caps(self, incaps, _outcaps):  # pylint: disable=arguments-differ
    if incaps and incaps.get_size() > 0:
      structure = incaps.get_structure(0)
      ok, rate = structure.get_int("clock-rate")
      if ok and rate > 0:
        self._mapper.set_clock_rate(rate)
        self._log.info(f"clock-rate from caps={rate}")
    return True

  def do_transform_ip(self, buffer):  # pylint: disable=arguments-differ
    try:
      self._attach_rtcp_probes()
      self._stamp_buffer(buffer)
    except Exception:  # pylint: disable=broad-except
      self._log.exception("Failed to map RTP timestamp to NTP")
    return Gst.FlowReturn.OK

  def _find_rtspsrc(self):
    peer = self.sinkpad.get_peer() if self.sinkpad else None
    seen = set()
    pad = peer
    while pad is not None:
      parent = pad.get_parent_element()
      if parent is None:
        break
      ident = id(parent)
      if ident in seen:
        break
      seen.add(ident)
      factory = parent.get_factory()
      if factory is not None and factory.get_name() == "rtspsrc":
        return parent
      sink = parent.get_static_pad("sink")
      if sink is None:
        break
      pad = sink.get_peer()
    return None

  def _attach_rtcp_probes(self) -> None:
    if self._rtcp_probe_ids:
      return
    rtspsrc = self._find_rtspsrc()
    if rtspsrc is None:
      return
    self._rtspsrc = rtspsrc
    if self._manager_handler_id is None:
      try:
        self._manager_handler_id = rtspsrc.connect(
          "new-manager", self._on_new_manager,
        )
      except TypeError:
        self._manager_handler_id = None

    watched_pads: set[int] = set()
    sessions = []
    jitterbuffers = []
    for child in _iter_bin_elements(rtspsrc):
      factory = child.get_factory()
      if factory is None:
        continue
      element_name = factory.get_name()
      if element_name == "rtpsession":
        sessions.append(child)
      elif element_name == "rtpjitterbuffer":
        jitterbuffers.append(child)

    targets: list[tuple] = []
    for session in sessions:
      rtcp_sink = session.get_static_pad("recv_rtcp_sink")
      if rtcp_sink is not None:
        targets.append((rtcp_sink, "rtpsession recv_rtcp_sink"))
    if not targets:
      for jitterbuffer in jitterbuffers:
        rtcp_sink = jitterbuffer.get_static_pad("sink_rtcp")
        if rtcp_sink is None:
          rtcp_sink = jitterbuffer.get_static_pad("recv_rtcp_sink")
        if rtcp_sink is not None:
          targets.append((rtcp_sink, "rtpjitterbuffer sink_rtcp"))

    for rtcp_sink, log_label in targets:
      pad_id = id(rtcp_sink)
      if pad_id in watched_pads:
        continue
      watched_pads.add(pad_id)
      probe_id = rtcp_sink.add_probe(
        Gst.PadProbeType.BUFFER, self._on_rtcp_buffer,
      )
      self._rtcp_probe_ids.append((rtcp_sink, probe_id))
      self._log.info(f"watching RTCP on {log_label}")

  def _on_new_manager(self, _src, _manager):
    self._remove_rtcp_probes()
    self._attach_rtcp_probes()

  def _remove_rtcp_probes(self) -> None:
    for pad, probe_id in self._rtcp_probe_ids:
      try:
        pad.remove_probe(probe_id)
      except Exception:  # pylint: disable=broad-except
        pass
    self._rtcp_probe_ids = []

  def _detach_rtcp_probes(self) -> None:
    self._remove_rtcp_probes()
    if self._rtspsrc is not None and self._manager_handler_id is not None:
      try:
        self._rtspsrc.disconnect(self._manager_handler_id)
      except Exception:  # pylint: disable=broad-except
        pass
    self._manager_handler_id = None
    self._rtspsrc = None

  def _on_rtcp_buffer(self, _pad, info):
    buffer = info.get_buffer()
    if buffer is None:
      return Gst.PadProbeReturn.OK
    data = _read_buffer_prefix(buffer, buffer.get_size())
    for ssrc, rtp_ts, ntp_ns in parse_rtcp_sender_reports(data):
      anchor = self._mapper.observe_sr(rtp_ts, ntp_ns, ssrc=ssrc)
      self._sr_count += 1
      self._log.info(
        f"SR #{self._sr_count} ssrc={ssrc:08x} rtp={rtp_ts} "
        f"ntp_ns={ntp_ns} rate={anchor.dntp_ns}/{anchor.drtp} ns/tick"
      )
    return Gst.PadProbeReturn.OK

  def _stamp_buffer(self, buffer: Gst.Buffer) -> None:
    data = _read_buffer_prefix(buffer, 12)
    parsed = parse_rtp_header(data)
    if parsed is None:
      return
    rtp_ts, ssrc = parsed
    ntp_ns = self._mapper.rtp_to_ntp_ns(rtp_ts, ssrc=ssrc)
    if ntp_ns is None:
      return
    if not self._ntp_caps:
      return
    # transform_ip is in-place: stamp this buffer, never a make_writable copy.
    existing = buffer.get_reference_timestamp_meta(self._ntp_caps)
    if existing is not None:
      try:
        buffer.remove_meta(existing)
      except Exception:  # pylint: disable=broad-except
        pass
    buffer.add_reference_timestamp_meta(
      self._ntp_caps, int(ntp_ns), Gst.CLOCK_TIME_NONE,
    )


GObject.type_register(RtpNtpTimestamp)
__gstelementfactory__ = (
  "sscape_rtp_ntp",
  Gst.Rank.NONE,
  RtpNtpTimestamp,
)
