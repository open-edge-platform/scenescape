#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for PubSub callback wiring."""

import concurrent.futures
import struct
import threading
from unittest.mock import MagicMock

import pytest

from scene_common.mqtt import CHUNK_HEADER, PubSub

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

  def test_wrap_callback_replaces_client_under_contention(self, pubsub):
    """wrapCallback must consistently inject PubSub as first arg."""
    seen = []
    lock = threading.Lock()
    errors = []

    def cb(client, userdata, message):
      with lock:
        seen.append(client)

    wrapped = pubsub.wrapCallback(cb)

    def invoke():
      try:
        for _ in range(100):
          wrapped(object(), None, MagicMock())
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=invoke) for _ in range(6)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    assert not errors, f"wrapCallback race: {errors}"
    assert len(seen) == 600
    assert all(item is pubsub for item in seen)

  def test_receive_file_condition_vs_chunk_callback(self, pubsub):
    """chunkReceived notify path must stay consistent with receiveFile waiters."""
    errors = []
    topic = "scenescape/image/camera/cam-1"
    payload = b"abcdefgh"
    header = struct.pack(CHUNK_HEADER, len(payload), len(payload), 1, 0)

    # Drive receiveFile on one thread while injecting chunks on another.
    def receiver():
      try:
        data = pubsub.receiveFile(topic, timeout=2)
        assert data == bytearray(payload)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def sender():
      try:
        # Wait until receiveFile installs callback + condition.
        for _ in range(100):
          if hasattr(pubsub, 'receivedCondition') and pubsub.receivedCondition is not None:
            break
          threading.Event().wait(0.01)
        message = MagicMock()
        message.payload = header + payload
        pubsub.chunkReceived(pubsub, None, message)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    t_recv = threading.Thread(target=receiver)
    t_send = threading.Thread(target=sender)
    t_recv.start()
    t_send.start()
    t_recv.join(timeout=3.0)
    t_send.join(timeout=3.0)
    assert not errors, f"receiveFile race: {errors}"
