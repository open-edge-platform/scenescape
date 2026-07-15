# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Analytics event publisher interface.

Defines the abstract contract for publishing analytics results to MQTT.

Phase 4 introduces this interface so the analytics package can depend on it
without knowing how messages are actually dispatched.  Phase 6 will add a
concrete ``MqttAnalyticsEventPublisher`` that publishes directly without
going through the Controller.
"""


class AnalyticsEventPublisher:
  """Abstract interface for publishing analytics results.

  Subclasses implement the two publish hooks.  The Controller's existing
  ``publishDetections`` / ``publishEvents`` paths satisfy this contract in
  Phases 4–5; a standalone MQTT implementation will be added in Phase 6.
  """

  def publish_detections(self, topic: str, payload: bytes) -> None:
    """Publish a detections payload to *topic*.

    Args:
      topic:   MQTT topic string.
      payload: Serialized message bytes (typically JSON).
    """
    raise NotImplementedError

  def publish_event(self, topic: str, payload: bytes) -> None:
    """Publish a single analytics event to *topic*.

    Args:
      topic:   MQTT topic string.
      payload: Serialized message bytes (typically JSON).
    """
    raise NotImplementedError
