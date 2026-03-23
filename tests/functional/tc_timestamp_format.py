import subprocess
import os
from scene_common import log
from tests.functional import FunctionalTest
import tests.common_test_utils as common
from datetime import datetime

TEST_NAME = "NEX-T10547"
MAX_CONTROLLER_WAIT = 20 # seconds
MAX_ATTEMPTS = 3

class ContainerCommandsTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.pgserver_container = self.get_container_name('pgserver')

  def get_container_name(self, pattern):
    """Returns the name of a container with specific pattern in name"""

    cmd = ["docker", "ps", "--format", "{{.Names}}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    containers = result.stdout.splitlines()

    for name in containers:
      if pattern in name:
        log.info(f"{pattern} found in the container list.")
        return name

    log.info(f"{pattern} not found in the container list.")
    return None

  def run_psql(self, container, query):
    cmd = ["docker", "exec", "-i", container,
           "psql", "-U", "scenescape",
           "-t", "-A", "-c", query]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

  def is_valid_timestamp(self, value):
    """Normalizes timezone and verifies if psql output in iso format represents a valid date"""
    try:
      if value.endswith("+00"):
        value = value[:-3] + "00:00"

      datetime.fromisoformat(self, value)
      return True
    except Exception:
      return False

  def validate_timestamps(self, output):
    lines = [line.strip() for line in output.splitlines() if line.strip()]

    for line in lines:
      assert self.is_valid_timestamp(line), f"Invalid timestamp {line!r}"

  def verifyCorrectTimestamp(self):
    """ Verifies that all timestamps are utilizing ISO 8601 UTC format.

    Steps:
      * Get pgserver container name
      * Run PSQL commands
      * Verify ISO 8601 format
    """
    query = """
      SELECT map_processed FROM manager_scene
      UNION ALL
      SELECT applied FROM django_migrations
      UNION ALL
      SELECT action_time FROM django_admin_log
      UNION ALL
      SELECT attempt_time FROM axes_accesslog;
    """

    try:
      self.pg_container = self.get_container_name('pgserver')
      output = self.run_psql(self.pg_container, query)
      self.validate_timestamps(output)

      self.exitCode = 0

    finally:
      self.recordTestResult()

    return

def test_orphaned_cameras(request, record_xml_attribute):
  test = ContainerCommandsTest(TEST_NAME, request, record_xml_attribute)
  test.verifyCorrectTimestamp()
  assert test.exitCode == 0
  return

def main():
  return test_orphaned_cameras(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
