# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import re
from datetime import datetime
from scene_common import log
from tests.common_test_utils import record_test_result

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


def test_timestamp_format():
  """ Verifies that all timestamps are utilizing ISO 8601 UTC format.

  Steps:
    * Get web container name
    *
  """
  test_name = "NEX-T10548"
  log.info(f"Test: {test_name}")
