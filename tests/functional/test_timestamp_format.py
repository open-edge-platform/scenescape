# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import logging
import os
import re
from datetime import datetime

def get_container_name(pattern, log):
  """Returns the name of a container with specific pattern in name"""

  cmd = ["docker", "ps", "--format", "{{.Names}}"]
  result = subprocess.run(cmd, capture_output=True, text=True)
  containers = result.stdout.splitlines()

  for name in containers:
    if pattern in name:
      log.info(f"Container {pattern} found in the container list.")
      return name

  log.info(f"Container {pattern} not found in the container list.")
  return None


def run_psql(container, query):
  cmd = ["docker", "exec", "-i", container,
          "psql", "-U", "scenescape",
          "-t", "-A", "-c", query]

  result = subprocess.run(cmd, capture_output=True, text=True)
  return result.stdout.strip()


def normalize_timezone(value: str) -> str:
  """Normalizes timezone to avoid python issues."""
  #+00 -> +00:0p
  value = re.sub(r"([+-]\d{2})$", r"\1:00", value)

  #+0000 -> +00:00
  value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)

  return value


def is_valid_timestamp(value: str, log) -> bool:
  """Verifies if psql output in iso format represents a valid date."""
  try:
    value = value.strip()

    # Replace space with T
    value = value.replace(" ", "T")

    # Normalize timezone formats like +00 -> +00:00
    tz_match = re.search(r"([+-]\d{2})$", value)
    if tz_match:
      value = value[-3] + tz_match.group(1) + ":00"

    # Normalize timezone formats like +0000 -> +00:00
    tz_match = re.search(r"([+-]\d{2})(\d{2})$", value)
    if tz_match:
      value = value[:-5] + tz_match.group(1) + ":" +tz_match.group(2)

    # check validity
    datetime.fromisoformat(value)
    return True

  except Exception as e:
    log.debug(f"Problem parsing value: {value!r} -> {e!r}")
    return False


def validate_timestamps(output, log):
  lines = [line.strip() for line in output.splitlines() if line.strip()]

  for line in lines:
    line = normalize_timezone(line)
    assert is_valid_timestamp(line, log), f"Invalid timestamp {line!r}"
  log.info("All values successfuly validated.")


def validate_timestamp_format(rows):
  invalid = []

  for schema, table, column, dtype in rows:
    if "timestamp with time zone" not in dtype.lower():
      invalid.append((schema, table, column, dtype))

  assert not invalid, (
    "Found timestamp columns without timezone:\n" +
    "\n".join(f"{schema}.{table}.{column} -> {dtype}"
              for schema, table, column, dtype in invalid)
  )


def test_timestamp_format(test_logger):
  """ Verifies that all timestamps are utilizing ISO 8601 UTC format.

  Steps:
    * Get pgserver container name
    * Run PSQL commands
    * Verify ISO 8601 format
  """
  test_name = "NEX-T10547"
  log = test_logger
  log.info(f"Test: {test_name}")

  query = """
    SELECT map_processed FROM manager_scene
    UNION ALL
    SELECT applied FROM django_migrations
    UNION ALL
    SELECT action_time FROM django_admin_log
    UNION ALL
    SELECT attempt_time FROM axes_accesslog;
  """

  pg_container = get_container_name('pgserver', log)
  output = run_psql(pg_container, query)
  log.info("Timestamp data from selected fields obtained.")

  validate_timestamps(output, log)

  query = """
    SELECT table_schema, table_name, column_name, data_type
    FROM information_schema.columns
    WHERE data_type LIKE '%timestamp%';
  """

  output = run_psql(pg_container, query)
  log.info("All timestamps in the postgres database obtained.")

  lines = output.splitlines()
  lines = [line.strip() for line in lines if line.strip()]
  lines = [line.split("|") for line in lines]
  log.info("Output parsed.")

  validate_timestamp_format(lines)
  log.info("All entries successfuly validated.")
