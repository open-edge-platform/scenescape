# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run HTTP query API and MQTT ingest in one process."""

import os
import threading

import uvicorn

from scene_common import log
from scene_metadata.db import Database
from scene_metadata.ingest import MqttIngest
from scene_metadata.query_app import create_app
from scene_metadata.store import EventStore


def main() -> None:
  deployment_id = os.environ.get('SCENE_METADATA_DEPLOYMENT_ID', 'default')
  host = os.environ.get('SCENE_METADATA_HTTP_HOST', '0.0.0.0')
  port = int(os.environ.get('SCENE_METADATA_HTTP_PORT', '8080'))
  mqtt_enabled = os.environ.get('SCENE_METADATA_MQTT_ENABLED', 'true').lower() in (
    '1', 'true', 'yes', 'on')

  db = Database()
  db.open()
  store = EventStore(db)
  app = create_app(db)

  if mqtt_enabled:
    ingest = MqttIngest(store, deployment_id)
    try:
      ingest.connect()
    except Exception as err:
      log.warning(f'scene-metadata MQTT ingest disabled: {err}')
    else:
      thread = threading.Thread(target=ingest.loop_forever, name='scene-metadata-mqtt', daemon=True)
      thread.start()
      log.info('scene-metadata MQTT ingest thread started')

  uvicorn.run(app, host=host, port=port, log_level='info')


if __name__ == '__main__':
  main()
