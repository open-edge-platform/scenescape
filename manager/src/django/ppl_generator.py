# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import os
import re
from pathlib import Path
from enum import IntEnum, Enum

import cv2
import numpy as np


class InferenceRegion(IntEnum):
  FULL_FRAME = 0
  ROI_LIST = 1


class CamerachainOperators(Enum):
  SEQUENTIAL = '+'
  PARALLEL = ','
  BRACKET_OPEN = '['
  BRACKET_CLOSE = ']'


class ChainableNode:
  """Base class for all chainable node types in a sub-pipeline."""

  def serialize(self) -> list:
    raise NotImplementedError("serialize method must be implemented by subclasses")

  def set_inference_input(self, region: InferenceRegion):
    raise NotImplementedError("set_inference_input method must be implemented by subclasses")

  def get_metadata_policy(self) -> str:
    raise NotImplementedError("get_metadata_policy method must be implemented by subclasses")

  def get_output_device(self) -> str:
    raise NotImplementedError("get_output_device method must be implemented by subclasses")

  def __str__(self):
    return 'Abstract Chainable Node'

class InferenceNode(ChainableNode):
  """Single model node that wraps InferenceModel."""

  def __init__(self, models_folder: str, model_expr: str, model_config: dict):
    self.inference_model = InferenceModel(models_folder, model_expr, model_config)

  def serialize(self) -> list:
    return self.inference_model.serialize()

  def set_inference_input(self, region: InferenceRegion):
    self.inference_model.set_inference_region(region)

  def get_metadata_policy(self) -> str:
    return self.inference_model.get_metadata_policy()

  def get_output_device(self) -> str:
    return self.inference_model.get_target_device()

  def __str__(self):
    return f'{self.inference_model.inference_element}({self.inference_model.model_name}, {self.inference_model.get_target_device()})'


class SequentialNodes(ChainableNode):
  """Container for sequential chaining of models."""

  def __init__(self, nodes: list):
    self.nodes = nodes

  def serialize(self) -> list:
    result = []
    for i, node in enumerate(self.nodes):
      result.extend(node.serialize())
      if i < len(self.nodes) - 1:
        result.append('queue')
    return result

  def set_inference_input(self, region: InferenceRegion):
    if len(self.nodes):
      self.nodes[0].set_inference_input(region)
      for node in self.nodes[1:]:
        node.set_inference_input(InferenceRegion.ROI_LIST)

  def get_metadata_policy(self) -> str:
    # get the policy from the last node in the sequence
    if len(self.nodes):
      return self.nodes[-1].get_metadata_policy()
    return 'detectionPolicy'

  def get_output_device(self) -> str:
    return self.nodes[-1].get_output_device() if len(self.nodes) else ''

  def __str__(self):
    return ' ( ' + ' -> '.join([str(node) for node in self.nodes]) + ' ) '


class ParallelNodes(ChainableNode):
  """Container for parallel chaining of models."""

  def __init__(self, nodes: list):
    self.nodes = nodes

  def serialize(self) -> list:
    raise NotImplementedError("serialize method not yet implemented")

  def set_inference_input(self, region: InferenceRegion):
    for node in self.nodes:
      node.set_inference_input(region)

  def get_metadata_policy(self) -> str:
    policies = [ node.get_metadata_policy() for node in self.nodes ] or ['detectionPolicy']
    if not all(policy == policies[0] for policy in policies):
      raise ValueError("Parallel nodes with mixed metadata policies are not supported")
    return policies[0]

  def get_output_device(self) -> str:
    return self.nodes[0].get_output_device() if len(self.nodes) else ''

  def __str__(self):
    return ' ( ' + ' || '.join([str(node) for node in self.nodes]) + ' ) '


def parse_camerachain(camerachain: str, models_folder: str, model_config: dict) -> ChainableNode:
  """Parse camerachain string and return a sub-pipeline object."""
  camerachain = camerachain.strip()

  # Check for unsupported characters
  if CamerachainOperators.BRACKET_OPEN.value in camerachain or CamerachainOperators.BRACKET_CLOSE.value in camerachain:
    raise ValueError("Square brackets '[' and ']' are not supported in current version")

  # Check for mixed operators
  has_sequential_operator = CamerachainOperators.SEQUENTIAL.value in camerachain
  has_parallel_operator = CamerachainOperators.PARALLEL.value in camerachain

  if has_sequential_operator and has_parallel_operator:
    raise NotImplementedError(f"Mixed sequential ('{CamerachainOperators.SEQUENTIAL.value}') and parallel ('{CamerachainOperators.PARALLEL.value}') chaining is not yet implemented")

  if has_sequential_operator:
    # Sequential chaining
    model_exprs = [expr.strip() for expr in camerachain.split(CamerachainOperators.SEQUENTIAL.value)]
    nodes = [InferenceNode(models_folder, expr, model_config) for expr in model_exprs if expr]
    return SequentialNodes(nodes)
  elif has_parallel_operator:
    # Parallel chaining
    model_exprs = [expr.strip() for expr in camerachain.split(CamerachainOperators.PARALLEL.value)]
    nodes = [InferenceNode(models_folder, expr, model_config) for expr in model_exprs if expr]
    return ParallelNodes(nodes)
  else:
    # Single model
    return InferenceNode(models_folder, camerachain, model_config)

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
        raise ValueError(f"Device name cannot be empty in model expression '{model_expr}'")
    else:
      model_name = model_expr.strip()
      device = None

    if not re.match(r'^[A-Za-z][A-Za-z0-9_-]*$', model_name):
      raise ValueError(f"Invalid model name '{model_name}'. Model name must start with a letter and contain only letters, numbers, underscores, and hyphens.")

    return model_name, device

  def _load_params(self, model_name: str) -> dict:
    if not model_name:
      raise ValueError(f"No model name provided for model expression")
    elif model_name in self.model_config:
      config = self.model_config[model_name]
      color_space = config.get(
        'input-format',
        {}).get(
        'color-space',
        '')
      if color_space:
        input_format = f'format={color_space}'
      else:
        input_format = ''

      model_params = self._resolve_paths(config.get('params', {}))
      model_params = self._set_default_params(model_params)

      metadata_policy = config.get("adapter-params", {}).get("metadatagenpolicy", "detectionPolicy")

      return {
        'input_format': input_format,
        'model_type': config.get('type'),
        'model_params': model_params,
        'metadata_policy': metadata_policy
      }
    else:
      raise ValueError(
        f"Model {model_name} not found in model config file.")

  def get_target_device(self) -> str:
    """Get the target device, defaulting to CPU if not specified."""
    return self.params['model_params'].get('device', 'CPU')

  def get_input_format(self) -> str:
    """Get the input format string for the model, or None if not specified."""
    return self.params.get('input_format', '')

  def get_metadata_policy(self) -> str:
    """Get the metadata generation policy for the model, defaulting to detectionPolicy."""
    return self.params.get('metadata_policy', 'detectionPolicy')

  def set_inference_region(self, region: InferenceRegion):
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
      raise ValueError(
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


class PipelineGenerator:
  """Generates a GStreamer pipeline string from camera settings and model config."""

  # the paths in the DLSPS container, to be mounted
  models_folder = '/home/pipeline-server/models'
  gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
  video_path = '/home/pipeline-server/videos'

  def __init__(self, camera_settings: dict, model_config: dict):
    self.camera_settings = camera_settings
    camera_chain = camera_settings.get('camerachain')
    self.model_chain = parse_camerachain(
      camera_chain, self.models_folder, model_config)
    # TODO: make it generic, support USB camera inputs etc.
    # for now we assume this is RTSP, HTTP or file URI
    self.input = self._parse_source(
      camera_settings['command'],
      PipelineGenerator.video_path)

    # Apply device rule set to determine pipeline components
    self._apply_device_rule_set()

    self.timestamp = [f'gvapython class=PostDecodeTimestampCapture function=processFrame module={self.gva_python_path}/sscape_adapter.py name=timesync']
    self.undistort = self.add_camera_undistort(camera_settings) if self.camera_settings.get('undistort') else []
    self.adapter = [
      'videoconvert',
      'video/x-raw,format=BGR',
      f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher'
    ]
    self.metadata_conversion = ['gvametaconvert add-tensor-data=true name=metaconvert']
    self.sink = ['appsink sync=true']

  def _apply_device_rule_set(self):
    """Apply device-based rule set to determine pipeline components."""
    decode_device = self.camera_settings.get('cv_subsystem', 'AUTO')

    # Validate inputs
    if decode_device not in ['CPU', 'GPU', 'AUTO']:
      raise ValueError(f"Unsupported decode device: {decode_device}. Supported values are 'CPU', 'GPU', 'AUTO'.")

    # Decoder selection
    if decode_device == "CPU":
      self.decode = ["decodebin force-sw-decoders=true", "videoconvert"]
    else:
      self.decode = ["decodebin3"]

    self.post_gpu_inference_conversion = (self.model_chain.get_output_device() == "GPU")

  def _parse_source(self, source: str, video_volume_path: str) -> list:
    """
    Parses the GStreamer source element type based on the source string.
    Supported source types are 'rtsp', 'file'.

    @param source: The source string as typed by the user (e.g., RTSP URL, file path).
    @return: array of Gstreamer source elements
    """
    if source.startswith('rtsp://'):
      return [
        f'rtspsrc location={source} latency=200 name=source',
        'rtph264depay',
        'h264parse']
    elif source.startswith('file://'):
      filepath = Path(video_volume_path) / Path(source[len('file://'):])
      return [
        f'multifilesrc loop=TRUE location={filepath} name=source']
    elif source.startswith('http://') or source.startswith('https://'):
      return [
        f'souphttpsrc location={source} name=source',
        'multipartdemux']
    else:
      raise ValueError(
        f"Unsupported source type in {source}. Supported types are 'rtsp://...' (raw H.264), 'http(s)://...' (MJPEG) and 'file://... (relative to video folder)'.")

  def add_camera_undistort(self, camera_settings: dict) -> list[str]:
    intrinsics_keys = [
      'intrinsics_fx',
      'intrinsics_fy',
      'intrinsics_cx',
      'intrinsics_cy']
    dist_coeffs_keys = [
      'distortion_k1',
      'distortion_k2',
      'distortion_p1',
      'distortion_p2',
      'distortion_k3']
    # Validation here can be removed if done prior to this step or we add a
    # flag to enable undistort in calib UI
    if not all(key in camera_settings for key in intrinsics_keys):
      return []
    if not all(key in camera_settings for key in dist_coeffs_keys):
      return []
    try:
      dist_coeffs = [float(camera_settings[key])
                     for key in dist_coeffs_keys]
    except Exception:
      return []
    if all(coef == 0 for coef in dist_coeffs):
      return []

    element = f"cameraundistort settings=cameraundistort0"
    return [element]

  def override_sink(self, new_sink: str):
    """
    Overrides the sink element of the pipeline.
    """
    self.sink = [new_sink]
    return self

  def generate(self) -> str:
    """
    Generates a GStreamer pipeline string from the serialized pipeline.
    """
    pipeline_components = []

    pipeline_components.extend(self.input)
    pipeline_components.extend(self.decode)
    pipeline_components.extend(self.undistort)
    pipeline_components.extend(self.timestamp)

    self.model_chain.set_inference_input(InferenceRegion.FULL_FRAME)
    pipeline_components.extend(self.model_chain.serialize())

    # TODO: optimize queue latency with leaky and max-size-buffers parameters
    pipeline_components.extend(["queue"])
    pipeline_components.extend(self.metadata_conversion)
    # if last inference was on GPU, convert back to video format supported by adapter
    if self.post_gpu_inference_conversion:
      pipeline_components.extend([
          "vapostproc",
          "video/x-raw,format=BGRA"
      ])
    # SceneScape metadata adapter and publisher
    pipeline_components.extend(self.adapter)
    pipeline_components.extend(self.sink)
    return ' ! '.join(pipeline_components)

  def get_model_chain(self) -> ChainableNode:
    return self.model_chain

  def get_metadata_policy(self) -> str:
    return self.model_chain.get_metadata_policy()


def create_pipeline_generator_from_dict(form_data_dict):
  """Create PipelineGenerator object from data dictionary and model config.
  The function accesses the model config file from the filesystem, path to the folder
  is taken from the environment variable MODEL_CONFIGS_FOLDER, defaults to /models/model_configs.
  """
  # `or` operator is used on purpose because `modelconfig` key may exist with value set to None
  model_config_path = Path(
    os.environ.get(
      'MODEL_CONFIGS_FOLDER',
      '/models/model_configs')) / (form_data_dict.get(
    'modelconfig') or 'model_config.json')
  if not model_config_path.is_file():
    raise ValueError(
      f"Model config file '{model_config_path}' does not exist.")

  with open(model_config_path, 'r') as f:
    model_config = json.load(f)

  return PipelineGenerator(form_data_dict, model_config)

def generate_pipeline_string_from_dict(form_data_dict):
  """Generate camera pipeline string from form data dictionary and model config."""
  return create_pipeline_generator_from_dict(form_data_dict).generate()


class PipelineConfigGenerator:
  """Generates a DLSPS configuration JSON file from camera settings.
  If the camera_pipeline is not provided, it will be generated using
  PipelineGenerator.
  """

  CONFIG_TEMPLATE = {
    "config": {
      "logging": {
        "C_LOG_LEVEL": "INFO",
        "PY_LOG_LEVEL": "INFO"
      },
      "pipelines": [
        {
          "name": "",
          "source": "gstreamer",
          "pipeline": "",
          "auto_start": True,
          "parameters": {
            "type": "object",
            "properties": {
              "undistort_config": {
                "element": {
                  "name": "cameraundistort0",
                  "property": "settings",
                  "format": "xml"
                },
                "type": "string"
              },
              "camera_config": {
                "element": {
                  "name": "datapublisher",
                  "property": "kwarg",
                  "format": "json"
                },
                "type": "object",
                "properties": {
                  "cameraid": {
                    "type": "string"
                  },
                  "metadatagenpolicy": {
                    "type": "string",
                    "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                  },
                  "publish_frame": {
                    "type": "boolean",
                    "description": "Publish frame to mqtt"
                  }
                }
              }
            }
          },
          "payload": {
            "parameters": {
              "undistort_config": "",
              "camera_config": {
                "cameraid": "",
                "metadatagenpolicy": ""
              }
            }
          }
        }
      ]
    }
  }

  def __init__(self, camera_settings: dict):
    self.name = camera_settings['name']
    self.camera_id = camera_settings['sensor_id']
    # if camera_pipeline is not provided, try to generate it (needed for
    # pre-existing cameras w/o pipelines)
    self.pipeline_generator = create_pipeline_generator_from_dict(camera_settings)
    if not camera_settings.get('camera_pipeline'):
      self.pipeline = self.pipeline_generator.generate()
    else:
      self.pipeline = camera_settings['camera_pipeline']
    self.metadata_policy = self.pipeline_generator.get_metadata_policy()

    # Deep copy to avoid mutating the class-level template
    self.config_dict = copy.deepcopy(
      PipelineConfigGenerator.CONFIG_TEMPLATE)

    pipeline_cfg = self.config_dict["config"]["pipelines"][0]
    pipeline_cfg["name"] = self.name
    pipeline_cfg["pipeline"] = self.pipeline

    if 'cameraundistort' in self.pipeline:
      intrinsics = self.get_camera_intrinsics_matrix(camera_settings)
      dist_coeffs = self.get_camera_dist_coeffs(camera_settings)
      pipeline_cfg["payload"]["parameters"]["undistort_config"] = self.generate_xml(
        intrinsics, dist_coeffs)

    pipeline_cfg["payload"]["parameters"]["camera_config"]["cameraid"] = self.camera_id
    pipeline_cfg["payload"]["parameters"]["camera_config"]["metadatagenpolicy"] = self.metadata_policy

  def generate_xml(self,
                   camera_intrinsics: list[list[float]],
                   dist_coeffs: list[float]) -> str:
    intrinsics_matrix = np.array(camera_intrinsics, dtype=np.float32)
    dist_coeffs = np.array(dist_coeffs, dtype=np.float32)
    fs = cv2.FileStorage("", cv2.FILE_STORAGE_WRITE |
                         cv2.FILE_STORAGE_MEMORY)
    fs.write("cameraMatrix", intrinsics_matrix)
    fs.write("distCoeffs", dist_coeffs)
    xml_string = fs.releaseAndGetString()
    xml_string = xml_string.replace('\n', '').replace('\r', '')
    return xml_string

  def get_camera_intrinsics_matrix(
      self, camera_settings: dict) -> list[list[float]]:
    intrinsics_matrix = [[camera_settings['intrinsics_fx'], 0, camera_settings['intrinsics_cx']],
                         [0, camera_settings['intrinsics_fy'], camera_settings['intrinsics_cy']],
                         [0, 0, 1]]
    return intrinsics_matrix

  def get_camera_dist_coeffs(self, camera_settings: dict) -> list[float]:
    dist_coeffs = [
      camera_settings['distortion_k1'],
      camera_settings['distortion_k2'],
      camera_settings['distortion_p1'],
      camera_settings['distortion_p2'],
      camera_settings['distortion_k3']]
    return dist_coeffs

  def get_config_as_dict(self) -> dict:
    return self.config_dict

  def get_config_as_json(self) -> str:
    return json.dumps(self.config_dict, indent=2)

  @property
  def pipeline_generator(self) -> PipelineGenerator:
    return self._pipeline_generator

  @pipeline_generator.setter
  def pipeline_generator(self, value: PipelineGenerator):
    self._pipeline_generator = value
