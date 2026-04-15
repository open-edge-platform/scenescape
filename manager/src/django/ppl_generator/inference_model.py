# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import base64
import json
import logging
import os
import re
from pathlib import Path
from .common_types import PipelineGenerationValueError

logger = logging.getLogger(__name__)


def _resolve_triton_url(url):
  """Resolve Triton URL to FQDN using Helm release name and K8s namespace.

  If the URL is a short service name (no dots in host), prepends the Helm
  release name and appends the K8s namespace to construct a full FQDN.
  This makes model_config.json release-agnostic and namespace-agnostic.

  Example: "tritonserver:8001" with HELM_RELEASE=mxcp in namespace mxcp
  becomes "mxcp-tritonserver.mxcp.svc.cluster.local:8001"
  """
  if not url or '.' in url.split(':')[0]:
    return url  # Already a FQDN or not a K8s service name
  try:
    ns = os.environ.get('POD_NAMESPACE') or open(
        '/var/run/secrets/kubernetes.io/serviceaccount/namespace').read().strip()
    release = os.environ.get('HELM_RELEASE', '')
    host, port = url.rsplit(':', 1) if ':' in url else (url, '8001')
    if release and not host.startswith(release):
      host = f"{release}-{host}"
    return f"{host}.{ns}.svc.cluster.local:{port}"
  except (FileNotFoundError, PermissionError):
    return url  # Not running in K8s, return as-is


class InferenceModel:
  """Generates DLStreamer sub-pipeline elements from model expression and model config."""

  DEFAULT_PARAMS = {
    "scheduling-policy": "latency",
    "batch-size": "1",
    "inference-interval": "1"
  }

  SUPPORTED_MODEL_TYPES = ['detect', 'classify', 'inference', 'track', 'triton']

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
      if key in ['model', 'model_proc'] and self.model_config.get(self.model_name, {}).get('type') != 'triton':
        converted[key] = str(Path(self.models_folder) / Path(value))
      else:
        converted[key] = value
    return converted

  def _get_inference_element_name(self, model_type: str) -> str:
    if model_type == 'triton':
      return 'gvapython'
    elif model_type in self.SUPPORTED_MODEL_TYPES:
      return f'gva{model_type}'
    else:
      raise PipelineGenerationValueError(
        f"Unsupported model type: {model_type}. Supported types are {', '.join(self.SUPPORTED_MODEL_TYPES)}.")

  def set_preprocessing_backend(self, preprocessing_backend: str):
    """Set the preprocessing backend parameter for the model."""
    if preprocessing_backend:
      self.params['model_params']['pre-process-backend'] = preprocessing_backend

  def _to_gstreamer_key(self, key: str) -> str:
    """Convert Python-style underscore keys to GStreamer hyphenated format.

    GStreamer element properties use hyphens (e.g., 'model-proc'), but Python
    identifiers and JSON keys often use underscores (e.g., 'model_proc').
    This ensures compatibility when serializing parameters for GStreamer pipelines.
    """
    return key.replace('_', '-')

  def serialize(self) -> list:
    if self.params.get('model_type') == 'triton':
      return self._serialize_triton_model()
    else:
      params_str = ' '.join(
        [f'{self._to_gstreamer_key(key)}={self._format_value(value)}' for key, value in self.params['model_params'].items()])
      return [f'{self.inference_element} {params_str}']

  def _format_value(self, value):
    """
    Quote string values if they contain spaces or special characters
    """
    if isinstance(value, str) and (
        any(c in value for c in ' ;!') or value == ''):
      return f'"{value}"'
    return str(value)

  def _serialize_triton_model(self) -> list:
    """Generate gvapython pipeline element for Triton inference with base64-encoded config.

    Uses Base64 encoding to safely pass JSON configuration through GStreamer
    pipeline strings, avoiding quote and brace escaping issues.
    """
    params = self.params.get('model_params', {})

    config_payload = {
        "triton_url": _resolve_triton_url(params.get('triton-url', 'localhost:8001')),
        "model_name": params.get('model', 'tensorrt_model'),
        "input_name": params.get('input-name', 'images'),
        "output_names": params.get('output-names', 'output0,output1,output2'),
        "confidence_threshold": params.get('confidence-threshold', 0.25),
        "nms_threshold": params.get('nms-threshold', 0.45),
        "input_width": params.get('input-width', 640),
        "input_height": params.get('input-height', 640),
        "labels": params.get('labels', None),
        "use_ensemble": params.get('use-ensemble', False),
        "ensemble_model_name": params.get('ensemble-model-name', 'yolov7_ensemble'),
    }

    json_bytes = json.dumps(config_payload).encode('utf-8')
    b64_str = base64.b64encode(json_bytes).decode('utf-8')

    model_type = params.get('model-type', '')
    if model_type in ['yolo', 'tensorrt']:
      inference_script = params.get('inference-script')
      if not inference_script:
        raise ValueError(f"Model config for '{params.get('model', 'unknown')}' is missing required 'inference-script' field")
      module_path = f"/home/pipeline-server/user_scripts/gvapython/sscape/{inference_script}.py"

      config_json_array = json.dumps([b64_str])
      inference_stage = (f'gvapython module={module_path} '
                         f'class=process_frame '
                         f'arg={config_json_array} '
                         f'name=tensorrt_inference')
    else:
      module_path = "triton_server.generic_triton_inference"
      inference_stage = f'gvapython class=process_frame module={module_path} name=generic_triton_inference'

    return [inference_stage]
