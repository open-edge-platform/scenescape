#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Logging configuration for end-to-end test orchestration.

All test orchestration code should obtain loggers via get_logger() so
that their records flow through the single "test" hierarchy and are
handled by exactly one console handler and phase-specific file handlers.

Typical usage in fixtures / utilities::

    from utils.log import get_logger
    log = get_logger(__name__)   # e.g. "test.containers"

In conftest pytest_runtest_setup hook::

    import utils.log as testlog
    testlog.setup(test_id, group="functional")

At the start of teardown (finally block)::

    testlog.silence_console()
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

LVL_CRITICAL = logging.CRITICAL
LVL_ERR = logging.ERROR
LVL_WARN = logging.WARNING
LVL_INFO = logging.INFO
LVL_DEBUG = logging.DEBUG

# Root logger name for all end-to-end orchestration output
_ROOT = "test"

_console_handler: logging.Handler | None = None
_setup_file_handler: logging.Handler | None = None
_file_handler: logging.Handler | None = None

# Silence the Python "last resort" stderr handler for our hierarchy so
# records don't leak to the terminal before setup() is called.
logging.getLogger(_ROOT).addHandler(logging.NullHandler())
logging.getLogger(_ROOT).propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
  """Return a logger in the 'test.*' hierarchy.

  Args:
    name: Dot-separated suffix appended to 'test.', e.g. "containers".
          Pass None to get the root 'test' logger.
  """
  if name:
    # Strip leading package path so "tests.utils.containers" → "test.containers"
    leaf = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{_ROOT}.{leaf}")
  return logging.getLogger(_ROOT)


def setup(test_name: str, group: str = "functional", log_base: Path | None = None) -> Path:
  """Configure console + file logging for one test run.

  Must be called once before the test starts (e.g. from
  pytest_runtest_setup). Creates:

  - A **console handler** at INFO level so setup and execution output
    appears in the terminal during the test.
  - A **setup file handler** at DEBUG level writing to
    ``test_setup.log`` in the per-test directory.
  - A **test file handler** at DEBUG level for runtime + teardown
    output. This handler is attached when begin_test_phase() is called
    from pytest_runtest_call.

  Args:
    test_name: Test identifier used as the log file stem (e.g. "mqtt_roi").
    group: Sub-directory under log_base (e.g. "functional", "unit").
    log_base: Root log directory. Defaults to tests/test_logs/ (relative
              to this file's location).

  Returns:
    Path to the newly created log file.
  """
  global _console_handler, _setup_file_handler, _file_handler

  root_log = logging.getLogger(_ROOT)
  root_log.setLevel(logging.DEBUG)

  if _setup_file_handler is not None:
    _setup_file_handler.close()
    _setup_file_handler = None
  if _file_handler is not None:
    _file_handler.close()
    _file_handler = None

  # Remove handlers left over from the previous test
  for h in list(root_log.handlers):
    if not isinstance(h, logging.NullHandler):
      root_log.removeHandler(h)
      h.close()

  # ── Console handler (INFO+, terminal only during setup/execution) ───────
  _console_handler = logging.StreamHandler(sys.stdout)
  _console_handler.setLevel(logging.INFO)
  _console_handler.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
  )
  root_log.addHandler(_console_handler)

  # ── File handlers (DEBUG+, split by setup vs test phase) ────────────────
  if log_base is None:
    # tests/utils/log.py → parents[1] = tests/, then test_logs/
    log_base = Path(__file__).parents[1] / "test_logs"
  else:
    log_base = Path(log_base)

  timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
  log_dir = log_base / group / f"{test_name}-{timestamp}"
  log_dir.mkdir(parents=True, exist_ok=True)
  root_log._log_dir = log_dir
  root_log._setup_log_path = log_dir / "test_setup.log"

  log_path = log_dir / f"{test_name}-{timestamp}.log"
  root_log._test_log_path = log_path

  _setup_file_handler = logging.FileHandler(str(root_log._setup_log_path))
  _setup_file_handler.setLevel(logging.DEBUG)
  _setup_file_handler.setFormatter(
    logging.Formatter(
      "%(asctime)s %(name)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )
  root_log.addHandler(_setup_file_handler)

  _file_handler = logging.FileHandler(str(log_path))
  _file_handler.setLevel(logging.DEBUG)
  _file_handler.setFormatter(
    logging.Formatter(
      "%(asctime)s %(name)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )

  return log_path


def begin_test_phase() -> None:
  """Switch file logging from setup log to test log for call/teardown."""
  global _setup_file_handler

  root_log = logging.getLogger(_ROOT)

  if _setup_file_handler is not None and _setup_file_handler in root_log.handlers:
    root_log.removeHandler(_setup_file_handler)
    _setup_file_handler.close()
    _setup_file_handler = None

  if _file_handler is not None and _file_handler not in root_log.handlers:
    root_log.addHandler(_file_handler)


def silence_console() -> None:
  """Suppress console output for the remainder of the current test.

  Call this as the very first line of the teardown block (finally) to
  ensure container-log collection and cleanup messages are written to
  the log file only and do not appear on the terminal.

  The file handler is unaffected.
  """
  if _console_handler is not None:
    _console_handler.setLevel(logging.CRITICAL + 1)
