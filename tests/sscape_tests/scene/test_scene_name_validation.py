# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.core.exceptions import ValidationError
from django.test import TestCase

from manager.models import Scene
from manager.serializers import SceneSerializer


class SceneNameValidationTestCase(TestCase):
  def test_model_rejects_unsafe_scene_names(self):
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name"]:
      with self.subTest(name=name):
        with self.assertRaises(ValidationError):
          Scene(name=name).full_clean()

  def test_serializer_rejects_unsafe_scene_names(self):
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name"]:
      with self.subTest(name=name):
        serializer = SceneSerializer(data={"name": name})
        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

  def test_serializer_accepts_safe_scene_name(self):
    serializer = SceneSerializer(data={"name": "scene-2026.1"})

    self.assertTrue(serializer.is_valid(), serializer.errors)
