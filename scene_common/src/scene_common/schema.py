# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from jsonschema import FormatChecker
from fastjsonschema import compile

class SchemaValidation:
  def __init__(self, schema_path):
    self.mqtt_schema = None
    self.validator = {}
    self.validator_no_format = {}
    self.standalone_validator = None
    self.standalone_validator_no_format = None
    self.is_standalone = False
    self.loadSchema(schema_path)
    self.compileValidators()
    return

  def compileValidators(self):
    checker = FormatChecker()
    formats = {}
    for key in checker.checkers:
      formatType = checker.checkers[key][0]
      if key not in formats:
        formats[key] = formatType

    if not self.mqtt_schema:
      raise Exception("Schema not available")

    # Check if this is a standalone schema or multi-message schema
    has_properties_with_refs = (
      "properties" in self.mqtt_schema and
      any("$ref" in v for v in self.mqtt_schema["properties"].values() if isinstance(v, dict))
    )

    if has_properties_with_refs:
      # Multi-message schema (e.g., metadata.schema.json)
      self.is_standalone = False
      for key, value in self.mqtt_schema["properties"].items():
        if "$ref" in value:
          sub_schema = {
            "$ref": value["$ref"],
            "definitions": self.mqtt_schema["definitions"]
          }
          self.validator[key] = compile(sub_schema, formats=formats)
          self.validator_no_format[key] = compile(sub_schema)
    else:
      # Standalone schema (e.g., scene-data.schema.json)
      self.is_standalone = True
      self.standalone_validator = compile(self.mqtt_schema, formats=formats)
      self.standalone_validator_no_format = compile(self.mqtt_schema)
    return

  def loadSchema(self, schema_path):
    print("Loading schema file..")
    try:
      with open(schema_path) as schema_fd:
        self.mqtt_schema = json.load(schema_fd)
      print("Schema file loaded - {}".format(schema_path))
    except:
      print("Invalid schema file / could not open {}".format(schema_path))
    return

  def validateMessage(self, msg_type, msg, check_format=False):
    """Validate a message against the schema
    @param msg_type        The type of message to validate
    @param msg            The message to validate
    @param check_format    Whether to check the format of the message for ex: uuid, date-time etc.
    """
    result = False
    if self.mqtt_schema is not None:
      try:
        if check_format:
          self.validator[msg_type](msg)
        else:
          self.validator_no_format[msg_type](msg)
        result = True
      except Exception as e:
        print(f"Message {msg} failed validation", e)

    return result

  def validateStandalone(self, msg, check_format=False):
    """Validate a message against a standalone schema
    @param msg            The message to validate
    @param check_format    Whether to check the format of the message for ex: uuid, date-time etc.
    """
    result = False
    if not self.is_standalone:
      print("Error: validateStandalone called on multi-message schema. Use validateMessage instead.")
      return result

    if self.mqtt_schema is not None:
      try:
        if check_format:
          self.standalone_validator(msg)
        else:
          self.standalone_validator_no_format(msg)
        result = True
      except Exception as e:
        print(f"Message failed validation: {e}")

    return result
