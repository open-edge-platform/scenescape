#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Logging setup for end-to-end test orchestration.

Each call to ``setup()`` writes one log file at
``tests/.test_logs/<group>/<test_id>/<test_id>-<timestamp>.log``,
tees ``sys.stdout``/``sys.stderr`` into it, and attaches a console
handler for the terminal. ``finalize(passed)`` closes everything and,
for passing tests, strips INFO/DEBUG chatter from infrastructure
loggers so the log shows only the test's own progress messages.
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = "test"

# INFO/DEBUG from infrastructure loggers (orchestration utilities).
# Used to trim noise from passing logs.
_NOISE_RE = re.compile(
  r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} test\.(?:conftest|containers|profiles|spec|k8s|runner) \[(INFO|DEBUG)\] "
)

# Silence the "last resort" stderr handler for our hierarchy so records
# don't leak to the terminal before setup() is called.
logging.getLogger(_ROOT).addHandler(logging.NullHandler())
logging.getLogger(_ROOT).propagate = False

_state: dict = {}


class _Tee:
  """Write to the primary stream and, while attached, to a per-test mirror.

  Installed once and kept on sys.stdout/sys.stderr so handlers that bound the
  stream on first use never hold a closed file.
  """

  def __init__(self, primary):
    self.primary = primary
    self.mirror = None

  def write(self, data):
    if self.mirror is not None:
      self.mirror.write(data)
    n = self.primary.write(data)
    self.primary.flush()
    return n

  def flush(self):
    if self.mirror is not None:
      self.mirror.flush()
    self.primary.flush()

  def isatty(self):
    return getattr(self.primary, "isatty", lambda: False)()

  def fileno(self):
    return self.primary.fileno()


def _install_tee(name: str) -> _Tee:
  """Wrap sys.<name> in a _Tee unless it is already wrapped."""
  stream = getattr(sys, name)
  if not isinstance(stream, _Tee):
    stream = _Tee(stream)
    setattr(sys, name, stream)
  return stream


def get_logger(name: str | None = None) -> logging.Logger:
  """Return a logger in the 'test.*' hierarchy."""
  if not name:
    return logging.getLogger(_ROOT)
  return logging.getLogger(f"{_ROOT}.{name.rsplit('.', 1)[-1]}")


def _teardown() -> None:
  """Undo whatever setup() installed; the tees stay on sys.std* but detach."""
  for tee in _state.pop("tees", ()):
    tee.mirror = None
  if "tee_file" in _state:
    _state.pop("tee_file").close()
  root = logging.getLogger(_ROOT)
  for h in list(root.handlers):
    if not isinstance(h, logging.NullHandler):
      root.removeHandler(h)
      h.close()
  _state.pop("console", None)


def setup(test_name: str, group: str = "functional", log_base: Path | None = None) -> Path:
  """Attach console+file handlers and tee stdout/stderr into the log file."""
  _teardown()

  log_base = Path(log_base) if log_base else Path(__file__).parents[1] / ".test_logs"
  timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
  stem = f"{test_name}-{timestamp}"
  test_dir = log_base / group / test_name
  test_dir.mkdir(parents=True, exist_ok=True)
  log_path = test_dir / f"{stem}.log"

  root = logging.getLogger(_ROOT)
  root.setLevel(logging.DEBUG)
  # Container-log dir is created lazily by utils.containers on failure.
  root._container_log_dir = test_dir / f"{stem}-containers"

  out_tee = _install_tee("stdout")
  err_tee = _install_tee("stderr")

  # Bind to the primary so console lines are not teed into the log file twice.
  console = logging.StreamHandler(out_tee.primary)
  console.setLevel(logging.INFO)
  console.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
  )
  root.addHandler(console)

  fh = logging.FileHandler(str(log_path))
  fh.setLevel(logging.DEBUG)
  fh.setFormatter(
    logging.Formatter(
      "%(asctime)s %(name)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )
  root.addHandler(fh)

  tee_file = open(str(log_path), "a", encoding="utf-8", buffering=1)
  out_tee.mirror = tee_file
  err_tee.mirror = tee_file
  _state["tees"] = (out_tee, err_tee)
  _state["tee_file"] = tee_file
  _state["console"] = console
  _state["log_path"] = log_path
  return log_path


def finalize(passed: bool) -> None:
  """Close handlers; for passing tests strip infrastructure INFO/DEBUG."""
  log_path = _state.get("log_path")
  _state.pop("log_path", None)
  _teardown()
  if not passed or not log_path or not log_path.exists():
    return
  kept = [
    ln for ln in log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not _NOISE_RE.match(ln)
  ]
  log_path.write_text("".join(kept), encoding="utf-8")


def silence_console() -> None:
  """Suppress console output for the remainder of the current test."""
  console = _state.get("console")
  if console is not None:
    console.setLevel(logging.CRITICAL + 1)
