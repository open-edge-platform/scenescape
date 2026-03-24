# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging, sys, os
from datetime import datetime

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

def _init_loger():
  """Initialize logger if not already created"""
  if hasattr(log, "logger"):
    return

  log.logger = logging.getLogger(__name__)
  log.logger.setLevel(LVL_DEBUG)

  if not log.logger.handlers:
    formatter = logging.Formatter(
      "%(asctime)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    log.logger.addHandler(console_handler)

def enable_file_logging(test_name):
  """OPTIONAL: enable file logging for the test if not enabled elsewhere."""

  _init_loger()

  # Prevent adding multiple file handlers
  if hasattr(log, "filehandler"):
    return

  log_dir = os.path.join(os.getcwd(), "test_data", "logs")
  os.makedirs(log_dir, exist_ok=True)

  timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  log_file = os.path.join(log_dir, f"{test_name}_{timestamp}.log")

  formatter = logging.Formatter(
      "%(asctime)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S"
    )

  file_handler = logging.FileHandler(log_file, mode="w")
  file_handler.setLevel(LVL_DEBUG)
  file_handler.setFormatter(formatter)

  log.logger.addHandler(file_handler)
  log.file_handler = file_handler

  log.logger.info("File logging enabled: {log_file}")


def log(*args, level=logging.INFO):
  _init_loger()

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
