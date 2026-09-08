# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

from django.test import TestCase

from manager.models import Scene
from manager.serializers import SceneSerializer


class SceneUpdateTestCase(TestCase):
  def setUp(self):
    self.scene = Scene.objects.create(name="test_scene")

  def test_map_corners_lla_json_string_is_parsed(self):
    corners = [
      [37.0, -122.0, 0],
      [37.1, -122.0, 0],
      [37.1, -121.9, 0],
      [37.0, -121.9, 0],
    ]
    serializer = SceneSerializer(
      instance=self.scene,
      data={
        'name': self.scene.name,
        'output_lla': True,
        'map_corners_lla': json.dumps(corners),
      },
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertEqual(serializer.validated_data['map_corners_lla'], corners)

  def test_output_lla_accepts_lowercase_true_string(self):
    corners = [
      [37.0, -122.0, 0],
      [37.1, -122.0, 0],
      [37.1, -121.9, 0],
      [37.0, -121.9, 0],
    ]
    serializer = SceneSerializer(
      instance=self.scene,
      data={
        'name': self.scene.name,
        'output_lla': 'true',
        'map_corners_lla': json.dumps(corners),
      },
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertIs(serializer.validated_data['output_lla'], True)

  def test_output_lla_rejects_unknown_choice(self):
    serializer = SceneSerializer(
      instance=self.scene,
      data={
        'name': self.scene.name,
        'output_lla': 'not-a-bool',
      },
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('output_lla', serializer.errors)

  def test_map_corners_lla_invalid_string_is_rejected(self):
    serializer = SceneSerializer(
      instance=self.scene,
      data={
        'name': self.scene.name,
        'map_corners_lla': 'not-json',
      },
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('map_corners_lla', serializer.errors)
