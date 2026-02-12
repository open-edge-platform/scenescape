# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from jsonschema import FormatChecker
from fastjsonschema import compile

class SchemaValidation:
  def __init__(self, schema_path, is_multi_message=False):
    self.mqtt_schema = None
    self.validator = {}
    self.validator_no_format = {}
    self.is_multi_message = is_multi_message
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

    if self.is_multi_message:
      for key, value in self.mqtt_schema["properties"].items():
        if "$ref" in value:
          defs_key = "$defs" if "$defs" in self.mqtt_schema else "definitions"
          sub_schema = {
            "$ref": value["$ref"],
            defs_key: self.mqtt_schema[defs_key]
          }
          self.validator[key] = compile(sub_schema, formats=formats)
          self.validator_no_format[key] = compile(sub_schema)
    else:
      self.validator[None] = compile(self.mqtt_schema, formats=formats)
      self.validator_no_format[None] = compile(self.mqtt_schema)
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
    @param msg             The message to validate
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
        print(f"Failed message validation", e)

    return result

  def validate(self, msg, check_format=False):
    return self.validateMessage(None, msg, check_format=check_format)
