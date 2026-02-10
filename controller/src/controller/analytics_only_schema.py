# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
from fastjsonschema import compile as compile_schema
from jsonschema import FormatChecker
from scene_common import log


class SceneDataValidator:
  """
  Validator for scene data in analytics-only mode.
  Loads and compiles the scene data schema for validation.
  """

  def __init__(self, schemaFilename='scene-data.schema.json'):
    """
    Initialize the schema validator.

    Args:
        schemaFilename: Name of the schema file to load (default: 'scene-data.schema.json')
    """
    self.validator = None
    self.validatorNoFormat = None
    self.schemaPath = None

    self._loadSchema(schemaFilename)

  def _loadSchema(self, schemaFilename):
    """
    Load and compile the schema file.

    Args:
        schemaFilename: Name of the schema file to load
    """
    self.schemaPath = Path(os.environ.get('SCENESCAPE_HOME')) / 'tracker' / 'schema' / schemaFilename

    if not self.schemaPath.exists():
      log.error(f"Schema file not found at: {self.schemaPath}")
      return

    try:
      with self.schemaPath.open() as schemaFd:
        sceneDataSchema = json.load(schemaFd)

      checker = FormatChecker()
      formats = {
        key: checker.checkers[key][0]
        for key in checker.checkers
      }

      self.validator = compile_schema(sceneDataSchema, formats=formats)
      self.validatorNoFormat = compile_schema(sceneDataSchema)
      log.info(f"Schema validator initialized from: {self.schemaPath}")
    except Exception as e:
      log.error(f"Failed to initialize schema validator: {e}")

  def validate(self, sceneData):
    """
    Validate scene data against the schema.

    Args:
        sceneData: The scene data to validate

    Returns:
        True if validation passes, False otherwise
    """
    validator = self.validator if self.validator else self.validatorNoFormat

    if validator is None:
      log.warning("No validator available, skipping validation")
      return False

    try:
      validator(sceneData)
      log.debug("Scene data validation passed")
      return True
    except Exception as e:
      log.error(f"Scene data validation failed: {e}")
      return False

  def isInitialized(self):
    """
    Check if the validator was successfully initialized.

    Returns:
        True if at least one validator is available, False otherwise
    """
    return self.validator is not None or self.validatorNoFormat is not None
