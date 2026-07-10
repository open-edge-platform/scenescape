# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

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
  _shadow_mode = False

  @classmethod
  def initialize(cls, analytics_only=False, shadow_mode=False):
    """
    Initialize the controller mode. Should be called once at startup.

    Args:
        analytics_only: If True, controller runs in analytics-only mode
                      (no tracking, consumes already-tracked objects)
        shadow_mode:    If True, run shadow analytics in parallel for parity
                      validation.  Divergences are logged as warnings.
    """
    if cls._initialized:
      log.warning("ControllerMode already initialized. Ignoring re-initialization.")
      return

    cls._analytics_only = analytics_only
    cls._shadow_mode = shadow_mode or os.getenv('ANALYTICS_SHADOW_MODE', '').lower() in ('1', 'true')
    cls._initialized = True

    if analytics_only:
      log.info("Controller mode: ANALYTICS-ONLY (tracker disabled)")
    elif cls._shadow_mode:
      log.info("Controller mode: SHADOW (parity validation enabled)")
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
  def isShadowMode(cls):
    """
    Check if controller is running in shadow mode for parity validation.

    Returns:
        bool: True if shadow mode is enabled, False otherwise
    """
    if not cls._initialized:
      return False
    return cls._shadow_mode

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
    cls._shadow_mode = False
