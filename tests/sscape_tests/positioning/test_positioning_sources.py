# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Positioning source configuration and single-owner assignment validation."""

import json
import os
import tempfile
import unittest

from positioning.ptz_poller import LoggingSampleSink
from positioning.sources import (
  DEFAULT_POLL_INTERVAL_S, SourceConfigError, build_pollers, load_assignments, parse_sources,
  validate_assignments)


def source(**overrides):
  raw = {"type": "onvif_ptz", "host": "camera.example", "port": 2020,
         "credentials_file": "/run/secrets/onvif/cam-a.json"}
  raw.update(overrides)
  return raw


class TestParseSources(unittest.TestCase):
  def test_shell_config_without_sources(self):
    self.assertEqual(parse_sources({"resolver_id": "r1"}), (DEFAULT_POLL_INTERVAL_S, {}))

  def test_defaults(self):
    interval, sources = parse_sources({"resolver_id": "r1", "sources": {"cam-a": source()}})
    config = sources["cam-a"]
    self.assertEqual(interval, 0.2)
    self.assertEqual((config.scheme, config.port, config.move_status), ("http", 2020, "get_status"))
    self.assertIsNone(config.move_event)
    self.assertIs(config.tls_verify, True)

  def test_event_mode(self):
    _, sources = parse_sources({"resolver_id": "r1", "poll_interval_s": 0.1, "sources": {
      "cam-b": source(move_status="event",
                      move_event={"topic": "/PTZController/Move/", "data_item": "is_moving"})}})
    self.assertEqual(sources["cam-b"].move_event.topic, "PTZController/Move")

  def test_event_topic_rejects_empty_or_invalid_segments(self):
    for topic in ("/", "///", "PTZ//Move", "PTZ/+", "PTZ/#"):
      with self.subTest(topic=topic):
        config = {"resolver_id": "r1", "sources": {"cam-b": source(
          move_status="event", move_event={"topic": topic, "data_item": "is_moving"})}}
        with self.assertRaises(SourceConfigError):
          parse_sources(config)

  def test_rejections(self):
    invalid = [
      {"poll_interval_s": 0},
      {"poll_interval_s": float("nan")},
      {"unexpected": 1},
      {"sources": []},
      {"sources": {"cam/a": source()}},
      {"sources": {"cam-a": source(type="rtsp")}},
      {"sources": {"cam-a": source(host="user:pw@camera")}},
      {"sources": {"cam-a": source(host="")}},
      {"sources": {"cam-a": source(port=0)}},
      {"sources": {"cam-a": source(port=True)}},
      {"sources": {"cam-a": source(scheme="ftp")}},
      {"sources": {"cam-a": source(tls_ca_file="/ca.pem")}},
      {"sources": {"cam-a": source(request_timeout_s=-1)}},
      {"sources": {"cam-a": source(move_status="event")}},
      {"sources": {"cam-a": source(move_status="maybe")}},
      {"sources": {"cam-a": source(move_event={"topic": "x"})}},
      {"sources": {"cam-a": source(password="inline")}},
      {"sources": {"cam-a": source(credentials_file=None)}},
    ]
    for overrides in invalid:
      with self.subTest(overrides=overrides):
        with self.assertRaises(SourceConfigError):
          parse_sources({"resolver_id": "r1", **overrides})


class TestAssignments(unittest.TestCase):
  def write(self, directory, payload):
    path = os.path.join(directory, "assignments.json")
    with open(path, "w", encoding="utf-8") as handle:
      json.dump(payload, handle)
    return path

  def test_manifest_ignores_comments(self):
    with tempfile.TemporaryDirectory() as directory:
      path = self.write(directory, {"$comment": "x", "cam-a": "r1"})
      self.assertEqual(load_assignments(path), {"cam-a": "r1"})

  def test_manifest_rejects_invalid_entries(self):
    with tempfile.TemporaryDirectory() as directory:
      for payload in ([], {"cam-a": 1}, {"cam/a": "r1"}, {"cam-a": "r/1"}):
        with self.subTest(payload=payload):
          with self.assertRaises(SourceConfigError):
            load_assignments(self.write(directory, payload))

  def test_single_owner_validation(self):
    sources = {"cam-a": object()}
    validate_assignments("r1", sources, {"cam-a": "r1", "cam-z": "r2"})
    validate_assignments("r1", {}, {"cam-z": "r2"})
    for assignments in ({}, {"cam-a": "r2"}, {"cam-a": "r1", "cam-b": "r1"}):
      with self.subTest(assignments=assignments):
        with self.assertRaises(SourceConfigError):
          validate_assignments("r1", sources, assignments)


class TestBuildPollers(unittest.TestCase):
  def test_missing_credentials_fail_without_leaking_config(self):
    _, sources = parse_sources({"resolver_id": "r1", "sources": {
      "cam-a": source(credentials_file="/nonexistent/cam-a.json")}})
    with self.assertRaises(SourceConfigError):
      build_pollers(sources, 0.2, LoggingSampleSink())

  def test_builds_poller_and_optional_monitor(self):
    with tempfile.TemporaryDirectory() as directory:
      path = os.path.join(directory, "creds.json")
      with open(path, "w", encoding="utf-8") as handle:
        json.dump({"username": "user", "password": "pw"}, handle)
      _, sources = parse_sources({"resolver_id": "r1", "sources": {
        "cam-a": source(credentials_file=path, move_status="none"),
        "cam-b": source(credentials_file=path, move_status="event",
                        move_event={"topic": "PTZController/Move", "data_item": "is_moving"})}})
      pollers = {poller.source_id: poller for poller in build_pollers(sources, 0.2, LoggingSampleSink())}
    self.assertIsNone(pollers["cam-a"].move_monitor)
    self.assertEqual(pollers["cam-b"].move_monitor.topic, "PTZController/Move")
    self.assertNotEqual(pollers["cam-a"].adapter_instance_id, pollers["cam-b"].adapter_instance_id)


if __name__ == "__main__":
  unittest.main()
