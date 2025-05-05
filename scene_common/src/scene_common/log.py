# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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

def log(*args, level=logging.INFO):
  if not hasattr(log, "logger"):
    log.logger = logging.getLogger(__name__)
    log.logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    # handler.setFormatter(logging.Formatter("%(message)s"))
    log.logger.addHandler(handler)
  outstr = " ".join(map(str, args))
  log.logger.log(level, outstr)
  return

def info(*args):
  log(*args, level=LVL_INFO)
  return

def debug(*args):
  log(*args, level=LVL_DEBUG)
  return

def warn(*args):
  log(*args, level=LVL_WARN)
  return

def error(*args):
  log(*args, level=LVL_ERR)
  return

def critical(*args):
  log(*args, level=LVL_CRITICAL)
  return
