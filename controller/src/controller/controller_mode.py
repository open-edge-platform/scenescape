# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
    """
    Initialize the controller mode. Should be called once at startup.

    Args:
        analytics_only: If True, controller runs in analytics-only mode
                      (no tracking, consumes already-tracked objects)
    """
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
    """
    Check if controller is running in analytics-only mode.

    Returns:
        bool: True if analytics-only mode is enabled, False otherwise
    """
    if not cls._initialized:
      log.warning("ControllerMode not initialized. Defaulting to default mode.")
      return False
    return cls._analytics_only

  @classmethod
  def isInitialized(cls):
    """
    Check if the controller mode has been initialized.

    Returns:
        bool: True if initialized, False otherwise
    """
    return cls._initialized

  @classmethod
  def reset(cls):
    """
    Reset the singleton state.
    """
    cls._initialized = False
    cls._analytics_only = False
