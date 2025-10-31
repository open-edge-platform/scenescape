#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model Registry for 3D Reconstruction Models
Central registry for managing reconstruction model plugins.
"""

from typing import Dict, Any, List

from scene_common import log

class ModelRegistry:
  """
  Registry for managing reconstruction model plugins.

  This class provides a central registry for all available reconstruction models
  and handles their initialization and access.
  """

  def __init__(self):
    self._models = {}
    self._loaded_models = {}
    log.info("Model registry initialized")

  def registerModel(self, model_class: type, model_id: str) -> None:
    """
    Register a reconstruction model class.

    Args:
      model_class: Class that implements ReconstructionModel interface
      model_id: Unique identifier for the model

    Raises:
      ValueError: If model_id already exists or model_class is invalid
    """
    if model_id in self._models:
      raise ValueError(f"Model {model_id} already registered")

    # Import here to avoid circular imports
    from model_interface import ReconstructionModel

    # Validate that the class implements the interface
    if not issubclass(model_class, ReconstructionModel):
      raise ValueError(f"Model class must inherit from ReconstructionModel")

    self._models[model_id] = model_class
    log.info(f"Registered model: {model_id}")

  def getAvailableModels(self) -> List[str]:
    """
    Get list of all registered model IDs.

    Returns:
      List of model identifiers
    """
    return list(self._models.keys())

  def getModel(self, model_id: str, device: str = "cpu"):
    """
    Get or create a model instance.

    Args:
      model_id: Model identifier
      device: Device to run the model on

    Returns:
      Model instance

    Raises:
      ValueError: If model_id is not registered
    """
    if model_id not in self._models:
      raise ValueError(f"Model {model_id} not registered. Available: {list(self._models.keys())}")

    # Create cache key
    cache_key = f"{model_id}_{device}"

    # Return cached instance if available
    if cache_key in self._loaded_models:
      return self._loaded_models[cache_key]

    # Create new instance
    model_class = self._models[model_id]
    model_instance = model_class(device=device)

    # Cache the instance
    self._loaded_models[cache_key] = model_instance

    log.info(f"Created model instance: {model_id} on {device}")
    return model_instance

  def loadModel(self, model_id: str, device: str = "cpu"):
    """
    Load a model and its weights.

    Args:
      model_id: Model identifier
      device: Device to run the model on

    Returns:
      Loaded model instance

    Raises:
      ValueError: If model_id is not registered
      RuntimeError: If model loading fails
    """
    model = self.getModel(model_id, device)

    if not model.isModelLoaded():
      log.info(f"Loading model weights for {model_id}...")
      model.loadModel()
      log.info(f"Model {model_id} loaded successfully")

    return model

  def getModelsStatus(self) -> Dict[str, Any]:
    """
    Get status of all registered models.

    Returns:
      Dictionary mapping model_id to model info
    """
    status = {}

    for model_id in self._models:
      # Check if any instance of this model is loaded
      loaded_instances = [
        instance for key, instance in self._loaded_models.items()
        if key.startswith(f"{model_id}_")
      ]

      if loaded_instances:
        # Use the first loaded instance for info
        status[model_id] = loaded_instances[0].getModelInfo()
      else:
        # Create temporary instance for info (without loading)
        temp_model = self._models[model_id](device="cpu")
        status[model_id] = temp_model.getModelInfo()

    return status


# Global model registry instance
model_registry = ModelRegistry()


def registerModel(model_id: str):
  """
  Decorator to register a model class with the global registry.

  Args:
    model_id: Unique identifier for the model

  Usage:
    @registerModel("my_model")
    class MyModel(ReconstructionModel):
      pass
  """
  def decorator(model_class):
    model_registry.registerModel(model_class, model_id)
    return model_class
  return decorator


def getModel(model_id: str, device: str = "cpu"):
  """
  Get a model instance from the global registry.

  Args:
    model_id: Model identifier
    device: Device to run the model on

  Returns:
    Model instance
  """
  return model_registry.getModel(model_id, device)


def loadModel(model_id: str, device: str = "cpu"):
  """
  Load a model from the global registry.

  Args:
    model_id: Model identifier
    device: Device to run the model on

  Returns:
    Loaded model instance
  """
  return model_registry.loadModel(model_id, device)


def getAvailableModels() -> List[str]:
  """
  Get list of all available model IDs.

  Returns:
    List of model identifiers
  """
  return model_registry.getAvailableModels()


def getModelsStatus() -> Dict[str, Any]:
  """
  Get status of all registered models.

  Returns:
    Dictionary mapping model_id to model info
  """
  return model_registry.getModelsStatus()
