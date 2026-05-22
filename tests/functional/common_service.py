# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time

from scene_common import log
from scene_common.mqtt import PubSub


class ServiceMqttTest:
  """! Shared MQTT helper for standalone service interaction tests.

  Manages a single PubSub connection, collects all received messages, and
  provides query helpers used by both controller and manager standalone tests.
  """

  MAX_WAIT_S = 30

  def __init__(self, params):
    """! Initialise the helper bound to the given connection parameters.

    @param    params    Dict of functional-test connection parameters from
                        the conftest fixture.
    """
    self.params = params
    self._messages = []
    self._lock = threading.Lock()
    self._client = None

  def connect(self, sub_topics):
    """! Create a PubSub client, subscribe to topics, and block until connected.

    @param    sub_topics    List of MQTT topic strings to subscribe to.
    """
    connected = threading.Event()

    def _on_connect(mqttc, _obj, _flags, rc):
      if rc == 0:
        for topic in sub_topics:
          mqttc.subscribe(topic)
        connected.set()

    def _on_message(_mqttc, _obj, msg):
      try:
        raw = msg.payload.decode('utf-8')
      except UnicodeDecodeError:
        raw = msg.payload.decode('utf-8', errors='replace')
        data = None
      else:
        try:
          data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
          data = None
      with self._lock:
        self._messages.append({'topic': msg.topic, 'payload': raw, 'data': data})

    self._client = PubSub(
      self.params['auth'], None, self.params['rootcert'],
      self.params['broker_url'], self.params['broker_port'],
    )
    self._client.onConnect = _on_connect
    self._client.onMessage = _on_message
    try:
      self._client.connect()
      self._client.loopStart()
      assert connected.wait(self.MAX_WAIT_S), "MQTT client did not connect within timeout"
    except Exception:
      self.disconnect()
      raise

  def disconnect(self):
    """! Disconnect and stop the MQTT client loop."""
    if self._client is not None:
      try:
        self._client.disconnect()
      finally:
        self._client.loopStop()
        self._client = None

  def publish(self, topic, payload):
    """! Publish a string payload to a topic.

    @param    topic     MQTT topic string.
    @param    payload   String payload to publish.
    """
    self._client.publish(topic, payload)

  def clear_messages(self):
    """! Discard all previously collected messages."""
    with self._lock:
      self._messages.clear()

  def wait_for_payload(self, expected_payload, timeout=None):
    """! Block until a message with the given raw string payload arrives.

    @param    expected_payload    Exact string to match against message payload.
    @param    timeout             Seconds to wait, defaults to MAX_WAIT_S.
    @return   True if the payload was received, False on timeout.
    """
    end = time.time() + (timeout or self.MAX_WAIT_S)
    while time.time() < end:
      with self._lock:
        if any(m['payload'] == expected_payload for m in self._messages):
          return True
      time.sleep(0.2)
    return False

  def has_any_message(self):
    """! Return True if any message has been received.

    @return   bool
    """
    with self._lock:
      return len(self._messages) > 0

  def has_objects(self):
    """! Return True if any JSON message contains a non-empty 'objects' list.

    @return   bool
    """
    with self._lock:
      return any(
        isinstance(m['data'], dict) and len(m['data'].get('objects', [])) > 0
        for m in self._messages
      )

  def get_tracked_ids(self):
    """! Return the set of object 'id' values seen across all received messages.

    Collects the 'id' field from every entry in the 'objects' array of each
    JSON message.  Used to verify whether a fresh tracker has reset its ID
    sequence.

    @return   set of object id values (any type, as received in the payload).
    """
    ids = set()
    with self._lock:
      for m in self._messages:
        if not isinstance(m['data'], dict):
          continue
        for obj in m['data'].get('objects', []):
          if 'id' in obj:
            ids.add(obj['id'])
    return ids
