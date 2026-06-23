#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MQTT helper utilities for cluster analytics component tests.
"""

import queue
import json
import threading


def wait_for_message(client, topic_pattern, timeout=10.0):
  """
  Block until one MQTT message arrives on a topic matching topic_pattern.

  Uses a simple wildcard '#' subscription on the test client and filters
  by prefix so callers don't need to pre-subscribe.

  Returns the parsed JSON payload dict, or raises TimeoutError.
  """
  received = queue.Queue()

  original_on_message = client.on_message

  def _on_message(c, userdata, msg):
    if msg.topic.startswith(topic_pattern.rstrip("#").rstrip("+")):
      try:
        received.put(json.loads(msg.payload.decode("utf-8")))
      except Exception:
        pass
    if original_on_message:
      original_on_message(c, userdata, msg)

  client.on_message = _on_message

  try:
    return received.get(timeout=timeout)
  except queue.Empty:
    raise TimeoutError(
      f"No message arrived on topic '{topic_pattern}' within {timeout}s"
    )
  finally:
    client.on_message = original_on_message
