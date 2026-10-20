# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""NTP clock-offset monitor gating PTZ pose validity."""

import logging
import math
import threading
import time

import ntplib

log = logging.getLogger(__name__)


class ClockMonitor:
  """Tracks the host clock offset against an NTP server.

  The clock counts as synchronized only while the last successful measurement is
  recent and its absolute offset is within `max_clock_offset_s`.
  """

  def __init__(self, server, max_clock_offset_s, check_interval_s=30.0, client=None,
               monotonic=time.monotonic, metrics=None):
    if isinstance(max_clock_offset_s, bool) or not isinstance(max_clock_offset_s, (int, float)) \
        or not math.isfinite(max_clock_offset_s) or max_clock_offset_s <= 0:
      raise ValueError("max_clock_offset_s must be a positive finite number")
    if not check_interval_s > 0:
      raise ValueError("check_interval_s must be positive")
    self.server = server
    self.max_clock_offset_s = float(max_clock_offset_s)
    self.check_interval_s = float(check_interval_s)
    self.max_measurement_age_s = 3 * self.check_interval_s
    self._client = client or ntplib.NTPClient()
    self._monotonic = monotonic
    self._metrics = metrics
    self._lock = threading.Lock()
    self._offset_s = None
    self._measured_at = None

  @property
  def offset_s(self):
    with self._lock:
      return self._offset_s

  def check(self):
    """Measure the offset once; returns True when the clock is synchronized."""
    if not self.server:
      log.warning("No NTP server configured; PTZ sources stay invalid")
      return False
    try:
      offset_s = float(self._client.request(self.server, version=3, timeout=1).offset)
    except (ntplib.NTPException, OSError, ValueError) as error:
      log.warning(f"NTP request to {self.server} failed: {error}")
      return self.is_synchronized()
    if not math.isfinite(offset_s):
      log.warning("NTP returned a non-finite clock offset")
      return self.is_synchronized()
    with self._lock:
      self._offset_s = offset_s
      self._measured_at = self._monotonic()
    if self._metrics is not None:
      self._metrics.set_clock_offset(offset_s)
    synchronized = abs(offset_s) <= self.max_clock_offset_s
    if not synchronized:
      log.warning(f"Clock offset {offset_s:.6f}s exceeds {self.max_clock_offset_s}s; "
                  "PTZ sources invalid")
    return synchronized

  def is_synchronized(self):
    with self._lock:
      if self._offset_s is None:
        return False
      if self._monotonic() - self._measured_at > self.max_measurement_age_s:
        return False
      return abs(self._offset_s) <= self.max_clock_offset_s

  def run(self, stop_event):
    while not stop_event.wait(self.check_interval_s):
      self.check()
