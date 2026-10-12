# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.core.exceptions import ValidationError
from django.test import TestCase

from manager.models import Scene
from manager.serializers import SceneSerializer
from manager.validators import validate_scene_name


class SceneNameValidationTestCase(TestCase):
  def test_model_rejects_unsafe_scene_names(self):
    # Model full_clean does not trim whitespace, so trailing newlines are rejected.
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name", "scene\n"]:
      with self.subTest(name=name):
        with self.assertRaises(ValidationError):
          Scene(name=name).full_clean()

  def test_serializer_rejects_unsafe_scene_names(self):
    # DRF CharField trims leading/trailing whitespace before validate_name runs,
    # so trailing-newline-only cases are covered separately.
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name", "sce\nne"]:
      with self.subTest(name=name):
        serializer = SceneSerializer(data={"name": name})
        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

  def test_validator_rejects_trailing_newline(self):
    with self.assertRaises(ValidationError):
      validate_scene_name("scene\n")

  def test_serializer_trims_trailing_newline_to_safe_name(self):
    """API CharField trim_whitespace normalizes 'scene\\n' to 'scene' before validation."""
    serializer = SceneSerializer(data={"name": "scene\n"})

    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertEqual(serializer.validated_data["name"], "scene")

  def test_serializer_accepts_safe_scene_name(self):
    serializer = SceneSerializer(data={"name": "scene-2026.1"})

    self.assertTrue(serializer.is_valid(), serializer.errors)
