#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
JSON Schema validation utilities for tracker service tests.

Validates messages against the actual schema files in schema/ directory
to catch schema drift between tests and production.
"""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import validate, ValidationError


# Path to schema directory (relative to this file)
SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schema"


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict:
  """
  Load a JSON schema file by name.

  Args:
    schema_name: Schema filename (e.g., "camera-data.schema.json")

  Returns:
    Parsed JSON schema dict
  """
  schema_path = SCHEMA_DIR / schema_name
  if not schema_path.exists():
    raise FileNotFoundError(f"Schema not found: {schema_path}")

  with open(schema_path) as f:
    return json.load(f)


def validate_camera_input(data: dict) -> None:
  """
  Validate camera detection message against camera-data.schema.json.

  Args:
    data: Camera detection message dict

  Raises:
    jsonschema.ValidationError: If validation fails
    AssertionError: With friendly message on validation failure
  """
  schema = load_schema("camera-data.schema.json")
  try:
    validate(instance=data, schema=schema)
  except ValidationError as e:
    raise AssertionError(f"Camera input validation failed: {e.message}") from e


def validate_scene_output(data: dict) -> None:
  """
  Validate scene data message against scene-data.schema.json.

  Args:
    data: Scene data message dict

  Raises:
    jsonschema.ValidationError: If validation fails
    AssertionError: With friendly message on validation failure
  """
  schema = load_schema("scene-data.schema.json")
  try:
    validate(instance=data, schema=schema)
  except ValidationError as e:
    raise AssertionError(f"Scene output validation failed: {e.message}") from e
