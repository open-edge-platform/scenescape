# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.event_publisher import publish_events
from analytics.state import AnalyticsStateStore


class TestEventPublisher:
  """Unit tests for analytics.event_publisher.publish_events."""

  def test_publish_events_publishes_region_events_and_clears_transient_event_lists(self):
    """Region events are published and objects/count queues are cleared afterward."""

    class FakeRegion:
      def __init__(self):
        self.uuid = 'roi-1'
        self.name = 'ROI'
        self.singleton_type = None

      def serialize(self):
        return {'name': self.name}

    region = FakeRegion()
    mock_publish = MagicMock()
    scene = SimpleNamespace(
      uid='scene-1',
      name='Test Scene',
      events={'objects': [('roi-1', region)]},
      analytics_state=AnalyticsStateStore(),
    )

    with patch('analytics.event_publisher._build_all_region_objs_list', return_value=({}, 0)), \
         patch('analytics.event_publisher._build_entered_objs_list'), \
         patch('analytics.event_publisher._build_exited_objs_list'), \
         patch('analytics.event_publisher._clear_sensor_values_on_exit'), \
         patch('analytics.event_publisher.Region', FakeRegion):
      publish_events(scene, '2026-01-01T00:00:01Z', mock_publish)

    assert mock_publish.call_count == 1
    assert 'objects' not in scene.events
    assert 'count' not in scene.events
