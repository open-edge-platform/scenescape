# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re
from pathlib import Path
from .common_types import PipelineGenerationValueError


class InferenceModel:
  """Generates DLStreamer sub-pipeline elements from model expression and model config."""

  DEFAULT_PARAMS = {
    "scheduling-policy": "latency",
    "batch-size": "1",
    "inference-interval": "1"
  }

  SUPPORTED_MODEL_TYPES = ['detect', 'classify', 'inference', 'track']

  def __init__(
      self,
      models_folder: str,
      model_expr: str,
      model_config: dict):
    self.models_folder = models_folder
    self.model_expr = model_expr
    self.model_config = model_config
    self.model_name, device = self._parse_model_expr(model_expr)
    self.params = self._load_params(self.model_name)
    if device:
      self.params['model_params']['device'] = device
    self.inference_element = self._get_inference_element_name(self.params.get('model_type'))

  def _parse_model_expr(self, model_expr: str) -> tuple[str, str]:
    """Parse model expression to extract model name and optional device."""
    if '=' in model_expr:
      model_name, device = model_expr.split('=', 1)
      model_name = model_name.strip()
      device = device.strip()

      if device == '':
        raise PipelineGenerationValueError(f"Device name cannot be empty in model expression '{model_expr}'")
    else:
      model_name = model_expr.strip()
      device = None

    if not re.match(r'^[A-Za-z][A-Za-z0-9_-]*$', model_name):
      raise PipelineGenerationValueError(f"Invalid model name '{model_name}'. Model name must start with a letter and contain only letters, numbers, underscores, and hyphens.")

    return model_name, device

  def _load_params(self, model_name: str) -> dict:
    if not model_name:
      raise PipelineGenerationValueError(f"No model name provided for model expression")
    elif model_name in self.model_config:
      config = self.model_config[model_name]

      if 'params' not in config:
        raise PipelineGenerationValueError(
          f"No parameters found for model {model_name} in model config file.")
      model_params = self._resolve_paths(config['params'])
      model_params = self._set_default_params(model_params)

      metadata_policy = config.get("adapter-params", {}).get("metadatagenpolicy", "detectionPolicy")

      return {
        'model_type': config.get('type', 'inference'),
        'model_params': model_params,
        'metadata_policy': metadata_policy
      }
    else:
      raise PipelineGenerationValueError(
        f"Model {model_name} not found in model config file.")

  def get_target_device(self) -> str:
    """Get the target device, defaulting to CPU if not specified."""
    return self.params['model_params'].get('device', 'CPU')

  def get_metadata_policy(self) -> str:
    """Get the metadata generation policy for the model, defaulting to detectionPolicy."""
    return self.params.get('metadata_policy', 'detectionPolicy')

  def set_inference_region(self, region):
    """Set the inference region parameter for the model."""
    self.params['model_params']['inference-region'] = str(region.value)

  def _set_default_params(self, params: dict) -> dict:
    """Apply default parameters, with config params taking precedence."""
    result = self.DEFAULT_PARAMS.copy()
    result.update(params)
    return result

  def _resolve_paths(self, params: dict) -> dict:
    converted = {}
    for key, value in params.items():
      if key in ['model', 'model_proc']:
        converted[key] = str(Path(self.models_folder) / Path(value))
      else:
        converted[key] = value
    return converted

  def _get_inference_element_name(self, model_type: str) -> str:
    if model_type in self.SUPPORTED_MODEL_TYPES:
      return f'gva{model_type}'
    else:
      raise PipelineGenerationValueError(
        f"Unsupported model type: {model_type}. Supported types are {', '.join(self.SUPPORTED_MODEL_TYPES)}.")

  def set_preprocessing_backend(self, preprocessing_backend: str):
    """Set the preprocessing backend parameter for the model."""
    if preprocessing_backend:
      self.params['model_params']['pre-process-backend'] = preprocessing_backend

  def serialize(self) -> list:
    # for now it is assumed that model_chain is a single model
    params_str = ' '.join(
      [f'{key}={self._format_value(value)}' for key, value in self.params['model_params'].items()])

    return [f'{self.inference_element} {params_str}']

  def _format_value(self, value):
    """
    Quote string values if they contain spaces or special characters
    """
    if isinstance(value, str) and (
        any(c in value for c in ' ;!') or value == ''):
      return f'"{value}"'
    return str(value)
