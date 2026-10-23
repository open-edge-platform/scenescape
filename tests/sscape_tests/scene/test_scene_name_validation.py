# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
import re

from django.core.exceptions import ValidationError
from django.test import TestCase

from manager.models import Scene
from manager.serializers import SceneSerializer
from manager.validators import validate_scene_name

_migration_0006 = importlib.import_module('manager.migrations.0006_scene_name_validator')
_is_valid_scene_name = _migration_0006._is_valid_scene_name
_sanitize_scene_name = _migration_0006._sanitize_scene_name

# Keep in sync with docs/user-guide/api-docs/api.yaml Scene.name.pattern.
API_SCENE_NAME_PATTERN = re.compile(r'^(?!.*\.\.)(?!\.)[\w \-.]+$')


class SceneNameValidationTestCase(TestCase):
  def test_model_rejects_unsafe_scene_names(self):
    # Model full_clean does not trim whitespace, so trailing newlines are rejected.
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name",
                 "scene\n", ".hidden", "foo..bar"]:
      with self.subTest(name=name):
        with self.assertRaises(ValidationError):
          Scene(name=name).full_clean()

  def test_serializer_rejects_unsafe_scene_names(self):
    # DRF CharField trims leading/trailing whitespace before validate_name runs,
    # so trailing-newline-only cases are covered separately.
    for name in ["../../reloc/hloc/extractors", "..", "/etc", "scene/name", "scene\\name",
                 "sce\nne", ".hidden", "foo..bar"]:
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

  def test_sanitize_legacy_name_with_leading_space_and_dot_terminates(self):
    """Regression: ' .hidden' must not hang the 0006 migration sanitizer."""
    for name in [" .hidden", ".hidden", " ..hidden", " . .foo"]:
      with self.subTest(name=name):
        sanitized = _sanitize_scene_name(name, set())
        self.assertTrue(_is_valid_scene_name(sanitized), sanitized)
        self.assertFalse(sanitized.startswith('.'))
        self.assertNotIn('..', sanitized)

  def test_api_schema_pattern_rejects_leading_dot_and_double_dot(self):
    self.assertIsNone(API_SCENE_NAME_PATTERN.fullmatch('.hidden'))
    self.assertIsNone(API_SCENE_NAME_PATTERN.fullmatch('foo..bar'))
    self.assertIsNotNone(API_SCENE_NAME_PATTERN.fullmatch('scene-2026.1'))
    self.assertIsNotNone(API_SCENE_NAME_PATTERN.fullmatch('foo.bar'))
