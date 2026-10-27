# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT topic parsing for scene-metadata ingest."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SceneTopic:
  scene_id: str
  category: str


@dataclass(frozen=True)
class AnalyticsEventTopic:
  region_type: str  # region | tripwire
  scene_id: str
  resource_id: str
  event_type: str


def parse_scene_topic(topic: str) -> Optional[SceneTopic]:
  parts = topic.split('/')
  if len(parts) != 5 or parts[0] != 'scenescape' or parts[1] != 'data' or parts[2] != 'scene':
    return None
  return SceneTopic(scene_id=parts[3], category=parts[4])


def parse_analytics_event_topic(topic: str) -> Optional[AnalyticsEventTopic]:
  parts = topic.split('/')
  if len(parts) != 6 or parts[0] != 'scenescape' or parts[1] != 'event':
    return None
  if parts[2] not in ('region', 'tripwire'):
    return None
  return AnalyticsEventTopic(
    region_type=parts[2],
    scene_id=parts[3],
    resource_id=parts[4],
    event_type=parts[5],
  )
