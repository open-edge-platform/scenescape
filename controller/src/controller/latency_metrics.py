# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import collections
import threading

from scene_common import log
from scene_common.timestamp import get_epoch_time
from controller.observability import metrics

DEFAULT_MAX_MATCH_LATENCIES_TRACKED = 10

class MatchLatencyTracker:
  """
  Tracks per-match latency: the elapsed time between a track's first
  appearance and its match/no-match decision. Keeps a bounded rolling window
  of recent measurements in memory so downstream metrics (dashboards,
  exporters, health checks) can be derived from real measurements rather
  than estimates.

  Every sample is also pushed as a raw value to an OTel histogram
  (record_reid_match_latency), so P95/P99 can be computed rigorously
  downstream (e.g. Prometheus histogram_quantile()) over whatever time
  range is queried -- not estimated in-process over a fixed sample count.

  Each recorded sample can be tagged with a camera_count and category
  supplied by the caller (see recordMatchLatency) -- this class has no
  camera or category knowledge of its own. UUIDManager derives camera_count
  locally from the distinct sscape_object.camera values among its currently
  active tracks, and passes through sscape_object.category, so no external
  plumbing (Scene/Tracking propagation) or REST calls are needed. category
  matters because a single controller process runs one MatchLatencyTracker
  per tracked category (e.g. "person", "car") -- without tagging, two
  categories' metrics would collide on the same unlabeled OTel time series.

  Thread-safe: intended to be shared across the tracker thread and the
  ThreadPoolExecutor worker threads that resolve similarity queries.
  """

  def __init__(self, max_tracked=DEFAULT_MAX_MATCH_LATENCIES_TRACKED):
    self._start_times = {}
    self._start_times_lock = threading.Lock()
    self._latencies = collections.deque(maxlen=max_tracked)
    self._latencies_lock = threading.Lock()

  def shutdown(self):
    """No-op, kept for interface stability with callers that always call it."""
    return

  def markTrackStart(self, track_id, timestamp=None):
    """
    Record the moment a track is first seen, for later per-match latency
    measurement. Uses setdefault so an already-running track's clock is
    never reset by a duplicate call.

    @param  track_id   The tracker ID that was just observed for the first time
    @param  timestamp  Epoch time of first appearance; defaults to now
    """
    if timestamp is None:
      timestamp = get_epoch_time()
    with self._start_times_lock:
      self._start_times.setdefault(track_id, timestamp)

  def recordMatchLatency(self, track_id, decision_timestamp=None, camera_count=None, category=None):
    """
    Compute and record the elapsed time between a track's first appearance
    and its match/no-match decision. Pops the start time so it is only
    counted once per track lifecycle, even if this is called more than once.

    @param   track_id            The tracker ID whose latency is being recorded
    @param   decision_timestamp  Epoch time of the match decision; defaults to now
    @param   camera_count        Number of active cameras at decision time, as
                                 determined by the caller. None if unknown.
    @param   category            The tracked object category (e.g. "person",
                                 "car") this sample belongs to. None if unknown.
                                 Used to tag exported metrics so multiple
                                 categories don't collide on the same series.
    @return  bool                True if a latency was recorded, False if there
                                 was no matching start time or the measurement
                                 was discarded (e.g. negative latency)
    """
    if decision_timestamp is None:
      decision_timestamp = get_epoch_time()

    with self._start_times_lock:
      start_time = self._start_times.pop(track_id, None)

    if start_time is None:
      return False

    latency = decision_timestamp - start_time
    if latency < 0:
      log.warning(
        f"MatchLatencyTracker: Negative latency ({latency:.3f}s) for "
        f"track_id={track_id}; discarding this measurement.")
      return False

    with self._latencies_lock:
      self._latencies.append({'latency': latency, 'camera_count': camera_count, 'category': category})

    otel_attributes = {'category': category} if category is not None else None

    # Raw sample straight to the histogram -- this is what makes rigorous
    # P95/P99 possible downstream (e.g. Prometheus histogram_quantile()),
    # aggregated over whatever time range is queried rather than a fixed
    # in-process sample count.
    metrics.record_reid_match_latency(latency, otel_attributes)

    # Push the rolling-window (last DEFAULT_MAX_MATCH_LATENCIES_TRACKED
    # samples) summary stats as gauges, in seconds (native unit of the
    # latency values already stored in self._latencies). Tagged with
    # category so multiple tracked categories (e.g. person + car) don't
    # overwrite each other's values on the same unlabeled time series.
    # camera_count is reported separately via record_reid_current_camera_count
    # rather than as an attribute here.
    rolling_stats = self.getStats()
    if rolling_stats['average'] is not None:
      metrics.record_reid_rolling_avg_match_latency(rolling_stats['average'], otel_attributes)
      metrics.record_reid_rolling_min_match_latency(rolling_stats['min'], otel_attributes)
      metrics.record_reid_rolling_max_match_latency(rolling_stats['max'], otel_attributes)
    if rolling_stats['camera_count'] is not None:
      metrics.record_reid_current_camera_count(rolling_stats['camera_count'], otel_attributes)

    return True

  def discardTrackStart(self, track_id):
    """
    Discard a track's start time without recording a latency. Used when a
    track goes inactive without ever reaching a match decision (e.g. reid
    disabled, insufficient features), so the start-time dict doesn't leak.

    @param  track_id  The tracker ID to discard
    """
    with self._start_times_lock:
      self._start_times.pop(track_id, None)

  def getStats(self):
    """
    Return summary stats over the most recently recorded per-match latencies,
    for downstream metrics consumers (e.g. dashboards, exporters). Aggregates
    across all samples in the rolling window, and includes the camera count
    tagged on the most recently recorded sample for context.

    @return  dict  {'count': int, 'average': float|None, 'min': float|None,
                    'max': float|None, 'camera_count': int|None}
                   'camera_count' is whatever was passed to recordMatchLatency
                   for the latest sample in the window (None if there are no
                   samples yet, or if that call didn't provide one).
    """
    with self._latencies_lock:
      samples = list(self._latencies)

    latencies = [s['latency'] for s in samples]
    camera_count = samples[-1]['camera_count'] if samples else None

    if not latencies:
      return {'average': None, 'min': None, 'max': None,
              'camera_count': camera_count}

    return {
      'average': sum(latencies) / len(latencies),
      'min': min(latencies),
      'max': max(latencies),
      'camera_count': camera_count,
    }
