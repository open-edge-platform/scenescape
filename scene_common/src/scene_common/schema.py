# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
from jsonschema import FormatChecker
from fastjsonschema import compile

class SchemaValidation:
  def __init__(self, schema_path):
    self.mqtt_schema = None
    self.validator = {}
    self.validator_no_format = {}
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

    if not self.mqtt_schema or "properties" not in self.mqtt_schema:
      raise Exception("Schema not available or is not well formed")

    for key, value in self.mqtt_schema["properties"].items():
      sub_schema = {
        "$ref": value["$ref"],
        "definitions": self.mqtt_schema["definitions"]
      }
      self.validator[key] = compile(sub_schema, formats=formats)
      self.validator_no_format[key] = compile(sub_schema)
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
