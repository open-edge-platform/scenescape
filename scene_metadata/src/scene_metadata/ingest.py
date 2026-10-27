# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT ingest for scene track (Option A) and analytics region/tripwire events."""

import json
import os
import threading
from collections import defaultdict

from scene_common import log
from scene_common.mqtt import PubSub

from scene_metadata.normalize import analytics_event_envelopes, track_lifecycle_events
from scene_metadata.store import EventStore
from scene_metadata.topics import parse_analytics_event_topic, parse_scene_topic

SCENE_TOPIC = os.environ.get(
  'SCENE_METADATA_SCENE_TOPIC', 'scenescape/data/scene/+/+')
REGION_TOPIC = os.environ.get(
  'SCENE_METADATA_REGION_TOPIC', 'scenescape/event/region/+/+/+')
TRIPWIRE_TOPIC = os.environ.get(
  'SCENE_METADATA_TRIPWIRE_TOPIC', 'scenescape/event/tripwire/+/+/+')


class MqttIngest:
  """Subscribe to scene + analytics topics and persist normalized events."""

  def __init__(self, store: EventStore, deployment_id: str):
    self._store = store
    self._deployment_id = deployment_id
    self._track_state: dict[tuple[str, str], set[str]] = defaultdict(set)
    self._lock = threading.Lock()
    self._pubsub: PubSub | None = None
    self._messages = 0

  @property
  def messages_handled(self) -> int:
    return self._messages

  def connect(self) -> None:
    broker = os.environ.get('BROKER') or os.environ.get('SCENE_METADATA_MQTT_BROKER')
    auth = os.environ.get('BROKERAUTH') or os.environ.get('SCENE_METADATA_MQTT_AUTH')
    cert = os.environ.get('BROKERCERT') or os.environ.get('SCENE_METADATA_MQTT_CERT')
    rootcert = os.environ.get('BROKERROOTCERT', '/run/secrets/certs/scenescape-ca.pem')
    self._pubsub = PubSub(auth, cert, rootcert, broker, keepalive=60)
    self._pubsub.onConnect = self._on_connect
    self._pubsub.onMessage = self._on_message
    self._pubsub.connect()

  def loop_forever(self) -> None:
    if self._pubsub is None:
      raise RuntimeError('MQTT ingest is not connected')
    self._pubsub.loopForever()

  def _on_connect(self, _userdata=None, _flags=None, _rc=None, *_args):
    assert self._pubsub is not None
    self._pubsub.subscribe(SCENE_TOPIC)
    self._pubsub.subscribe(REGION_TOPIC)
    self._pubsub.subscribe(TRIPWIRE_TOPIC)
    log.info(
      f'scene-metadata ingest subscribed: {SCENE_TOPIC}, {REGION_TOPIC}, {TRIPWIRE_TOPIC}')

  def _on_message(self, _client, _userdata, message):
    topic = message.topic
    try:
      payload = json.loads(message.payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
      log.warning(f'scene-metadata ingest skipped non-JSON on {topic}: {err}')
      return
    if not isinstance(payload, dict):
      return

    events = self._normalize(topic, payload)
    if events:
      self._store.insert_events(events)
    self._messages += 1

  def _normalize(self, topic: str, payload: dict):
    scene_topic = parse_scene_topic(topic)
    if scene_topic is not None:
      key = (scene_topic.scene_id, scene_topic.category)
      with self._lock:
        previous = set(self._track_state[key])
        events, current = track_lifecycle_events(
          topic=scene_topic,
          payload=payload,
          previous_ids=previous,
          deployment_id=self._deployment_id,
        )
        self._track_state[key] = current
      return events

    analytics_topic = parse_analytics_event_topic(topic)
    if analytics_topic is not None:
      return analytics_event_envelopes(
        topic=analytics_topic,
        payload=payload,
        deployment_id=self._deployment_id,
      )
    return []
