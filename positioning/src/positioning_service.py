#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Entrypoint for the Positioning deployable."""

import argparse
import json
import logging
import os
import signal
import sys
import threading

from positioning.ptz_poller import LoggingSampleSink
from positioning.sources import (
  build_pollers, load_assignments, parse_sources, validate_assignments)
from positioning_status import status_payload, status_topic
from scene_common import log
from scene_common.mqtt import PubSub


def load_config(path):
  with open(path, "r", encoding="utf-8") as config_file:
    config = json.load(config_file)
  status_topic(config.get("resolver_id"))
  parse_sources(config)
  return config


def configure_library_logging():
  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
  library_logger = logging.getLogger("positioning")
  library_logger.addHandler(handler)
  library_logger.setLevel(logging.INFO)
  library_logger.propagate = False


def create_pollers(config, assignments_path):
  """Validate single-owner assignment and build pollers for this resolver's sources."""
  poll_interval_s, sources = parse_sources(config)
  if os.path.isfile(assignments_path):
    validate_assignments(config["resolver_id"], sources, load_assignments(assignments_path))
  elif sources:
    raise FileNotFoundError(f"Positioning assignment manifest not found: {assignments_path}")
  # The PTZ Resolver replaces this interim sink.
  return build_pollers(sources, poll_interval_s, LoggingSampleSink())


class PositioningService:
  """Owns broker liveness and the lifecycle of source pollers."""

  def __init__(self, config, broker, broker_auth, cert, keyfile, root_cert, pollers=()):
    self.resolver_id = config["resolver_id"]
    self.topic = status_topic(self.resolver_id)
    self.pollers = list(pollers)
    self._stop_workers = threading.Event()
    self._workers = []
    for credential_path in (cert, keyfile, root_cert):
      if not os.path.isfile(credential_path):
        raise FileNotFoundError(f"Required MQTT TLS file not found: {credential_path}")
    self.readiness_file = os.environ.get("POSITIONING_READINESS_FILE", "/tmp/positioning-ready")
    try:
      os.remove(self.readiness_file)
    except FileNotFoundError:
      pass
    self.client = PubSub(broker_auth, None, None, broker, keepalive=60)
    try:
      self.client.client.tls_set(ca_certs=root_cert, certfile=cert, keyfile=keyfile)
    except Exception as error:
      raise RuntimeError(f"Failed to configure TLS for MQTT broker {broker}") from error
    self.client.client.on_pre_connect = self.on_pre_connect
    self.client.client.on_connect = self.on_connect
    self.client.client.on_disconnect = self.on_disconnect

  def on_pre_connect(self, client, userdata):
    will = json.dumps(status_payload(self.resolver_id, "offline"))
    client.will_set(self.topic, will, qos=0, retain=True)

  def on_connect(self, client, userdata, flags, reason_code, properties=None):
    result = getattr(reason_code, "value", reason_code)
    if int(result) != 0:
      return
    payload = json.dumps(status_payload(self.resolver_id, "online"))
    client.publish(self.topic, payload, qos=0, retain=True)
    with open(self.readiness_file, "w", encoding="utf-8") as readiness_file:
      readiness_file.write("ready\n")
    log.info("Positioning connected to MQTT broker")

  def on_disconnect(self, *args):
    try:
      os.remove(self.readiness_file)
    except FileNotFoundError:
      pass
    log.warning("Positioning disconnected from MQTT broker")

  def on_sigterm(self, signum, frame):
    raise SystemExit(0)

  def start_workers(self):
    for poller in self.pollers:
      targets = [(poller.run, f"ptz-poll-{poller.source_id}")]
      if poller.move_monitor is not None:
        targets.append((poller.move_monitor.run, f"ptz-events-{poller.source_id}"))
      for target, name in targets:
        worker = threading.Thread(target=target, args=(self._stop_workers,), name=name, daemon=True)
        worker.start()
        self._workers.append(worker)

  def stop_workers(self, timeout_s=5.0):
    self._stop_workers.set()
    for worker in self._workers:
      worker.join(timeout_s)
    self._workers = []

  def run(self):
    previous_sigterm_handler = signal.signal(signal.SIGTERM, self.on_sigterm)
    try:
      self.start_workers()
      try:
        self.client.connect()
        self.client.loopForever()
      finally:
        self.stop_workers()
        if self.client.isConnected():
          payload = json.dumps(status_payload(self.resolver_id, "offline"))
          self.client.publish(self.topic, payload, qos=0, retain=True)
          self.client.disconnect()
    finally:
      signal.signal(signal.SIGTERM, previous_sigterm_handler)


def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--broker", default="broker.scenescape.intel.com",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--brokerauth", default="/run/secrets/positioning.auth",
                      help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--cert", default="/run/secrets/certs/scenescape-positioning.crt",
                      help="path to client certificate")
  parser.add_argument("--keyfile", default="/run/secrets/certs/scenescape-positioning.key",
                      help="path to client private key")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to CA certificate")
  parser.add_argument("--config", default="/app/config/positioning.json",
                      help="path to deployment-owned Positioning config")
  parser.add_argument("--assignments", default="/app/deployment/positioning-assignments.json",
                      help="path to the shared source_id -> resolver_id manifest")
  return parser


def main():
  args = build_argparser().parse_args()
  if not os.path.isfile(args.config):
    raise FileNotFoundError(f"Positioning config not found: {args.config}")
  config = load_config(args.config)
  log.info("Starting Positioning service")
  configure_library_logging()
  pollers = create_pollers(config, args.assignments)
  log.info(f"Configured PTZ sources: {[poller.source_id for poller in pollers]}")
  PositioningService(config, args.broker, args.brokerauth, args.cert, args.keyfile, args.rootcert,
                     pollers).run()


if __name__ == "__main__":
  main()
