#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random
import string
import logging

TEST_NAME = "NEX-T10583"

def _generate_string(length: int = 256) -> str:
  # Generate a random string of specified length to trigger max-length validation.
  characters = string.ascii_letters + string.digits + string.punctuation
  return "".join(random.choice(characters) for _ in range(length))

def test_api_strings(rest, result_recorder, scene_uid, params):
  random_string = _generate_string(256)

  # Authentication length validations
  res = rest.authenticate(params["user"], random_string)
  assert res.errors["password"] == ["Ensure this field has no more than 150 characters."]

  res = rest.authenticate(random_string, params["user"])
  assert res.errors["username"] == ["Ensure this field has no more than 150 characters."]

  # Negative auth with bad creds
  res = rest.authenticate("admin123", "admin123")
  logging.info(res.errors["non_field_errors"])
  assert res.errors["non_field_errors"] == ["Incorrect Username/Password. "]
  assert res.statusCode == 400

  # Re-auth with valid creds for subsequent API calls
  assert rest.authenticate(params["user"], params["password"]), "Re-authentication failed"

  # Overlong name validation across entities
  res = rest.createTripwire({"name": random_string, "scene": scene_uid})
  logging.info(res.errors["name"])
  assert res.errors["name"] == ["Ensure this field has no more than 150 characters."]

  res = rest.createRegion({"name": random_string, "scene": scene_uid})
  logging.info(res.errors["name"])
  assert res.errors["name"] == ["Ensure this field has no more than 150 characters."]

  res = rest.createSensor({"name": random_string, "scene": scene_uid})
  logging.info(res.errors["name"])
  assert res.errors["name"] == ["Ensure this field has no more than 150 characters."]

  res = rest.createCamera({"name": random_string, "scene": scene_uid})
  logging.info(res.errors["name"])
  assert res.errors["name"] == ["Ensure this field has no more than 150 characters."]

  res = rest.createScene({"name": random_string})
  logging.info(res.errors["name"])
  assert res.errors["name"] == ["Ensure this field has no more than 150 characters."]

  # Overlong sensor_id validation
  res = rest.createSensor({"sensor_id": random_string, "scene": scene_uid})
  logging.info(res.errors["sensor_id"])
  assert res.errors["sensor_id"] == ["Ensure this field has no more than 20 characters."]

  result_recorder.success()
