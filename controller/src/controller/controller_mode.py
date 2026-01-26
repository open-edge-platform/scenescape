# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log

class ControllerMode:
    """
    Singleton class for managing controller's mode.

    Usage:
        # Initialize once at startup
        ControllerMode.initialize(analytics_only=True)

        # Access anywhere in the codebase
        if ControllerMode.is_analytics_only():
            # analytics-only mode
        else:
            # default mode
    """

    _instance = None
    _initialized = False
    _analytics_only = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ControllerMode, cls).__new__(cls)
        return cls._instance

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
    def is_analytics_only(cls):
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
    def is_initialized(cls):
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
