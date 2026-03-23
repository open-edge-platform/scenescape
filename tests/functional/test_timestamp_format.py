import subprocess
import logging
import os
from datetime import datetime

def logging_configuration(test_name):
  try:
    LOG_FILE = os.path.join(os.path.dirname(__file__), f"timestamp_format_test_{test_name}.log")

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
    return logger
  except Exception:
    return None

def get_container_name(pattern, logger):
    """Returns the name of a container with specific pattern in name"""

    cmd = ["docker", "ps", "--format", "{{.Names}}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    containers = result.stdout.splitlines()

    for name in containers:
      if pattern in name:
        logger.info(f"{pattern} found in the container list.")
        return name

    logger.info(f"{pattern} not found in the container list.")
    return None

def run_psql(container, query):
    cmd = ["docker", "exec", "-i", container,
           "psql", "-U", "scenescape",
           "-t", "-A", "-c", query]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def is_valid_timestamp(value):
  """Normalizes timezone and verifies if psql output in iso format represents a valid date"""
  try:
    if value.endswith("+00"):
      value = value[:-3] + "00:00"

    datetime.fromisoformat(value)
    return True
  except Exception:
    return False

def validate_timestamps(output):
    lines = [line.strip() for line in output.splitlines() if line.strip()]

    for line in lines:
      assert is_valid_timestamp(line), f"Invalid timestamp {line!r}"

def test_timestamp_format(request, record_xml_attribute):
  """ Verifies that all timestamps are utilizing ISO 8601 UTC format.

    Steps:
      * Get pgserver container name
      * Run PSQL commands
      * Verify ISO 8601 format
  """
  test_name = "NEX-T10547"
  logger = logging_configuration(test_name)
  assert logger, "Logging initialization failed. "
  logger.debug(f"Test: {test_name}")

  query = """
      SELECT map_processed FROM manager_scene
      UNION ALL
      SELECT applied FROM django_migrations
      UNION ALL
      SELECT action_time FROM django_admin_log
      UNION ALL
      SELECT attempt_time FROM axes_accesslog;
    """

  pg_container = get_container_name('pgserver', logger)
  output = run_psql(pg_container, query)
  validate_timestamps(output)
