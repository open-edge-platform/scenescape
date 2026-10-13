# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from positioning_status import status_payload, status_topic

try:
  from positioning import PositioningService
except ModuleNotFoundError as error:
  if error.name != "paho":
    raise
  PositioningService = None


class TestPositioningStatus(unittest.TestCase):
  def test_status_topic_uses_resolver_identity(self):
    self.assertEqual(status_topic("resolver-a"), "scenescape/positioning/status/resolver-a")

  def test_payload_contains_only_v1_status_fields(self):
    timestamp = datetime.datetime(2026, 10, 12, tzinfo=datetime.timezone.utc)
    payload = status_payload("resolver-a", "online", timestamp)
    self.assertEqual(payload, {
      "resolver_id": "resolver-a",
      "status": "online",
      "timestamp": "2026-10-12T00:00:00.000Z",
    })

  def test_invalid_resolver_id_is_rejected(self):
    for resolver_id in (None, "", "resolver/a", "resolver+one", "resolver#one"):
      with self.subTest(resolver_id=resolver_id):
        with self.assertRaises(ValueError):
          status_topic(resolver_id)

  def test_invalid_status_is_rejected(self):
    with self.assertRaises(ValueError):
      status_payload("resolver-a", "degraded")

  def test_naive_timestamp_is_rejected(self):
    with self.assertRaises(ValueError):
      status_payload("resolver-a", "online", datetime.datetime(2026, 10, 12))

  def _create_service(self, temp_dir):
    cert = Path(temp_dir) / "client.crt"
    keyfile = Path(temp_dir) / "client.key"
    root_cert = Path(temp_dir) / "root.crt"
    for credential_path in (cert, keyfile, root_cert):
      credential_path.write_text("", encoding="utf-8")
    readiness_file = Path(temp_dir) / "positioning-ready"
    fake_pubsub = mock.Mock()
    with mock.patch.dict(os.environ, {"POSITIONING_READINESS_FILE": str(readiness_file)}):
      with mock.patch("positioning.PubSub", return_value=fake_pubsub) as pubsub_factory:
        service = PositioningService(
          {"resolver_id": "resolver-a"}, "broker", "positioning:secret",
          str(cert), str(keyfile), str(root_cert))
    return service, fake_pubsub, readiness_file, pubsub_factory

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_service_configures_client_certificate_and_key(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      _, fake_pubsub, _, pubsub_factory = self._create_service(temp_dir)
      pubsub_factory.assert_called_once_with(
        "positioning:secret", None, None, "broker", keepalive=60)
      fake_pubsub.client.tls_set.assert_called_once_with(
        ca_certs=str(Path(temp_dir) / "root.crt"),
        certfile=str(Path(temp_dir) / "client.crt"),
        keyfile=str(Path(temp_dir) / "client.key"))

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_liveness_readiness_and_retained_status_across_reconnect(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, readiness_file, _ = self._create_service(temp_dir)
      topic = "scenescape/positioning/status/resolver-a"
      payloads = [
        {"resolver_id": "resolver-a", "status": "offline", "timestamp": "will-1"},
        {"resolver_id": "resolver-a", "status": "online", "timestamp": "online-1"},
        {"resolver_id": "resolver-a", "status": "offline", "timestamp": "will-2"},
        {"resolver_id": "resolver-a", "status": "online", "timestamp": "online-2"},
      ]
      client = fake_pubsub.client
      with mock.patch("positioning.status_payload", side_effect=payloads):
        client.on_pre_connect(client, None)
        client.on_connect(client, None, None, 0)
        self.assertEqual(readiness_file.read_text(encoding="utf-8"), "ready\n")

        service.on_disconnect(client, None, 1, None)
        self.assertFalse(readiness_file.exists())

        client.on_pre_connect(client, None)
        client.on_connect(client, None, None, 0)
        self.assertEqual(readiness_file.read_text(encoding="utf-8"), "ready\n")

      self.assertEqual(client.will_set.call_args_list, [
        mock.call(topic, json.dumps(payloads[0]), qos=0, retain=True),
        mock.call(topic, json.dumps(payloads[2]), qos=0, retain=True),
      ])
      self.assertEqual(client.publish.call_args_list, [
        mock.call(topic, json.dumps(payloads[1]), qos=0, retain=True),
        mock.call(topic, json.dumps(payloads[3]), qos=0, retain=True),
      ])

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_rejected_connection_does_not_publish_online_or_mark_ready(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, readiness_file, _ = self._create_service(temp_dir)
      service.on_connect(fake_pubsub.client, None, None, 5)
      fake_pubsub.client.publish.assert_not_called()
      self.assertFalse(readiness_file.exists())

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_graceful_shutdown_publishes_retained_offline_status(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, _, _ = self._create_service(temp_dir)
      will_payload = {"resolver_id": "resolver-a", "status": "offline", "timestamp": "will"}
      shutdown_payload = {
        "resolver_id": "resolver-a", "status": "offline", "timestamp": "shutdown",
      }
      fake_pubsub.isConnected.return_value = True
      fake_pubsub.connect.side_effect = lambda: fake_pubsub.client.on_pre_connect(
        fake_pubsub.client, None)
      with mock.patch("positioning.status_payload", side_effect=[will_payload, shutdown_payload]):
        service.run()

      fake_pubsub.client.will_set.assert_called_once_with(
        "scenescape/positioning/status/resolver-a", json.dumps(will_payload), qos=0, retain=True)
      fake_pubsub.publish.assert_called_once_with(
        "scenescape/positioning/status/resolver-a", json.dumps(shutdown_payload), qos=0, retain=True)
      fake_pubsub.disconnect.assert_called_once_with()


if __name__ == "__main__":
  unittest.main()
