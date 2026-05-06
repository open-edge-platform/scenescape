# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
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


def _effective_level(level):
  if LVL_MIN != 99:
    return LVL_MIN
  return level


def _ensure_logger(level):
  effective_level = _effective_level(level)
  if not hasattr(log, "logger"):
    log.logger = logging.getLogger(__name__)
    log.logger.setLevel(effective_level)
    log.logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    # handler.setFormatter(logging.Formatter("%(message)s"))
    log.logger.addHandler(handler)
  elif LVL_MIN != 99 and log.logger.level != effective_level:
    log.logger.setLevel(effective_level)
  return log.logger

def log(*args, level=logging.INFO):
  logger = _ensure_logger(level)
  outstr = " ".join(map(str, args))
  logger.log(level, outstr)
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
