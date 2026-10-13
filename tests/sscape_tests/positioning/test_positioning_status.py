# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
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

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_service_configures_client_certificate_and_key(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      cert = Path(temp_dir) / "client.crt"
      keyfile = Path(temp_dir) / "client.key"
      root_cert = Path(temp_dir) / "root.crt"
      for credential_path in (cert, keyfile, root_cert):
        credential_path.write_text("", encoding="utf-8")
      readiness_file = Path(temp_dir) / "positioning-ready"

      fake_pubsub = mock.Mock()
      with mock.patch.dict(os.environ, {"POSITIONING_READINESS_FILE": str(readiness_file)}):
        with mock.patch("positioning.PubSub", return_value=fake_pubsub) as pubsub_factory:
          PositioningService(
            {"resolver_id": "resolver-a"}, "broker", "positioning:secret",
            str(cert), str(keyfile), str(root_cert))

      pubsub_factory.assert_called_once_with(
        "positioning:secret", None, None, "broker", keepalive=60)
      fake_pubsub.client.tls_set.assert_called_once_with(
        ca_certs=str(root_cert), certfile=str(cert), keyfile=str(keyfile))


if __name__ == "__main__":
  unittest.main()
