#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for PubSub callback wiring."""

import concurrent.futures
from unittest.mock import MagicMock

import pytest

from scene_common.mqtt import PubSub

TEST_NAME = "NEX-T28258"


@pytest.fixture
def pubsub():
  # Bypass TLS/broker setup; wire a mock paho client directly.
  ps = PubSub.__new__(PubSub)
  ps.broker = "localhost"
  ps.port = 1883
  ps.keepalive = 60
  ps.client = MagicMock()
  ps.client.subscribe.return_value = (0, 1)
  ps.client.unsubscribe.return_value = (0, 1)
  ps.client.message_callback_add = MagicMock()
  ps.client.message_callback_remove = MagicMock()
  return ps


class TestPubSubCallbackConcurrency:
  def test_concurrent_add_and_remove_callback(self, pubsub):
    """addCallback/removeCallback must not crash under concurrent registration."""
    errors = []

    def adder(i):
      try:
        topic = f"scenescape/data/camera/cam-{i % 10}"
        pubsub.addCallback(topic, lambda *_a, **_k: None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def remover(i):
      try:
        topic = f"scenescape/data/camera/cam-{i % 10}"
        pubsub.removeCallback(topic)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
      futures = [pool.submit(adder, i) for i in range(80)]
      futures += [pool.submit(remover, i) for i in range(80)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"add/removeCallback race: {errors}"
    assert pubsub.client.message_callback_add.call_count == 80
    assert pubsub.client.message_callback_remove.call_count == 80
    # Negative: remove of a never-added topic must not raise.
    pubsub.removeCallback("scenescape/data/camera/never-registered")
