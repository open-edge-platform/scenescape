# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

from scene_common import log

class ControllerMode:
  """
  Static namespace for managing controller's mode.

  Usage:
      # Initialize once at startup
      ControllerMode.initialize(analytics_only=True)

      # Access anywhere in the codebase
      if ControllerMode.isAnalyticsOnly():
          # analytics-only mode
      else:
          # default mode
  """

  _initialized = False
  _analytics_only = False

  @classmethod
  def initialize(cls, analytics_only=False):
    if cls._initialized:
      log.warning("ControllerMode already initialized. Ignoring re-initialization.")
      return
    cls._analytics_only = analytics_only
    cls._initialized = True
    if analytics_only:
      log.info("Controller mode: ANALYTICS-ONLY (tracker disabled)")
    else:
      log.info("Controller mode: DEFAULT (tracker enabled)")

  @classmethod
  def isAnalyticsOnly(cls):
    return cls._analytics_only

  @classmethod
  def isInitialized(cls):
    return cls._initialized

  @classmethod
  def reset(cls):
    cls._initialized = False
    cls._analytics_only = False
