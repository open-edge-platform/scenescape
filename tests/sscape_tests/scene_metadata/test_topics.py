# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from scene_metadata.topics import parse_analytics_event_topic, parse_scene_topic

pytestmark = pytest.mark.test_name('SC-SceneMetadata-Topics')


def test_parse_scene_topic():
  parsed = parse_scene_topic('scenescape/data/scene/abc-123/person')
  assert parsed is not None
  assert parsed.scene_id == 'abc-123'
  assert parsed.category == 'person'


def test_parse_scene_topic_rejects_non_scene():
  assert parse_scene_topic('scenescape/event/region/x/y/count') is None


def test_parse_region_event_topic():
  parsed = parse_analytics_event_topic(
    'scenescape/event/region/scene-1/region-9/count')
  assert parsed is not None
  assert parsed.region_type == 'region'
  assert parsed.scene_id == 'scene-1'
  assert parsed.resource_id == 'region-9'
  assert parsed.event_type == 'count'


def test_parse_tripwire_event_topic():
  parsed = parse_analytics_event_topic(
    'scenescape/event/tripwire/scene-1/tw-1/objects')
  assert parsed is not None
  assert parsed.region_type == 'tripwire'
  assert parsed.event_type == 'objects'
