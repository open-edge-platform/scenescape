#!/usr/bin/env python3

"""
Model Registry for 3D Reconstruction Models
Central registry for managing reconstruction model plugins.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Registry for managing reconstruction model plugins.
    
    This class provides a central registry for all available reconstruction models
    and handles their initialization and access.
    """
    
    def __init__(self):
        self._models = {}
        self._loaded_models = {}
        logger.info("Model registry initialized")
    
    def register_model(self, model_class: type, model_id: str) -> None:
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
        logger.info(f"Registered model: {model_id}")
    
    def get_available_models(self) -> List[str]:
        """
        Get list of all registered model IDs.
        
        Returns:
            List of model identifiers
        """
        return list(self._models.keys())
    
    def get_model(self, model_id: str, device: str = "cpu"):
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
        
        logger.info(f"Created model instance: {model_id} on {device}")
        return model_instance
    
    def load_model(self, model_id: str, device: str = "cpu"):
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
        model = self.get_model(model_id, device)
        
        if not model.is_model_loaded():
            logger.info(f"Loading model weights for {model_id}...")
            model.load_model()
            logger.info(f"Model {model_id} loaded successfully")
        
        return model
    
    def get_models_status(self) -> Dict[str, Any]:
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
                status[model_id] = loaded_instances[0].get_model_info()
            else:
                # Create temporary instance for info (without loading)
                temp_model = self._models[model_id](device="cpu")
                status[model_id] = temp_model.get_model_info()
        
        return status


# Global model registry instance
model_registry = ModelRegistry()


def register_model(model_id: str):
    """
    Decorator to register a model class with the global registry.
    
    Args:
        model_id: Unique identifier for the model
    
    Usage:
        @register_model("my_model")
        class MyModel(ReconstructionModel):
            pass
    """
    def decorator(model_class):
        model_registry.register_model(model_class, model_id)
        return model_class
    return decorator


def get_model(model_id: str, device: str = "cpu"):
    """
    Get a model instance from the global registry.
    
    Args:
        model_id: Model identifier
        device: Device to run the model on
    
    Returns:
        Model instance
    """
    return model_registry.get_model(model_id, device)


def load_model(model_id: str, device: str = "cpu"):
    """
    Load a model from the global registry.
    
    Args:
        model_id: Model identifier  
        device: Device to run the model on
    
    Returns:
        Loaded model instance
    """
    return model_registry.load_model(model_id, device)


def get_available_models() -> List[str]:
    """
    Get list of all available model IDs.
    
    Returns:
        List of model identifiers
    """
    return model_registry.get_available_models()


def get_models_status() -> Dict[str, Any]:
    """
    Get status of all registered models.
    
    Returns:
        Dictionary mapping model_id to model info
    """
    return model_registry.get_models_status()