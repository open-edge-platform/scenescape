# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import unittest
from unittest import mock

from positioning_status import status_payload, status_topic

try:
  from scene_common.mqtt import PubSub
except ModuleNotFoundError as error:
  if error.name != "paho":
    raise
  PubSub = None


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

  @unittest.skipIf(PubSub is None, "paho-mqtt is installed in the service test image")
  def test_pubsub_configures_client_certificate_and_key(self):
    fake_client = mock.Mock()
    with mock.patch("scene_common.mqtt.initializeMqttClient", return_value=fake_client):
      PubSub(None, "client.crt", None, "broker", keyfile="client.key")
    fake_client.tls_set.assert_called_once_with(certfile="client.crt", keyfile="client.key")

  @unittest.skipIf(PubSub is None, "paho-mqtt is installed in the service test image")
  def test_pubsub_rejects_key_without_client_certificate(self):
    with self.assertRaises(ValueError):
      PubSub(None, None, None, "broker", keyfile="client.key")


if __name__ == "__main__":
  unittest.main()