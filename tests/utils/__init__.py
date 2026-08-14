# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared utilities for end-to-end test orchestration."""

import logging
import subprocess

logger = logging.getLogger("test.runner")


def stream_subprocess(cmd, check=True, **kwargs):
  """Run a subprocess, streaming stdout+stderr through the logging system.

  This ensures all subprocess output (make, docker run, etc.) appears both
  in the live terminal (via log_cli) and in any log file configured with
  --log-file, matching the behaviour of the original bash tests.

  Args:
    cmd: Command list to execute.
    check: Raise CalledProcessError on non-zero exit (default True).
    **kwargs: Passed to subprocess.Popen (e.g. cwd=, env=).

  Returns:
    The process exit code.
  """
  proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    **kwargs,
  )
  for line in proc.stdout:
    logger.info(f"{line.rstrip()}")
  proc.wait()
  if check and proc.returncode != 0:
    raise subprocess.CalledProcessError(proc.returncode, cmd)
  return proc.returncode
