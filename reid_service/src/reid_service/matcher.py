# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live-loop ReID orchestration ported from ``controller.uuid_manager.UUIDManager``.

One ``TrackMatcher`` serves one (scene_id, category) stream, the same scope a
Controller ``UUIDManager`` has today. It decides when to query and when to
write; the adapter (``ReIDDatabase``) decides how.

Ported:
  - quality-feature gating (pixel-bbox area, vetted provenance)
  - per-track feature accumulation with exact-duplicate suppression
  - lazy dimension inference + ``ensureSchema`` on the first vector
  - ``findMatches`` once ``feature_accumulation_threshold`` observations exist,
    majority-vote result parsing, live-gid collision handling
  - enrollment vector selection (promotion on no-match, per-vector exact-hit
    skip on rematch), slicing, flush on track exit or stale timeout
  - write-health / epoch so failed or superseded writes stop further writes

Not ported (see design doc §5.1 / follow-up stories):
  - hierarchy will_enroll / empty-batch handoff (ADR 15)
  - persisted-attribute merge (``getPersistedAttributes``) and chain_data
  - the query-latency circuit breaker (``DEFAULT_MAX_QUERY_TIME``)
  - purge scheduling and Controller metrics

Writes are off unless ``write_enabled`` is True (shadow mode). In shadow mode
the matcher queries and reports decisions but never calls ``addEntry``, so it
can run beside the Controller without double-enrolling descriptors.
"""

import collections
import concurrent.futures
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from scene_common import log
from scene_common.reid_constants import (
  COSINE_SIMILARITY_TOLERANCE,
  DEFAULT_CONFIG_SIMILARITY_METRIC,
  DEFAULT_MINIMUM_BBOX_AREA,
  QUERY_K_NEIGHBORS,
  is_higher_better_metric,
  is_similarity_match,
  is_upstream_enrollment_claim,
  is_vetted_provenance,
  normalize_config_similarity_metric,
  normalize_similarity_score,
  pick_best_metric_value,
  resolve_database_similarity_metric,
)
from reid_service.reid import (
  ReidNoValidVectorsError,
  ReidPartialWriteError,
  ReidWriteSupersededError,
)

# Same defaults as controller.uuid_manager.
DEFAULT_SIMILARITY_THRESHOLD_L2 = 40.0
DEFAULT_SIMILARITY_THRESHOLD_COSINE = 0.5
DEFAULT_MINIMUM_FEATURE_COUNT = 12
DEFAULT_FEATURE_SLICE_SIZE = 10
DEFAULT_STALE_FEATURE_TIMEOUT_SECS = 5.0


@dataclass
class MatcherConfig:
  """reid-config.json values, with the Controller's defaults."""
  minimum_feature_count: int = DEFAULT_MINIMUM_FEATURE_COUNT
  similarity_metric: str = DEFAULT_CONFIG_SIMILARITY_METRIC
  similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD_COSINE
  minimum_bbox_area: float = DEFAULT_MINIMUM_BBOX_AREA
  feature_slice_size: int = DEFAULT_FEATURE_SLICE_SIZE
  stale_feature_timeout_secs: float = DEFAULT_STALE_FEATURE_TIMEOUT_SECS
  # Scene-level tracks carry no pixel bbox, so the Controller's bbox-area gate
  # cannot be applied here. When True, an embedding with neither a bbox nor
  # vetted provenance is still used. See ingest docs before enabling writes.
  accept_unvetted_embeddings: bool = True

  @classmethod
  def from_reid_config(cls, data=None, accept_unvetted_embeddings=True):
    data = data or {}
    metric = normalize_config_similarity_metric(
      data.get("similarity_metric", DEFAULT_CONFIG_SIMILARITY_METRIC))
    threshold = data.get("similarity_threshold")
    if threshold is None:
      threshold = (DEFAULT_SIMILARITY_THRESHOLD_COSINE if metric == "COSINE"
                   else DEFAULT_SIMILARITY_THRESHOLD_L2)
    return cls(
      minimum_feature_count=int(data.get(
        "feature_accumulation_threshold", DEFAULT_MINIMUM_FEATURE_COUNT)),
      similarity_metric=metric,
      similarity_threshold=_validate_threshold(threshold, metric),
      minimum_bbox_area=data.get("minimum_bbox_area", DEFAULT_MINIMUM_BBOX_AREA),
      feature_slice_size=int(data.get("feature_slice_size", DEFAULT_FEATURE_SLICE_SIZE)),
      stale_feature_timeout_secs=float(data.get(
        "stale_feature_timeout_secs", DEFAULT_STALE_FEATURE_TIMEOUT_SECS)),
      accept_unvetted_embeddings=accept_unvetted_embeddings,
    )


def _validate_threshold(value, metric):
  try:
    threshold = float(value)
  except (TypeError, ValueError) as err:
    raise ValueError(f"similarity_threshold must be numeric, got {value}") from err
  if not math.isfinite(threshold):
    raise ValueError(f"similarity_threshold must be finite, got {value}")
  if metric == "COSINE" and not -1.0 <= threshold <= 1.0:
    raise ValueError("similarity_threshold for COSINE must be within [-1.0, 1.0]")
  if metric != "COSINE" and threshold < 0.0:
    raise ValueError("similarity_threshold for L2 must be non-negative")
  return threshold


@dataclass
class TrackObservation:
  """One object from one scene-track message."""
  track_id: str
  category: str
  embedding: Optional[np.ndarray] = None
  provenance: Optional[dict] = None
  metadata: Dict[str, Any] = field(default_factory=dict)
  bbox_px_area: Optional[float] = None
  timestamp: Optional[str] = None
  camera_id: Optional[str] = None
  cameras: List[str] = field(default_factory=list)
  # Present when the stream is Controller output (already ReID-resolved);
  # used for shadow-mode parity, never for decisions.
  upstream_reid_state: Optional[str] = None
  previous_ids: List[str] = field(default_factory=list)


@dataclass
class _TrackState:
  quality: List[np.ndarray] = field(default_factory=list)
  observation_count: int = 0
  enrollment: List[np.ndarray] = field(default_factory=list)
  local_enrollment: List[np.ndarray] = field(default_factory=list)
  query_submitted: bool = False
  gid: Optional[str] = None
  similarity: Optional[float] = None
  upstream_id: Optional[str] = None
  upstream_reid_state: Optional[str] = None
  last_embedding: Optional[np.ndarray] = None
  distinct_embeddings: int = 0


class _InlineExecutor:
  """Run submitted work immediately (tests, or single-threaded use)."""

  def submit(self, fn, *args, **kwargs):
    future = concurrent.futures.Future()
    try:
      future.set_result(fn(*args, **kwargs))
    except BaseException as err:  # noqa: B902 - mirror executor semantics
      future.set_exception(err)
    return future

  def shutdown(self, wait=True):
    return


def _same_vector(a, b):
  return np.array_equal(np.asarray(a, dtype=np.float32).reshape(-1),
                        np.asarray(b, dtype=np.float32).reshape(-1))


def _contains(vectors, candidate):
  return any(_same_vector(v, candidate) for v in vectors)


def _append_unique(vectors, candidate):
  if _contains(vectors, candidate):
    return False
  vectors.append(candidate)
  return True


class TrackMatcher:
  """Match and enroll the tracks of one (scene_id, category) stream."""

  def __init__(self, adapter, config: MatcherConfig, scene_id=None, category=None,
               write_enabled=False, executor=None,
               on_decision: Optional[Callable[[dict], None]] = None,
               clock: Callable[[], float] = time.time):
    self.adapter = adapter
    self.config = config
    self.scene_id = scene_id
    self.category = category
    self.write_enabled = write_enabled
    self.executor = executor or _InlineExecutor()
    self.on_decision = on_decision
    self.clock = clock

    # Same mapping UUIDManager applies: COSINE config -> IP descriptors.
    self.adapter.similarity_metric = resolve_database_similarity_metric(
      config.similarity_metric)

    self._lock = threading.RLock()
    self._tracks: Dict[str, _TrackState] = {}
    self._pending: Dict[str, dict] = {}
    self._pending_since: Dict[str, float] = {}

    self._dimensions = None
    self._dimensions_lock = threading.Lock()

    # Write-health (non-hierarchy subset of UUIDManager's state machine).
    self.write_healthy = True
    self.write_confirmed = False
    self.write_epoch = 0
    self._write_lock = threading.Lock()

    self.stats = collections.Counter()

  def process_frame(self, observations: List[TrackObservation]):
    """Feed one scene-track message, then retire tracks no longer present."""
    present = set()
    for obs in observations:
      self.observe(obs)
      present.add(obs.track_id)
    self.prune(present)
    self.flush_stale()

  def observe(self, obs: TrackObservation):
    with self._lock:
      state = self._stateFor(obs)
      state.upstream_id = obs.track_id
      state.upstream_reid_state = obs.upstream_reid_state

      if obs.embedding is None:
        self.stats["observations_without_embedding"] += 1
        return
      self.stats["observations_with_embedding"] += 1
      # A producer that freezes metadata per track (Tracker metadata fusion)
      # repeats the same vector every frame; make that visible in IngestStats.
      if state.last_embedding is not None and _same_vector(state.last_embedding, obs.embedding):
        self.stats["embeddings_repeated"] += 1
      else:
        self.stats["embeddings_changed"] += 1
        state.distinct_embeddings += 1
      state.last_embedding = obs.embedding
      if not self._ensureDimensions(obs.embedding):
        return

      if state.query_submitted:
        # Decision made (or in flight): keep enhancing the pending write,
        # as UUIDManager.pickBestID does after a match decision.
        if state.gid is not None:
          self._appendPendingEnrollment(obs, state)
        return

      if not self._isQueryable(obs):
        self.stats["embeddings_rejected_quality"] += 1
        return

      state.observation_count += 1
      _append_unique(state.quality, obs.embedding)
      if self._mayContributeEnrollment(obs):
        if _append_unique(state.enrollment, obs.embedding) and self._isEnrollable(obs):
          _append_unique(state.local_enrollment, obs.embedding)

      if state.observation_count < self.config.minimum_feature_count:
        return
      state.query_submitted = True
      vectors = list(state.quality)
      metadata = dict(obs.metadata)

    future = self.executor.submit(self._runQuery, obs, state, vectors, metadata)
    future.add_done_callback(self._logUnhandled)

  def prune(self, present_track_ids):
    """Flush tracks that left the stream (UUIDManager.pruneInactiveTracks)."""
    with self._lock:
      gone = [tid for tid in self._tracks if tid not in present_track_ids]
      retired = [self._tracks.pop(tid) for tid in gone]
    for tid in gone:
      self.stats["tracks_retired"] += 1
      self._flush(tid)
    with self._lock:
      for state in retired:
        if state.distinct_embeddings == 1:
          self.stats["tracks_single_embedding"] += 1

  def flush_stale(self, now=None):
    """Flush pending writes older than stale_feature_timeout_secs."""
    now = self.clock() if now is None else now
    with self._lock:
      stale = [tid for tid, since in self._pending_since.items()
               if now - since > self.config.stale_feature_timeout_secs]
      for tid in stale:
        self._pending_since.pop(tid, None)
    for tid in stale:
      self._flush(tid)

  def shutdown(self):
    """Flush every pending write (best effort). The executor is owned by the caller."""
    with self._lock:
      pending = list(self._pending)
    for tid in pending:
      self._flush(tid)

  def _stateFor(self, obs):
    state = self._tracks.get(obs.track_id)
    if state is not None:
      return state
    # Controller output renames a track when it rematches (provisional gid ->
    # matched gid, recorded in previous_ids_chain). Follow the rename so one
    # physical track keeps one state.
    for previous in obs.previous_ids:
      if previous in self._tracks:
        state = self._tracks.pop(previous)
        self._tracks[obs.track_id] = state
        if previous in self._pending:
          self._pending[obs.track_id] = self._pending.pop(previous)
        if previous in self._pending_since:
          self._pending_since[obs.track_id] = self._pending_since.pop(previous)
        self.stats["tracks_renamed"] += 1
        return state
    state = _TrackState()
    self._tracks[obs.track_id] = state
    self.stats["tracks_seen"] += 1
    return state

  def _ensureDimensions(self, embedding):
    dim = int(np.asarray(embedding).reshape(-1).shape[0])
    if dim == 0:
      self.stats["embeddings_rejected_empty"] += 1
      return False
    with self._dimensions_lock:
      if self._dimensions is None:
        try:
          self.adapter.ensureSchema(dim)
        except (ValueError, RuntimeError) as err:
          log.error(f"[reid-ingest] schema initialization failed: {err}")
          self.stats["schema_errors"] += 1
          return False
        self._dimensions = dim
        log.info(f"[reid-ingest] {self.scene_id}/{self.category}: "
                 f"inferred embedding dimensions {dim}")
        return True
      if dim != self._dimensions:
        self.stats["embeddings_rejected_dimension"] += 1
        return False
    return True

  def _isEnrollable(self, obs):
    """A local camera crop above the pixel-area gate."""
    return obs.bbox_px_area is not None and obs.bbox_px_area > self.config.minimum_bbox_area

  def _isQueryable(self, obs):
    if self._isEnrollable(obs):
      return True
    if obs.bbox_px_area is not None:
      return False  # local crop that failed the area gate
    if is_vetted_provenance(obs.provenance):
      return True
    return self.config.accept_unvetted_embeddings

  def _mayContributeEnrollment(self, obs):
    if not self.write_healthy:
      return False
    if not self._isQueryable(obs):
      return False
    return not is_upstream_enrollment_claim(obs.provenance)

  def _appendPendingEnrollment(self, obs, state):
    if not self._mayContributeEnrollment(obs):
      return
    if self._isEnrollable(obs):
      _append_unique(state.local_enrollment, obs.embedding)
    entry = self._pending.get(obs.track_id)
    if entry is not None:
      _append_unique(entry["reid_vectors"], obs.embedding)

  def _runQuery(self, obs, state, vectors, metadata):
    started = self.clock()
    try:
      scores = self.adapter.findMatches(
        obs.category, vectors, k_neighbors=QUERY_K_NEIGHBORS, **metadata)
    except Exception as err:  # matches UUIDManager: a failed query is a no-match
      log.error(f"[reid-ingest] findMatches failed for track {obs.track_id}: {err}")
      self.stats["query_errors"] += 1
      scores = []
    query_secs = self.clock() - started
    self.stats["queries"] += 1

    gid, similarity, per_vector = self.parseQueryResults(scores)
    with self._lock:
      # Look the state up by identity: the track may have been renamed while
      # the query was in flight.
      track_id = next((tid for tid, s in self._tracks.items() if s is state), None)
      if track_id is None:
        self.stats["tracks_left_before_decision"] += 1
        return None
      decision = self._decide(track_id, state, obs, gid, similarity, per_vector)
    decision["query_secs"] = query_secs
    # Best raw score in the result, even when it missed the threshold or the
    # majority vote: shows how close a no-match was.
    decision["best_score"], decision["best_gid"] = self._bestOverall(scores)
    decision["threshold"] = self.config.similarity_threshold
    if self.on_decision is not None:
      try:
        self.on_decision(decision)
      except Exception as err:
        log.error(f"[reid-ingest] decision callback failed: {err}")
    return decision

  def _decide(self, track_id, state, obs, gid, similarity, per_vector):
    live = {s.gid for tid, s in self._tracks.items() if tid != track_id and s.gid}
    matched = gid is not None and similarity is not None and gid not in live
    if gid is not None and gid in live:
      self.stats["gid_collisions"] += 1
      log.warning(f"[reid-ingest] candidate gid {gid} already live; "
                  f"treating track {track_id} as no-match")

    if matched:
      state.gid, state.similarity = gid, similarity
      self.stats["matches"] += 1
      vectors = self._enrollmentVectorsForMatch(state, similarity, per_vector)
    else:
      if state.gid is None:
        # A new person keeps the producer's track id as its identity, so the
        # id downstream consumers already show never changes on a no-match.
        state.gid = track_id if track_id not in live else str(uuid.uuid4())
      state.similarity = None
      self.stats["no_matches"] += 1
      vectors = state.enrollment
      if not vectors and not is_upstream_enrollment_claim(obs.provenance):
        vectors = []
        for promoted in state.quality:
          _append_unique(vectors, promoted)

    if self.write_healthy:
      self._pending[track_id] = {
        "gid": state.gid,
        "category": obs.category,
        "reid_vectors": list(vectors),
        "metadata": dict(obs.metadata),
      }
      self._pending_since[track_id] = self.clock()

    return {
      "scene_id": self.scene_id,
      "category": obs.category,
      "track_id": track_id,
      "gid": state.gid,
      "matched": matched,
      "similarity": state.similarity,
      "query_vectors": len(state.quality),
      "enrollment_vectors": len(vectors),
      "timestamp": obs.timestamp,
      "cameras": list(obs.cameras),
      "upstream_id": state.upstream_id,
      "upstream_reid_state": state.upstream_reid_state,
    }

  def _isExactRematchScore(self, score):
    if score is None:
      return False
    try:
      score = float(score)
    except (TypeError, ValueError):
      return False
    if not math.isfinite(score):
      return False
    if is_higher_better_metric(self.adapter.similarity_metric):
      return math.isclose(score, 1.0, rel_tol=0.0, abs_tol=COSINE_SIMILARITY_TOLERANCE)
    return score <= COSINE_SIMILARITY_TOLERANCE

  def _enrollmentVectorsForMatch(self, state, similarity, per_vector):
    """Port of UUIDManager._enrollmentVectorsForMatch."""
    vectors = []
    for local in state.local_enrollment:
      _append_unique(vectors, local)
    if per_vector is not None:
      for idx, vec in enumerate(state.quality):
        score = per_vector[idx] if idx < len(per_vector) else None
        if score is None or self._isExactRematchScore(score):
          continue
        if not _contains(state.enrollment, vec):
          continue
        _append_unique(vectors, vec)
      return vectors
    if self._isExactRematchScore(similarity):
      return vectors
    for vec in state.enrollment:
      _append_unique(vectors, vec)
    return vectors

  def parseQueryResults(self, similarity_scores, threshold=None):
    """Majority vote over per-vector best matches (UUIDManager.parseQueryResults)."""
    if threshold is None:
      threshold = self.config.similarity_threshold
    if not similarity_scores:
      return None, None, None
    if not isinstance(similarity_scores, list) or not all(
        isinstance(item, list) for item in similarity_scores):
      log.warning("[reid-ingest] unexpected findMatches result shape")
      return None, None, None

    metric = self.adapter.similarity_metric
    candidates = [self._bestCandidate(entities, metric) for entities in similarity_scores]
    qualifying = [(gid, value) for gid, value in candidates
                  if value is not None and is_similarity_match(value, threshold, metric)]
    if not qualifying:
      return None, None, None
    winner, count = collections.Counter(g for g, _ in qualifying).most_common(1)[0]
    if count < len(candidates) / 2:
      return None, None, None
    similarity = pick_best_metric_value([v for g, v in qualifying if g == winner], metric)
    per_vector = [self._bestScoreFor(entities, winner, metric) for entities in similarity_scores]
    return winner, similarity, per_vector

  @staticmethod
  def _bestCandidate(entities, metric):
    best = None
    for entity in entities or []:
      value = normalize_similarity_score(entity.get("_distance"), metric)
      if value is None or entity.get("uuid") is None:
        continue
      if best is None or (value > best[1] if is_higher_better_metric(metric) else value < best[1]):
        best = (entity["uuid"], value)
    return best or (None, None)

  def _bestOverall(self, similarity_scores):
    metric = self.adapter.similarity_metric
    best = (None, None)
    if not isinstance(similarity_scores, list):
      return best
    for entities in similarity_scores:
      if not isinstance(entities, list):
        continue
      gid, value = self._bestCandidate(entities, metric)
      if value is None:
        continue
      if best[0] is None or (value > best[0] if is_higher_better_metric(metric) else value < best[0]):
        best = (value, gid)
    return best

  @staticmethod
  def _bestScoreFor(entities, target, metric):
    best = None
    for entity in entities or []:
      if str(entity.get("uuid")) != str(target):
        continue
      value = normalize_similarity_score(entity.get("_distance"), metric)
      if value is None:
        continue
      if best is None or (value > best if is_higher_better_metric(metric) else value < best):
        best = value
    return best

  def _flush(self, track_id):
    """Port of UUIDManager._addNewFeaturesToDatabase."""
    with self._lock:
      entry = self._pending.pop(track_id, None)
      self._pending_since.pop(track_id, None)
    if not entry or not entry["reid_vectors"]:
      return
    vectors = entry["reid_vectors"][::max(1, self.config.feature_slice_size)]

    if not self.write_enabled:
      self.stats["shadow_writes"] += 1
      self.stats["shadow_vectors"] += len(vectors)
      log.info(f"[reid-ingest] shadow: would write {len(vectors)} vector(s) "
               f"for track {track_id} gid={entry['gid']}")
      return
    if not self.write_healthy:
      self.stats["writes_discarded_unhealthy"] += 1
      return

    epoch = self.write_epoch
    future = self.executor.submit(
      self._writeEntry, epoch, entry["gid"], track_id, entry["category"],
      vectors, entry["metadata"])
    future.add_done_callback(self._onWriteComplete)

  def _writeEntry(self, epoch, gid, track_id, category, vectors, metadata):
    with self._write_lock:
      if epoch != self.write_epoch or not self.write_healthy:
        raise ReidWriteSupersededError(f"superseded ReID write for track {track_id}")
      self.adapter.addEntry(gid, track_id, category, vectors, persist={}, **metadata)

  def _onWriteComplete(self, future):
    if future.cancelled():
      return
    try:
      future.result()
    except ReidWriteSupersededError:
      self.stats["writes_superseded"] += 1
      return
    except ReidNoValidVectorsError as err:
      self.stats["writes_no_valid_vectors"] += 1
      log.warning(f"[reid-ingest] write skipped (no valid vectors): {err}")
      return
    except ReidPartialWriteError as err:
      self._markUnhealthy(f"partial write: {err}", confirmed=True)
      self.stats["writes_partial"] += 1
      return
    except Exception as err:
      self._markUnhealthy(f"write failed: {err}")
      self.stats["write_errors"] += 1
      return
    with self._write_lock:
      self.write_confirmed = True
    self.stats["writes"] += 1

  def _markUnhealthy(self, reason, confirmed=False):
    with self._write_lock:
      if self.write_healthy:
        log.error(f"[reid-ingest] disabling writes for {self.scene_id}/"
                  f"{self.category}: {reason}")
      self.write_healthy = False
      self.write_epoch += 1
      if confirmed:
        self.write_confirmed = True

  @staticmethod
  def _logUnhandled(future):
    if future.cancelled():
      return
    err = future.exception()
    if err is not None:
      log.error(f"[reid-ingest] unhandled error in query worker: {err}")
