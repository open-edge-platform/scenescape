#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Logging configuration for end-to-end test orchestration.

All test orchestration code should obtain loggers via get_logger() so
that their records flow through the single "test" hierarchy and are
handled by exactly one console handler and one per-test file handler.

Typical usage in fixtures / utilities::

    from utils.log import get_logger
    log = get_logger(__name__)   # e.g. "test.containers"

In conftest pytest_runtest_setup hook::

    import utils.log as testlog
    testlog.setup(test_id, group="functional")

At the start of teardown (finally block)::

    testlog.silence_console()

Each call to ``setup()`` creates one log file at
``tests/test_logs/<group>/<test_id>-<timestamp>/<test_id>-<timestamp>.log``
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

LVL_CRITICAL = logging.CRITICAL
LVL_ERR = logging.ERROR
LVL_WARN = logging.WARNING
LVL_INFO = logging.INFO
LVL_DEBUG = logging.DEBUG

_ROOT = "test"

_console_handler: logging.Handler | None = None
_file_handler: logging.Handler | None = None
_saved_stdout = None
_saved_stderr = None
_tee_file = None
_current_log_path: Path | None = None

# Matches a log-record line written by the file handler formatter
_LOG_LINE_RE = re.compile(
  r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} test\.\S+ \[(INFO|DEBUG)\] "
)

# Silence the "last resort" stderr handler for our hierarchy so records
# don't leak to the terminal before setup() is called.
logging.getLogger(_ROOT).addHandler(logging.NullHandler())
logging.getLogger(_ROOT).propagate = False


class _Tee:
  """Duplicate every ``write``/``flush`` across a primary stream and a file.

  The primary stream is flushed after every write so test output appears in
  the terminal in real time, independent of Python's buffering heuristics
  (which would otherwise block-buffer when stdout is not a tty).
  """

  def __init__(self, primary, mirror):
    self._primary = primary
    self._mirror = mirror

  def write(self, data):
    self._mirror.write(data)
    result = self._primary.write(data)
    self._primary.flush()
    return result

  def flush(self):
    self._mirror.flush()
    self._primary.flush()

  def isatty(self):
    return getattr(self._primary, "isatty", lambda: False)()

  def fileno(self):
    return self._primary.fileno()


def get_logger(name: str | None = None) -> logging.Logger:
  """Return a logger in the 'test.*' hierarchy.

  Args:
    name: Dot-separated suffix appended to 'test.'. Pass None for the root.
  """
  if name:
    leaf = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{_ROOT}.{leaf}")
  return logging.getLogger(_ROOT)


def setup(test_name: str, group: str = "functional", log_base: Path | None = None) -> Path:
  """Configure console + file logging for one test run.

  Creates a single per-test log file and attaches:
    - a console handler (INFO+) writing to the terminal;
    - a file handler (DEBUG+) writing to the log file;
    - a stdout/stderr tee so raw ``print()`` output is mirrored into
      the same log file.

  Any state from the previous test is torn down first.

  Returns:
    Path to the newly created log file.
  """
  global _console_handler, _file_handler
  global _saved_stdout, _saved_stderr, _tee_file, _current_log_path

  root_log = logging.getLogger(_ROOT)
  root_log.setLevel(logging.DEBUG)

  # Restore stdout/stderr and drop the previous file handle.
  if _saved_stdout is not None:
    sys.stdout = _saved_stdout
    _saved_stdout = None
  if _saved_stderr is not None:
    sys.stderr = _saved_stderr
    _saved_stderr = None
  if _tee_file is not None:
    _tee_file.close()
    _tee_file = None

  # Drop handlers from the previous test.
  for h in list(root_log.handlers):
    if not isinstance(h, logging.NullHandler):
      root_log.removeHandler(h)
      h.close()

  # Console handler (terminal, INFO+).
  _console_handler = logging.StreamHandler(sys.stdout)
  _console_handler.setLevel(logging.INFO)
  _console_handler.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
  )
  root_log.addHandler(_console_handler)

  # Resolve the log directory and open the per-test log file.
  if log_base is None:
    log_base = Path(__file__).parents[1] / "test_logs"
  else:
    log_base = Path(log_base)
  timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
  test_dir = log_base / group / test_name
  test_dir.mkdir(parents=True, exist_ok=True)
  stem = f"{test_name}-{timestamp}"
  log_path = test_dir / f"{stem}.log"

  # Container logs land in a sibling directory that's only created on demand
  # (see utils.containers._get_log_dir); it stays absent for passing tests.
  root_log._container_log_dir = test_dir / f"{stem}-containers"

  # File handler (log file, DEBUG+).
  _file_handler = logging.FileHandler(str(log_path))
  _file_handler.setLevel(logging.DEBUG)
  _file_handler.setFormatter(
    logging.Formatter(
      "%(asctime)s %(name)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )
  root_log.addHandler(_file_handler)

  # Tee stdout/stderr into the same log file so raw print() is captured.
  _tee_file = open(str(log_path), "a", encoding="utf-8", buffering=1)
  _saved_stdout = sys.stdout
  _saved_stderr = sys.stderr
  sys.stdout = _Tee(_saved_stdout, _tee_file)
  sys.stderr = _Tee(_saved_stderr, _tee_file)

  _current_log_path = log_path
  return log_path


def finalize(passed: bool) -> None:
  """Close the current test's log file and optionally trim it.

  Called from the pytest teardown-report hook once the outcome is known.

  For a **passing** test the log file is rewritten in place with all
  ``INFO``/``DEBUG`` log-record lines removed, leaving only raw
  ``print()`` output (the test's own progress reporting) plus any
  ``WARNING``+ records worth attention.

  For a **failing** test nothing is filtered — the full orchestration
  log is preserved for debugging.
  """
  global _saved_stdout, _saved_stderr, _tee_file, _file_handler, _current_log_path

  # Detach the file handler and tee so the file is fully flushed and closed
  # before we rewrite it.
  if _saved_stdout is not None:
    sys.stdout = _saved_stdout
    _saved_stdout = None
  if _saved_stderr is not None:
    sys.stderr = _saved_stderr
    _saved_stderr = None
  if _tee_file is not None:
    _tee_file.close()
    _tee_file = None

  root_log = logging.getLogger(_ROOT)
  if _file_handler is not None:
    root_log.removeHandler(_file_handler)
    _file_handler.close()
    _file_handler = None

  log_path = _current_log_path
  _current_log_path = None
  if not passed or log_path is None or not log_path.exists():
    return

  # Drop INFO/DEBUG log-record lines; keep raw print() output and WARNING+.
  kept = [
    line for line in log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not _LOG_LINE_RE.match(line)
  ]
  log_path.write_text("".join(kept), encoding="utf-8")


def silence_console() -> None:
  """Suppress console output for the remainder of the current test.

  Call this at the start of the teardown block so container-log
  collection and cleanup messages go only to the log file.
  The file handler and stdout/stderr tee are unaffected.
  """
  if _console_handler is not None:
    _console_handler.setLevel(logging.CRITICAL + 1)
