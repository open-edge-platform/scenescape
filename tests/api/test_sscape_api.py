# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import json
import glob
import inspect
import pytest
from scene_common.rest_client import RESTClient

# Logging Configuration
LOG_FILE = os.path.join(os.path.dirname(__file__), "api_test.log")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE, mode="w")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info(
  "Logger initialized. Logs will be written to console and %s",
  LOG_FILE)

# Setup Base HTTP Client
API_TOKEN = os.environ.get("API_TOKEN")
BASE_URL = os.environ.get("API_BASE_URL", "https://localhost")

http_client = RESTClient(url=f"{BASE_URL}/api/v1", token=API_TOKEN, verify_ssl=False)
autocalib_client = RESTClient(url=f"{BASE_URL}/v1", token=API_TOKEN, verify_ssl=False)

saved_vars = {}

API_MAP = {
  "scene": http_client,
  "camera": http_client,
  "sensor": http_client,
  "region": http_client,
  "tripwire": http_client,
  "user": http_client,
  "asset": http_client,
  "child": http_client,
  "autocalibration": autocalib_client,
}


def load_scenarios(path=None):
  """
  Load multi-step test scenarios from JSON file(s)

  Args:
    path: Can be:
      - A specific JSON file path (e.g., "test/test.json")
      - A folder path to load all *.json files from
      - None to load from default "scenarios" folder
  """
  if path is None:
    path = "scenarios"

  scenarios = []

  if os.path.isfile(path):
    logger.info(f"Loading scenario file: {path}")
    with open(path, "r") as sf:
      data = json.load(sf)
      scenarios.extend(data)
  elif os.path.isdir(path):
    scenario_files = glob.glob(f"{path}/*.json")
    logger.info(
      f"Loading {len(scenario_files)} scenario files from folder: {path}")
    for f in scenario_files:
      with open(f, "r") as sf:
        data = json.load(sf)
        scenarios.extend(data)
  else:
    raise FileNotFoundError(f"Scenario path not found: {path}")

  return scenarios


def substitute_variables(obj):
  """Recursively substitute ${VAR} placeholders with saved values"""
  if isinstance(obj, dict):
    return {k: substitute_variables(v) for k, v in obj.items()}
  if isinstance(obj, list):
    return [substitute_variables(x) for x in obj]
  if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
    var_name = obj[2:-1]
    return saved_vars.get(var_name, obj)
  return obj


def build_call_kwargs(request_data):
  """
  Normalise the structured request dict from the JSON scenario into a flat
  kwargs dict ready to be splatted into the API method call.

  Supported top-level keys in request_data:
    path_params  dict of URL path variables (e.g. scene_id, camera_id, uid)
                 Each key is unpacked directly as a kwarg.
    body         request payload; forwarded as kwarg "data".
  """
  kwargs = {}

  for key, value in request_data.items():
    if key == "path_params":
      # Unpack every path variable as its own kwarg
      if isinstance(value, dict):
        kwargs.update(value)
      else:
        logger.warning(f"    'path_params' should be a dict, got {type(value).__name__}; skipping")
    elif key == "body":
      # Request body → "data" (RESTClient convention)
      kwargs["data"] = value
    else:
      # filter, uid, data, or any legacy flat key – pass through as-is
      kwargs[key] = value

  return kwargs


def compare_expected_json_body(actual, expected, path="root"):
  """
  Deep comparison of two JSON structures with detailed error reporting.
  """
  errors = []

  # Type mismatch
  if not isinstance(actual, type(expected)):
    errors.append(
      f"{path}: type mismatch - expected {type(expected).__name__}, got {type(actual).__name__}")
    return False, errors

  if isinstance(expected, dict):
    for key in expected:
      if key not in actual:
        errors.append(f"{path}.{key}: missing in actual response")
    for key in actual:
      if key not in expected:
        errors.append(f"{path}.{key}: unexpected key in actual response")
    for key in expected:
      if key in actual:
        _, sub_errors = compare_expected_json_body(
          actual[key], expected[key], f"{path}.{key}")
        errors.extend(sub_errors)

  elif isinstance(expected, list):
    if len(actual) != len(expected):
      errors.append(
        f"{path}: list length mismatch - expected {len(expected)}, got {len(actual)}")
    else:
      for i, (actual_item, expected_item) in enumerate(zip(actual, expected)):
        _, sub_errors = compare_expected_json_body(
          actual_item, expected_item, f"{path}[{i}]")
        errors.extend(sub_errors)

  else:
    if actual != expected:
      errors.append(f"{path}: expected '{expected}', got '{actual}'")

  return len(errors) == 0, errors


def validate_response(response_body, validation_rules):
  """
  Validate response body against expected values.
  """
  errors = []

  for field, expected_value in validation_rules.items():
    actual_value = response_body
    for key in field.split('.'):
      if isinstance(actual_value, dict):
        actual_value = actual_value.get(key)
      else:
        actual_value = getattr(actual_value, key, None)

    if actual_value != expected_value:
      errors.append(
        f"Field '{field}': expected '{expected_value}', got '{actual_value}'"
      )

  return len(errors) == 0, errors


def execute_step(step, step_number, total_steps):
  step_name = step.get("step_name", f"Step {step_number}")
  api_name = step["api"]
  method_name = step["method"]
  raw_request = substitute_variables(step.get("request", {}))
  expected_status = step.get("expected_status", {})
  save_vars = step.get("save", {})
  validate_rules = step.get("validate", {})
  expected_body = step.get("expected_body")

  logger.debug(f"  [{step_number}/{total_steps}] {step_name}")
  logger.debug(f"    API: {api_name}, Method: {method_name}")
  logger.debug(f"    Raw request: {raw_request}")

  # Get API client
  api = API_MAP.get(api_name)
  if not api:
    return False, None, f"Unknown API client: {api_name}"

  if not hasattr(api, method_name):
    return False, None, f"API {api_name} has no method {method_name}"

  # Flatten structured request into call kwargs
  call_kwargs = build_call_kwargs(raw_request)

  # If the method expects "filter" and it wasn't provided, default to None
  api_method = getattr(api, method_name)
  method_params = inspect.signature(api_method).parameters
  if "filter" in method_params and "filter" not in call_kwargs:
    call_kwargs["filter"] = None

  # Execute API call
  try:
    response = api_method(**call_kwargs)
  except Exception as e:
    return False, None, f"API call failed: {str(e)}"

  # Parse response
  try:
    response_body = response.json()
  except Exception:
    response_body = response.text

  logger.debug(f"    Response Body: {json.dumps(response_body, indent=2) if isinstance(response_body, dict) else response_body}")

  # Check status code
  expected_status = expected_status.get("status_code", 200)
  if response.status_code != expected_status:
    return False, response, f"Expected status {expected_status}, got {response.status_code}"

  # Validate entire response body if expected_body is provided
  if expected_body is not None:
    logger.debug("    Validating entire response body against expected structure")
    expected_body = substitute_variables(expected_body)
    _, errors = compare_expected_json_body(response_body, expected_body)
    if errors:
      error_msg = "Response body validation failed:\n" + \
        "\n".join(f"  - {e}" for e in errors)
      return False, response, error_msg

  # Save variables from response
  for var_name, path in save_vars.items():
    val = response_body if isinstance(response_body, (dict, list)) else response
    for key in path.split("."):
      if isinstance(val, dict):
        val = val.get(key)
      else:
        val = getattr(val, key, None)

    if val is not None:
      saved_vars[var_name] = val
      os.environ[var_name] = str(val)
      logger.debug(f"    Saved variable '{var_name}' = {val}")
    else:
      logger.warning(f"    Could not find path '{path}' in response")

  # Validate specific fields if rules provided
  if validate_rules:
    logger.debug(f"    Validating response against rules: {validate_rules}")
    _, errors = validate_response(response_body, validate_rules)
    if errors:
      error_msg = "Response validation failed:\n" + \
        "\n".join(f"  - {e}" for e in errors)
      return False, response, error_msg

  logger.debug("    ✓ Step passed")
  return True, response, None


def pytest_generate_tests(metafunc):
  """
  Dynamically generate test parameters based on --file and --test_case options.
  """
  if "test_case" in metafunc.fixturenames:
    file_path = metafunc.config.getoption("--file")
    test_case_filter = metafunc.config.getoption("--test_case")

    scenarios = load_scenarios(file_path)

    # filter by test_case ID if specified (e.g., --test_case
    # Vision_AI/SSCAPE/API/SCENE/01)
    if test_case_filter:
      original_count = len(scenarios)
      scenarios = [
        s for s in scenarios
        if s.get("test_name", "").split(":")[0].strip() == test_case_filter
      ]
      logger.info(
        f"Filtered scenarios: {len(scenarios)}/{original_count} "
        f"matching test_case '{test_case_filter}'")

      if not scenarios:
        pytest.fail(f"No test case found with ID: {test_case_filter}")

    if not scenarios:
      pytest.fail(f"No scenarios found in: {file_path or 'scenarios'}")

    metafunc.parametrize(
      "test_case",
      scenarios,
      ids=lambda tc: tc.get("test_name", "unnamed_test"),
    )


def test_api_scenario_multistep(test_case):
  """
  Execute a multi-step API test scenario.

  Each test case can have multiple steps that execute sequentially.
  If any step fails, the entire test case is marked as failed.
  """
  test_name = test_case.get("test_name", "unnamed_test")
  test_steps = test_case.get("test_steps", [])

  if not test_steps:
    pytest.fail("Test case has no steps defined")

  logger.debug(f"\n{'=' * 70}")
  logger.debug(f"Test: {test_name}")
  logger.debug(f"Steps: {len(test_steps)}")
  logger.debug(f"{'=' * 70}")

  for step_num, step in enumerate(test_steps, start=1):
    success, _, error_msg = execute_step(step, step_num, len(test_steps))
    if not success:
      step_name = step.get("step_name", f"Step {step_num}")
      pytest.fail(f"Step {step_num} '{step_name}' failed: {error_msg}")

  logger.debug(f"✓ All {len(test_steps)} steps passed\n")
