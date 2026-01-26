# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Controller operational mode configuration.

This module centralizes all mode-related decisions (analytics-only vs full mode)
to avoid spreading boolean flags across multiple classes.
"""

from enum import Enum
from dataclasses import dataclass


class ControllerMode(Enum):
  """Operational modes for the Scene Controller."""
  FULL = "full"  # Full tracking + analytics (default)
  ANALYTICS_ONLY = "analytics_only"  # Analytics only, no tracking


@dataclass(frozen=True)
class ControllerConfig:
  """
  Singleton configuration for controller operational mode.
  
  This class maintains a single instance of the configuration that can be
  accessed globally. Instead of passing config around, classes access it via:
  
    ControllerConfig.instance()
  
  Good:  if ControllerConfig.instance().is_analytics_only: ...
  Why:   Single source of truth, no need to pass/store config everywhere
  
  Usage pattern:
  1. Initialize once at startup: ControllerConfig.initialize(mode)
  2. Access anywhere: ControllerConfig.instance()
  """
  mode: ControllerMode
  
  # Class-level singleton instance
  _instance: 'ControllerConfig' = None
  
  @classmethod
  def initialize(cls, mode: ControllerMode = None, analytics_only: bool = None) -> 'ControllerConfig':
    """
    Initialize the singleton configuration instance.
    Must be called once at application startup.
    
    Args:
        mode: ControllerMode enum value (preferred)
        analytics_only: Boolean flag for backward compatibility
        
    Returns:
        The initialized singleton instance
        
    Raises:
        ValueError: If already initialized (prevents accidental re-initialization)
    """
    if cls._instance is not None:
      raise ValueError(
        "ControllerConfig already initialized. Use instance() to access it."
      )
    
    if mode is None:
      if analytics_only is None:
        analytics_only = False
      mode = ControllerMode.ANALYTICS_ONLY if analytics_only else ControllerMode.FULL
    
    # Use object.__setattr__ because dataclass is frozen
    instance = cls(mode=mode)
    object.__setattr__(cls, '_instance', instance)
    return instance
  
  @classmethod
  def instance(cls) -> 'ControllerConfig':
    """
    Get the singleton configuration instance.
    
    Returns:
        The singleton instance
        
    Raises:
        RuntimeError: If not yet initialized
    """
    if cls._instance is None:
      raise RuntimeError(
        "ControllerConfig not initialized. Call initialize() at startup."
      )
    return cls._instance
  
  @classmethod
  def reset(cls):
    """
    Reset the singleton (primarily for testing).
    """
    object.__setattr__(cls, '_instance', None)
  
  @property
  def is_analytics_only(self) -> bool:
    """
    Check if running in analytics-only mode.
    
    In analytics-only mode:
    - No tracker initialization (separate Tracker service handles tracking)
    - No camera data processing (no raw detections)
    - Subscribe to DATA_SCENE topics to receive tracked objects via MQTT
    - Perform analytics (regions, tripwires, sensors) on tracked objects
    """
    return self.mode == ControllerMode.ANALYTICS_ONLY
  
  @property
  def is_full_mode(self) -> bool:
    """
    Check if running in full mode (tracking + analytics).
    
    In full mode:
    - Tracker is initialized locally
    - Process camera detection data
    - Perform tracking and analytics together
    """
    return self.mode == ControllerMode.FULL
  
  def __str__(self) -> str:
    return f"ControllerConfig(mode={self.mode.value})"
