# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Consume the scene-track MQTT stream and feed per-(scene, category) matchers.

Topic: ``scenescape/data/scene/{scene_id}/{category}`` (``PubSub.DATA_SCENE``).
Each message lists every object currently tracked for that scene and
category, so a track missing from a message has left and is flushed.

Environment:
  REID_INGEST_ENABLED          "false" to run the gRPC API only (default on)
  REID_INGEST_WRITE_ENABLED    "false" for shadow mode: match and report, never
                               call addEntry (default on). Use it only if another
                               writer (e.g. Controller ReID) shares the store.
  REID_INGEST_ACCEPT_UNVETTED  "false" to drop embeddings that have neither a
                               pixel bbox nor vetted provenance (default true)
  REID_INGEST_TOPIC            subscription (default scenescape/data/scene/+/+)
  REID_INGEST_SCENES           optional comma-separated scene_id allowlist
  REID_INGEST_WORKERS          query/write worker threads (default 4)
  REID_CONFIG_PATH             reid-config.json (default: Controller defaults)
  REID_MQTT_BROKER             broker host[:port] (default broker.scenescape.intel.com)
  REID_MQTT_AUTH               auth file or user:password (default /run/secrets/controller.auth)
  REID_MQTT_ROOT_CERT          CA file (default /run/secrets/certs/scenescape-ca.pem)
"""

import concurrent.futures
import datetime
import json
import os
import threading
import time
from collections import Counter

from scene_common import log
from scene_common.mqtt import PubSub
from reid.embedding import decode_reid_payload
from reid.matcher import MatcherConfig, TrackMatcher, TrackObservation

DEFAULT_TOPIC = "scenescape/data/scene/+/+"
# One message per ReID decision. Analytics maps track_id -> gid from these and
# publishes the gid on the regulated topic (as the Controller's scene output did).
_TOPIC_PREFIX = ("scenescape", "data", "scene")
_STATS_LOG_INTERVAL_SECS = 30.0


def env_flag(name, default=False):
  value = os.getenv(name)
  if value is None:
    return default
  return value.strip().lower() in ("1", "true", "yes", "on")


def load_reid_config(path=None):
  path = path or os.getenv("REID_CONFIG_PATH")
  if not path:
    return {}
  try:
    with open(path) as handle:
      return json.load(handle)
  except (OSError, ValueError) as err:
    log.warning(f"[reid-ingest] could not read reid config {path}: {err}; using defaults")
    return {}


class TrackIngest:
  """Route scene-track messages to one TrackMatcher per (scene_id, category)."""

  def __init__(self, adapter_factory, config: MatcherConfig, write_enabled=False,
               scenes=None, executor=None, clock=time.time):
    self.adapter_factory = adapter_factory
    self.config = config
    self.write_enabled = write_enabled
    self.scenes = set(scenes) if scenes else None
    self.executor = executor
    self.clock = clock
    self.stats = Counter()
    self._matchers = {}
    self._lock = threading.Lock()
    self._last_stats_log = clock()
    self.pubsub = None

  @staticmethod
  def _announce(message):
    """Log at a level that is always shown: scene_common.log hides INFO by default."""
    emit = getattr(log, "log", None) or log.warning
    emit(message)

  @staticmethod
  def _parse_scene_topic(topic):
    """Return (scene_id, category) for a DATA_SCENE topic, else None."""
    parts = topic.split("/")
    if len(parts) != 5 or tuple(parts[:3]) != _TOPIC_PREFIX:
      return None
    return parts[3], parts[4]

  @staticmethod
  def _bbox_area(obj):
    bbox = obj.get("bounding_box_px")
    if not isinstance(bbox, dict):
      return None
    try:
      return float(bbox["width"]) * float(bbox["height"])
    except (KeyError, TypeError, ValueError):
      return None

  @classmethod
  def _parse_scene_message(cls, payload, category=None, stats=None):
    """
    Turn one scene-track message into TrackObservations.

    @param   payload   bytes/str JSON, or an already-decoded dict
    @param   category  topic category, used when an object omits its own
    @param   stats     optional Counter for decode problems
    @return  (message_timestamp, [TrackObservation, ...])
    """
    stats = stats if stats is not None else Counter()
    data = json.loads(payload) if isinstance(payload, (bytes, bytearray, str)) else payload
    timestamp = data.get("timestamp")
    observations = []
    for obj in data.get("objects") or []:
      track_id = obj.get("id")
      if track_id is None:
        stats["objects_without_id"] += 1
        continue
      metadata = obj.get("metadata") or {}
      embedding = provenance = None
      if isinstance(metadata, dict) and metadata.get("reid") is not None:
        try:
          embedding, provenance = decode_reid_payload(metadata["reid"])
        except ValueError as err:
          stats["embedding_decode_errors"] += 1
          log.debug(f"[reid-ingest] bad embedding on {track_id}: {err}")
      semantic = ({k: v for k, v in metadata.items() if k != "reid"}
                  if isinstance(metadata, dict) else {})
      chain = obj.get("previous_ids_chain") or []
      observations.append(TrackObservation(
        track_id=str(track_id),
        category=obj.get("category") or category or "object",
        embedding=embedding,
        provenance=provenance,
        metadata=semantic,
        bbox_px_area=cls._bbox_area(obj),
        timestamp=timestamp,
        cameras=list(obj.get("visibility") or []),
        upstream_reid_state=obj.get("reid_state"),
        previous_ids=[str(c["id"]) for c in chain if isinstance(c, dict) and c.get("id")],
      ))
    return timestamp, observations

  @staticmethod
  def _decision_message(decision, decided_at_epoch):
    """Wire format for one identity decision."""
    decided_at = datetime.datetime.fromtimestamp(decided_at_epoch, datetime.timezone.utc)
    return {
      "scene_id": decision["scene_id"],
      "category": decision["category"],
      "track_id": decision["track_id"],
      "gid": decision["gid"],
      "matched": bool(decision["matched"]),
      "reid_state": decision.get("reid_state", "matched" if decision["matched"] else "query_no_match"),
      "unique_id_count": decision.get("unique_id_count", 0),
      "similarity": decision["similarity"],
      "timestamp": decision.get("timestamp"),
      "decided_at": decided_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }

  def handle_message(self, topic, payload):
    parsed = self._parse_scene_topic(topic)
    if parsed is None:
      self.stats["messages_ignored_topic"] += 1
      return
    scene_id, category = parsed
    if self.scenes is not None and scene_id not in self.scenes:
      self.stats["messages_ignored_scene"] += 1
      return
    try:
      _, observations = self._parse_scene_message(payload, category, self.stats)
    except (ValueError, TypeError, AttributeError) as err:
      self.stats["messages_malformed"] += 1
      log.warning(f"[reid-ingest] malformed message on {topic}: {err}")
      return
    self.stats["messages"] += 1
    self.stats["objects"] += len(observations)
    self._matcherFor(scene_id, category).process_frame(observations)
    self._maybeLogStats()

  def _matcherFor(self, scene_id, category):
    key = (scene_id, category)
    with self._lock:
      matcher = self._matchers.get(key)
      if matcher is None:
        adapter = self.adapter_factory()
        adapter.connect()
        matcher = TrackMatcher(
          adapter, self.config, scene_id=scene_id, category=category,
          write_enabled=self.write_enabled, executor=self.executor,
          on_decision=self._onDecision, clock=self.clock,
          on_state=self._publishDecision)
        self._matchers[key] = matcher
        self._announce(f"[reid-ingest] started matcher for scene={scene_id} "
                  f"category={category} (writes {'on' if self.write_enabled else 'off'})")
      return matcher

  def _onDecision(self, decision):
    self.stats["decisions"] += 1
    self._publishDecision(decision)
    upstream = decision.get("upstream_reid_state")
    if upstream in ("matched", "query_no_match"):
      # Stream is Controller output: compare against its decision.
      agrees = (decision["matched"] and upstream == "matched"
                and decision["gid"] == decision["upstream_id"]) or (
                  not decision["matched"] and upstream == "query_no_match")
      self.stats["parity_agree" if agrees else "parity_disagree"] += 1
    best = decision.get("best_score")
    best_txt = "none" if best is None else f"{best:.3f}"
    if decision["matched"]:
      self._announce(
        f"[reid-ingest] MATCH scene={decision['scene_id']} track={decision['track_id']} "
        f"-> gid={decision['gid']} similarity={decision['similarity']:.3f} "
        f"(threshold={decision['threshold']}) vectors={decision['query_vectors']} "
        f"cameras={decision['cameras']} query_secs={decision['query_secs']:.3f}")
    else:
      self._announce(
        f"[reid-ingest] NO MATCH scene={decision['scene_id']} track={decision['track_id']} "
        f"-> new gid={decision['gid']} best_score={best_txt} best_gid={decision.get('best_gid')} "
        f"(threshold={decision['threshold']}) vectors={decision['query_vectors']} "
        f"query_secs={decision['query_secs']:.3f}")

  def _publishDecision(self, decision):
    if self.pubsub is None:
      return
    payload = self._decision_message(decision, self.clock())
    topic = PubSub.formatTopic(PubSub.DATA_REID, scene_id=decision["scene_id"],
                   thing_type=decision["category"])
    try:
      self.pubsub.publish(topic, json.dumps(payload), qos=1)
      self.stats["decisions_published"] += 1
    except Exception as err:
      self.stats["decision_publish_errors"] += 1
      log.error(f"[reid-ingest] failed to publish decision on {topic}: {err}")

  def snapshot(self):
    """Aggregate ingest + matcher counters (for the IngestStats RPC and logs)."""
    total = Counter(self.stats)
    with self._lock:
      matchers = list(self._matchers.items())
    for _, matcher in matchers:
      total.update(matcher.stats)
    return {
      "write_enabled": self.write_enabled,
      "matchers": [f"{s}/{c}" for (s, c), _ in matchers],
      "unhealthy_matchers": [f"{s}/{c}" for (s, c), m in matchers if not m.write_healthy],
      "counters": dict(total),
      "unique_id_counts": {f"{s}/{c}": m.unique_id_count for (s, c), m in matchers},
    }

  def _maybeLogStats(self):
    now = self.clock()
    if now - self._last_stats_log < _STATS_LOG_INTERVAL_SECS:
      return
    self._last_stats_log = now
    self._announce(f"[reid-ingest] stats {self.snapshot()['counters']}")

  def start(self, pubsub, topic=DEFAULT_TOPIC):
    """Subscribe on connect (so reconnects resubscribe) and start the loop."""
    self.pubsub = pubsub

    def on_connect(client, userdata, flags, rc):
      if rc != 0:
        log.error(f"[reid-ingest] MQTT connect failed rc={rc}")
        return
      client.addCallback(topic, self._onMessage)
      self._announce(f"[reid-ingest] subscribed to {topic}")

    pubsub.onConnect = on_connect
    pubsub.connect()
    pubsub.loopStart()

  def _onMessage(self, client, userdata, message):
    try:
      self.handle_message(message.topic, message.payload)
    except Exception as err:  # never kill the MQTT network thread
      self.stats["handler_errors"] += 1
      log.error(f"[reid-ingest] error handling {message.topic}: {err}")

  def stop(self):
    if self.pubsub is not None:
      self.pubsub.loopStop()
      self.pubsub.disconnect()
    with self._lock:
      matchers = list(self._matchers.values())
    for matcher in matchers:
      matcher.shutdown()
    if self.executor is not None:
      self.executor.shutdown(wait=True)


def build_from_env(adapter_factory):
  """Create and start ingest from REID_* environment, or return None if disabled."""
  if not env_flag("REID_INGEST_ENABLED", True):
    log.info("[reid-ingest] disabled by REID_INGEST_ENABLED=false; serving gRPC API only")
    return None

  from scene_common.mqtt import PubSub  # paho is only needed when ingest runs

  config = MatcherConfig.from_reid_config(
    load_reid_config(),
    accept_unvetted_embeddings=env_flag("REID_INGEST_ACCEPT_UNVETTED", True))
  write_enabled = env_flag("REID_INGEST_WRITE_ENABLED", True)
  scenes = [s.strip() for s in os.getenv("REID_INGEST_SCENES", "").split(",") if s.strip()]
  workers = int(os.getenv("REID_INGEST_WORKERS", "4"))

  if config.accept_unvetted_embeddings:
    log.warning(
      "[reid-ingest] scene tracks carry no pixel bbox; accepting embeddings without "
      "bbox/provenance gating (REID_INGEST_ACCEPT_UNVETTED=true)")
  if not write_enabled:
    log.warning("[reid-ingest] shadow mode (REID_INGEST_WRITE_ENABLED=false): "
                "matching only, no descriptors will be stored")

  ingest = TrackIngest(
    adapter_factory, config, write_enabled=write_enabled, scenes=scenes,
    executor=concurrent.futures.ThreadPoolExecutor(max_workers=workers))
  pubsub = PubSub(
    os.getenv("REID_MQTT_AUTH", "/run/secrets/controller.auth"),
    None,
    os.getenv("REID_MQTT_ROOT_CERT", "/run/secrets/certs/scenescape-ca.pem"),
    os.getenv("REID_MQTT_BROKER", "broker.scenescape.intel.com"),
    keepalive=60)
  ingest.start(pubsub, os.getenv("REID_INGEST_TOPIC", DEFAULT_TOPIC))
  return ingest
