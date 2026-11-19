#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Collect scene messages and assert a stable global ID across ReID controllers."""

import json
import threading
import time
from dataclasses import dataclass

from scene_common.mqtt import PubSub

# Objects still collecting features have no usable global ID once warm-up has ended.
UNRESOLVED_STATES = frozenset({"pending_collection"})


@dataclass(frozen=True)
class Observation:
  """One object with a nonempty global ID seen in a scene message."""
  topic: str
  received_at: float
  source: str
  gid: str
  reid_state: str
  qualifying: bool


class SceneIdentityCollector:
  """Record scene-topic objects and retain every collection error.

  Messages seen before end_warmup() never qualify for the identity set. Decode
  failures, callback exceptions and unexpected objects are kept in errors()
  rather than dropped, and unexpected objects never reach the target ID set.
  """

  def __init__(self, pubsub=None, scene_uid=None, target_category="person",
               source_resolver=None):
    """
    @param pubsub           Connected PubSub; only needed when used as a context manager.
    @param scene_uid        Scene whose topics are subscribed to.
    @param target_category  The only object category and thing_type accepted.
    @param source_resolver  Optional callable(topic, data) -> publisher name, used
                            when ingest() is not given a source.
    """
    self._pubsub = pubsub
    self._scene_uid = scene_uid
    self._target_category = target_category
    self._source_resolver = source_resolver
    self._lock = threading.Lock()
    self._warmup_ended = False
    self._message_count = 0
    self._observations = []
    self._errors = []

  def __enter__(self):
    topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=self._scene_uid, thing_type="+")
    self._topic = topic
    self._pubsub.addCallback(topic, self._on_message)
    return self

  def __exit__(self, *exc):
    self._pubsub.removeCallback(self._topic)

  def _on_message(self, client, userdata, message):
    try:
      self.ingest(message.topic, message.payload)
    except Exception as err:
      self._add_error(f"callback error on {getattr(message, 'topic', '?')}: {err!r}")

  def _add_error(self, text):
    with self._lock:
      self._errors.append(text)

  def end_warmup(self):
    """Messages ingested from now on may qualify for the identity set."""
    with self._lock:
      self._warmup_ended = True

  def ingest(self, topic, payload, source=None, received_at=None):
    """Record one scene message; usable directly without MQTT."""
    received_at = time.monotonic() if received_at is None else received_at
    try:
      if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
      data = json.loads(payload)
    except (ValueError, TypeError) as err:
      self._add_error(f"decode error on {topic}: {err}")
      return

    thing_type = topic.rsplit("/", 1)[-1]
    if thing_type != self._target_category:
      self._add_error(f"unexpected thing_type '{thing_type}' on {topic}")
      return
    objects = data.get("objects", []) if isinstance(data, dict) else None
    if not isinstance(objects, list):
      self._add_error(f"unexpected payload shape on {topic}: {type(data).__name__}")
      return

    if source is None and self._source_resolver is not None:
      source = self._source_resolver(topic, data)
    source = source or "unknown"

    with self._lock:
      warmup = not self._warmup_ended
      self._message_count += 1
    for obj in objects:
      self._ingest_object(topic, obj, source, received_at, warmup)

  def _ingest_object(self, topic, obj, source, received_at, warmup):
    if not isinstance(obj, dict):
      self._add_error(f"unexpected object on {topic}: not a JSON object")
      return
    category = obj.get("category")
    if category is not None and category != self._target_category:
      self._add_error(
        f"unexpected object on {topic}: category '{category}', id {obj.get('id')!r}")
      return
    gid = obj.get("id")
    if gid is not None and not isinstance(gid, str):
      self._add_error(f"unexpected object on {topic}: non-string id {gid!r}")
      return
    if not gid or not gid.strip():
      return

    state = obj.get("reid_state")
    qualifying = not warmup and state not in UNRESOLVED_STATES
    with self._lock:
      self._observations.append(
        Observation(topic, received_at, source, gid, state, qualifying))

  def message_count(self):
    with self._lock:
      return self._message_count

  def errors(self):
    with self._lock:
      return list(self._errors)

  def observations(self):
    with self._lock:
      return list(self._observations)

  def qualifying_ids(self):
    """Distinct nonempty global IDs seen after warm-up."""
    return {o.gid for o in self.observations() if o.qualifying}

  def excluded_ids(self):
    """Nonempty global IDs seen only as warm-up or unresolved observations."""
    return {o.gid for o in self.observations() if not o.qualifying}

  def qualifying_sources(self):
    """Publisher name -> number of qualifying observations."""
    counts = {}
    for obs in self.observations():
      if obs.qualifying:
        counts[obs.source] = counts.get(obs.source, 0) + 1
    return counts


def _describe_ids(collector):
  """One line per qualifying ID with counts, sources and receive-time span."""
  by_gid = {}
  for obs in collector.observations():
    if obs.qualifying:
      by_gid.setdefault(obs.gid, []).append(obs)
  lines = []
  for gid in sorted(by_gid):
    group = by_gid[gid]
    sources = sorted({o.source for o in group})
    first = min(o.received_at for o in group)
    last = max(o.received_at for o in group)
    lines.append(
      f"  {gid}: {len(group)} messages, sources={sources}, t={first:.3f}..{last:.3f}")
  return "\n".join(lines)


def assert_single_global_id(collector, required_sources=()):
  """Fail unless exactly one nonempty post-warm-up global ID was observed cleanly.

  @param collector         A SceneIdentityCollector with the capture window ingested.
  @param required_sources  Publisher names that must each have a qualifying message.
  @return  The single observed global ID.
  """
  problems = []
  errors = collector.errors()
  if errors:
    problems.append(f"{len(errors)} collection error(s):\n" +
                    "\n".join(f"  {e}" for e in errors))

  ids = collector.qualifying_ids()
  if not ids:
    problems.append(
      f"no qualifying global ID observed ({collector.message_count()} messages; "
      f"excluded warm-up/unresolved IDs: {sorted(collector.excluded_ids())})")
  elif len(ids) > 1:
    problems.append(
      f"global ID split, observed {sorted(ids)}:\n{_describe_ids(collector)}")

  seen_sources = collector.qualifying_sources()
  missing = [s for s in required_sources if s not in seen_sources]
  if missing:
    problems.append(
      f"no qualifying message from {missing}; observed sources: {sorted(seen_sources)}")

  if problems:
    raise AssertionError("\n".join(problems))
  return next(iter(ids))
