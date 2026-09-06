# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ChildSceneTest.wait_for_analytics_geometry readiness checks."""

from unittest.mock import MagicMock, patch

import pytest

from tests.functional.common_child import ChildSceneTest, GEOMETRY_READY_WAIT


def _helper():
  helper = ChildSceneTest({'resturl': 'x', 'rootcert': 'y', 'user': 'u', 'password': 'p'})
  helper.child_id = 'child-1'
  helper.roi_uid = 'roi-1'
  helper.tripwire_uid = 'tw-1'
  helper.sensor_uid = 'sensor-1'
  return helper


class TestWaitForAnalyticsGeometry:

  def test_raises_when_setup_incomplete(self):
    helper = ChildSceneTest({})
    with pytest.raises(AssertionError, match='setup_scenes'):
      helper.wait_for_analytics_geometry(MagicMock(), MagicMock())

  def test_polls_until_geometry_present_then_publishes_qos1(self):
    helper = _helper()
    client = MagicMock()
    rest = MagicMock()
    missing = MagicMock(statusCode=200)
    missing.get.return_value = []
    ready = MagicMock(statusCode=200)
    ready.get.side_effect = lambda key, default=None: {
      'regions': [{'uid': 'roi-1'}],
      'tripwires': [{'uid': 'tw-1'}],
      'sensors': [{'uid': 'sensor-1'}],
    }.get(key, default)
    rest.getScene.side_effect = [missing, ready]

    with patch('tests.functional.common_child.time.sleep'):
      helper.wait_for_analytics_geometry(client, rest)

    assert rest.getScene.call_count == 2
    client.publish.assert_called_once()
    assert client.publish.call_args.kwargs.get('qos') == 1

  def test_times_out_when_geometry_never_appears(self):
    helper = _helper()
    client = MagicMock()
    rest = MagicMock()
    empty = MagicMock(statusCode=200)
    empty.get.return_value = []
    rest.getScene.return_value = empty

    times = {'n': 0}

    def fake_time():
      times['n'] += 1
      return 0.0 if times['n'] == 1 else GEOMETRY_READY_WAIT + 1.0

    with patch('tests.functional.common_child.time.sleep'), \
         patch('tests.functional.common_child.time.time', side_effect=fake_time):
      with pytest.raises(AssertionError, match='not visible via REST'):
        helper.wait_for_analytics_geometry(client, rest)

    client.publish.assert_not_called()
