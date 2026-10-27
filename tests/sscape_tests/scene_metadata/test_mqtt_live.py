# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live MQTT ingest into Timescale, then investigator timeline query."""

import json
import os
import time
import uuid

import paho.mqtt.client as mqtt
import pytest

from scene_metadata.db import Database
from scene_metadata.ingest import MqttIngest
from scene_metadata.store import EventStore

pytestmark = pytest.mark.test_name('SC-SceneMetadata-MQTT-Live')

pytestmark_live = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_MQTT_LIVE'),
  reason='Set SCENE_METADATA_MQTT_LIVE=1 and BROKER to a reachable broker',
)


@pytestmark_live
def test_mqtt_analytics_and_scene_land_on_timeline():
  deployment = f'mqtt-{uuid.uuid4().hex[:8]}'
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = deployment
  os.environ.setdefault('BROKER', '127.0.0.1:1883')
  os.environ['BROKERROOTCERT'] = '/tmp/scene-metadata-no-ca.pem'

  db = Database()
  db.open()
  store = EventStore(db)
  ingest = MqttIngest(store, deployment)
  ingest.connect()
  ingest._pubsub.loopStart()
  deadline = time.time() + 10
  while time.time() < deadline and not ingest._pubsub.isConnected():
    time.sleep(0.1)
  assert ingest._pubsub.isConnected()

  identity = f'gid-{uuid.uuid4().hex[:6]}'
  scene_id = 'mqtt-scene'
  publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
  publisher.connect('127.0.0.1', 1883, 30)
  publisher.loop_start()
  publisher.publish(
    f'scenescape/data/scene/{scene_id}/person',
    json.dumps({
      'timestamp': '2026-04-01T08:00:00Z',
      'objects': [{'id': identity, 'type': 'person'}],
    }),
  )
  publisher.publish(
    f'scenescape/event/region/{scene_id}/roi-live/count',
    json.dumps({
      'timestamp': '2026-04-01T08:00:05Z',
      'scene_id': scene_id,
      'region_id': 'roi-live',
      'entered': [{'id': identity, 'category': 'person'}],
      'exited': [],
      'counts': {'person': 1},
    }),
  )
  publisher.publish(
    f'scenescape/event/tripwire/{scene_id}/tw-live/objects',
    json.dumps({
      'timestamp': '2026-04-01T08:00:10Z',
      'objects': [{'id': identity, 'type': 'person'}],
    }),
  )

  types = set()
  deadline = time.time() + 15
  while time.time() < deadline:
    rows = store.identity_timeline(deployment_id=deployment, identity_id=identity)
    types = {row['event_type'] for row in rows}
    if {'track_started', 'region_enter', 'tripwire_cross'} <= types:
      break
    time.sleep(0.2)

  publisher.loop_stop()
  publisher.disconnect()
  ingest._pubsub.loopStop()
  db.close()

  assert {'track_started', 'region_enter', 'tripwire_cross'} <= types
