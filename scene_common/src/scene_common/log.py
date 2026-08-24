# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging, sys

# Disable logging by default
LVL_TRACK = 0
LVL_CRITICAL = logging.CRITICAL
LVL_ERR = logging.ERROR
LVL_WARN = logging.WARN
LVL_INFO = logging.INFO
LVL_DEBUG = logging.DEBUG
LVL_MIN = 99

# Put this in your program after importing log to enable logging:
# log.LVL_TRACK = 20
# log.LVL_MIN = log.LVL_INFO

class _SafeStreamHandler(logging.StreamHandler):
  """StreamHandler that tolerates sys.stdout being replaced or closed."""
  def emit(self, record):
    if self.stream is not sys.stdout:
      self.stream = sys.stdout
    super().emit(record)

  def handleError(self, record):
    pass

def log(*args, level=logging.INFO):
  if not hasattr(log, "logger"):
    log.logger = logging.getLogger(__name__)
    log.logger.setLevel(level)
    log.handler = _SafeStreamHandler(sys.stdout)
    log.handler.setFormatter(logging.Formatter("%(asctime)s %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    # log.handler.setFormatter(logging.Formatter("%(message)s"))
    log.logger.addHandler(log.handler)
  outstr = " ".join(map(str, args))
  log.logger.log(level, outstr)
  return

def info(*args):
  log(*args, level=LVL_INFO)
  return

def debug(*args):
  log(*args, level=LVL_DEBUG)
  return

def warning(*args):
  log(*args, level=LVL_WARN)
  return

def error(*args):
  log(*args, level=LVL_ERR)
  return

def critical(*args):
  log(*args, level=LVL_CRITICAL)
  return
