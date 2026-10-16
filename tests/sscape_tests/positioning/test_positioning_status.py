# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import json
import logging
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from positioning.ptz_poller import LoggingSampleSink
from positioning_status import status_payload, status_topic

try:
  from positioning_service import (
    PositioningService, configure_library_logging, create_pollers, load_config, main)
except ModuleNotFoundError as error:
  if error.name != "paho":
    raise
  PositioningService = None
  configure_library_logging = create_pollers = load_config = main = None


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

  def test_payload_uses_current_utc_time_when_omitted(self):
    payload = status_payload("resolver-a", "online")
    timestamp = datetime.datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    self.assertEqual(timestamp.utcoffset(), datetime.timedelta(0))
    self.assertEqual(timestamp.microsecond % 1000, 0)

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

  def test_invalid_timestamp_values_are_rejected(self):
    for timestamp in ("", 123):
      with self.subTest(timestamp=timestamp):
        with self.assertRaises(ValueError):
          status_payload("resolver-a", "online", timestamp)

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_load_config_validates_resolver_and_sources(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      config_path = Path(temp_dir) / "positioning.json"
      config = {"resolver_id": "resolver-a"}
      config_path.write_text(json.dumps(config), encoding="utf-8")
      self.assertEqual(load_config(config_path), config)

      for invalid in (
          {"resolver_id": "resolver/a"},
          {"resolver_id": "resolver-a", "sources": []},
      ):
        with self.subTest(config=invalid):
          config_path.write_text(json.dumps(invalid), encoding="utf-8")
          with self.assertRaises(ValueError):
            load_config(config_path)

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_configure_library_logging_sets_handler_and_level(self):
    with mock.patch("positioning_service.logging.StreamHandler") as handler_factory:
      with mock.patch("positioning_service.logging.Formatter") as formatter_factory:
        with mock.patch("positioning_service.logging.getLogger") as logger_factory:
          configure_library_logging()

    handler_factory.assert_called_once_with(sys.stdout)
    handler_factory.return_value.setFormatter.assert_called_once_with(formatter_factory.return_value)
    logger = logger_factory.return_value
    logger.addHandler.assert_called_once_with(handler_factory.return_value)
    logger.setLevel.assert_called_once_with(logging.INFO)
    self.assertFalse(logger.propagate)

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_main_loads_config_and_runs_service(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      config_path = Path(temp_dir) / "positioning.json"
      assignments_path = Path(temp_dir) / "assignments.json"
      config = {"resolver_id": "resolver-a"}
      config_path.write_text(json.dumps(config), encoding="utf-8")
      arguments = ["positioning_service", "--config", str(config_path),
                   "--assignments", str(assignments_path)]
      with mock.patch.object(sys, "argv", arguments):
        with mock.patch("positioning_service.configure_library_logging"):
          with mock.patch("positioning_service.create_pollers", return_value=[]) as poller_factory:
            with mock.patch("positioning_service.PositioningService") as service_factory:
              main()

      poller_factory.assert_called_once_with(config, str(assignments_path))
      service_factory.assert_called_once_with(
        config, "broker.scenescape.intel.com", "/run/secrets/positioning.auth",
        "/run/secrets/certs/scenescape-positioning.crt",
        "/run/secrets/certs/scenescape-positioning.key",
        "/run/secrets/certs/scenescape-ca.pem", [])
      service_factory.return_value.run.assert_called_once_with()

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_main_rejects_missing_config(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      config_path = Path(temp_dir) / "missing.json"
      with mock.patch.object(sys, "argv", ["positioning_service", "--config", str(config_path)]):
        with self.assertRaisesRegex(FileNotFoundError, "Positioning config not found"):
          main()

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_create_pollers_validates_assignment_manifest(self):
    config = {"resolver_id": "resolver-a", "sources": {"cam-a": {
      "type": "onvif_ptz", "host": "camera.example", "credentials_file": "/unused"}}}
    with tempfile.TemporaryDirectory() as temp_dir:
      assignments_path = Path(temp_dir) / "assignments.json"
      assignments_path.write_text(json.dumps({"cam-a": "resolver-a"}), encoding="utf-8")
      pollers = [object()]
      with mock.patch("positioning_service.build_pollers", return_value=pollers) as builder:
        self.assertIs(create_pollers(config, str(assignments_path)), pollers)
      sources = builder.call_args.args[0]
      self.assertEqual(sources["cam-a"].host, "camera.example")
      self.assertEqual(builder.call_args.args[1], 0.2)
      self.assertIsInstance(builder.call_args.args[2], LoggingSampleSink)

      assignments_path.write_text(json.dumps({"cam-a": "another-resolver"}), encoding="utf-8")
      with self.assertRaises(ValueError):
        create_pollers(config, str(assignments_path))

  def _create_service(self, temp_dir):
    cert = Path(temp_dir) / "client.crt"
    keyfile = Path(temp_dir) / "client.key"
    root_cert = Path(temp_dir) / "root.crt"
    for credential_path in (cert, keyfile, root_cert):
      credential_path.write_text("", encoding="utf-8")
    readiness_file = Path(temp_dir) / "positioning-ready"
    fake_pubsub = mock.Mock()
    with mock.patch.dict(os.environ, {"POSITIONING_READINESS_FILE": str(readiness_file)}):
      with mock.patch("positioning_service.PubSub", return_value=fake_pubsub) as pubsub_factory:
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
  def test_missing_client_credential_is_rejected(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      cert = Path(temp_dir) / "missing.crt"
      keyfile = Path(temp_dir) / "client.key"
      root_cert = Path(temp_dir) / "root.crt"
      keyfile.write_text("", encoding="utf-8")
      root_cert.write_text("", encoding="utf-8")
      with self.assertRaisesRegex(FileNotFoundError, "missing.crt"):
        PositioningService(
          {"resolver_id": "resolver-a"}, "broker", "positioning:secret",
          str(cert), str(keyfile), str(root_cert))

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_tls_setup_failure_is_wrapped(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      for filename in ("client.crt", "client.key", "root.crt"):
        (Path(temp_dir) / filename).write_text("", encoding="utf-8")
      fake_pubsub = mock.Mock()
      fake_pubsub.client.tls_set.side_effect = OSError("invalid certificate")
      with mock.patch.dict(os.environ, {"POSITIONING_READINESS_FILE": str(Path(temp_dir) / "ready")}):
        with mock.patch("positioning_service.PubSub", return_value=fake_pubsub):
          with self.assertRaisesRegex(RuntimeError, "Failed to configure TLS for MQTT broker") as error:
            PositioningService(
              {"resolver_id": "resolver-a"}, "broker", "auth",
              str(Path(temp_dir) / "client.crt"), str(Path(temp_dir) / "client.key"),
              str(Path(temp_dir) / "root.crt"))
      self.assertIsInstance(error.exception.__cause__, OSError)

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
      with mock.patch("positioning_service.status_payload", side_effect=payloads):
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
  def test_disconnect_without_readiness_file_is_safe(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, readiness_file, _ = self._create_service(temp_dir)
      service.on_disconnect(fake_pubsub.client, None, 1, None)
      self.assertFalse(readiness_file.exists())

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_start_workers_without_move_monitor(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, _, _, _ = self._create_service(temp_dir)
      poller = mock.Mock(source_id="cam-a", move_monitor=None)
      service.pollers = [poller]
      with mock.patch("positioning_service.threading.Thread") as thread_factory:
        service.start_workers()
        thread_factory.assert_called_once_with(
          target=poller.run, args=(service._stop_workers,), name="ptz-poll-cam-a", daemon=True)
        thread_factory.return_value.start.assert_called_once_with()
      service.stop_workers()
      thread_factory.return_value.join.assert_called_once_with(5.0)
      self.assertEqual(service._workers, [])

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_run_stops_workers_and_restores_signal_when_connect_fails(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, _, _ = self._create_service(temp_dir)
      fake_pubsub.connect.side_effect = RuntimeError("broker unavailable")
      fake_pubsub.isConnected.return_value = False
      original_sigterm_handler = signal.getsignal(signal.SIGTERM)
      with self.assertRaisesRegex(RuntimeError, "broker unavailable"):
        service.run()
      self.assertTrue(service._stop_workers.is_set())
      self.assertIs(signal.getsignal(signal.SIGTERM), original_sigterm_handler)

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_sigterm_publishes_retained_offline_status(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, _, _ = self._create_service(temp_dir)
      original_sigterm_handler = signal.getsignal(signal.SIGTERM)
      will_payload = {"resolver_id": "resolver-a", "status": "offline", "timestamp": "will"}
      shutdown_payload = {
        "resolver_id": "resolver-a", "status": "offline", "timestamp": "shutdown",
      }
      fake_pubsub.isConnected.return_value = True
      fake_pubsub.connect.side_effect = lambda: fake_pubsub.client.on_pre_connect(
        fake_pubsub.client, None)
      fake_pubsub.loopForever.side_effect = lambda: os.kill(os.getpid(), signal.SIGTERM)
      with mock.patch("positioning_service.status_payload", side_effect=[will_payload, shutdown_payload]):
        with self.assertRaises(SystemExit) as exit_info:
          service.run()

      self.assertEqual(exit_info.exception.code, 0)
      self.assertIs(signal.getsignal(signal.SIGTERM), original_sigterm_handler)
      fake_pubsub.client.will_set.assert_called_once_with(
        "scenescape/positioning/status/resolver-a", json.dumps(will_payload), qos=0, retain=True)
      fake_pubsub.publish.assert_called_once_with(
        "scenescape/positioning/status/resolver-a", json.dumps(shutdown_payload), qos=0, retain=True)
      fake_pubsub.disconnect.assert_called_once_with()

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_run_starts_and_stops_poller_workers(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      service, fake_pubsub, _, _ = self._create_service(temp_dir)
      poller = mock.Mock(source_id="cam-a")
      started = []
      poller.run.side_effect = lambda stop: (started.append("poll"), stop.wait(5))
      poller.move_monitor.run.side_effect = lambda stop: (started.append("events"), stop.wait(5))
      service.pollers = [poller]
      fake_pubsub.isConnected.return_value = False
      fake_pubsub.loopForever.side_effect = lambda: (time.sleep(0.1), None)[1]
      service.run()
      self.assertEqual(sorted(started), ["events", "poll"])
      self.assertTrue(service._stop_workers.is_set())
      self.assertEqual(service._workers, [])

  @unittest.skipIf(PositioningService is None, "paho-mqtt is installed in the service test image")
  def test_configured_sources_require_assignment_manifest(self):
    config = {"resolver_id": "resolver-a", "sources": {"cam-a": {
      "type": "onvif_ptz", "host": "camera.example", "credentials_file": "/nonexistent"}}}
    with self.assertRaises(FileNotFoundError):
      create_pollers(config, "/nonexistent/assignments.json")
    self.assertEqual(create_pollers({"resolver_id": "resolver-a"}, "/nonexistent/a.json"), [])


if __name__ == "__main__":
  unittest.main()
