# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import os
import re
from pathlib import Path

import cv2
import numpy as np


class InferenceModel:
  """Generates DLStreamer sub-pipeline elements from model expression and model config."""

  DEFAULT_PARAMS = {
    "scheduling-policy": "latency",
    "batch-size": "1",
    "inference-interval": "1"
  }

  def __init__(
      self,
      models_folder: str,
      model_expr: str,
      model_config: dict):
    self.models_folder = models_folder
    self.model_expr = model_expr
    self.model_config = model_config
    self.model_name, self.device = self._parse_model_expr(model_expr)
    self.params = self._load_params(self.model_name)
    self._set_target_device()
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

      return {
        'input_format': input_format,
        'model_type': config.get('type'),
        'model_params': model_params
      }
    else:
      raise ValueError(
        f"Model {model_name} not found in model config file.")

  def _set_target_device(self):
    """Set target device parameter if specified in model expression."""
    if self.device:
      self.params['model_params']['device'] = self.device

  def get_target_device(self) -> str:
    """Get the target device, defaulting to CPU if not specified."""
    return self.device or 'CPU'

  def get_input_format(self) -> str:
    """Get the input format string for the model, or None if not specified."""
    return self.params.get('input_format', '')

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
    if model_type == 'detect':
      return 'gvadetect'
    elif model_type == 'classify':
      return 'gvaclassify'
    else:
      raise ValueError(
        f"Unsupported model type: {model_type}. Supported types are 'detect', 'classify'.")

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
    self.inference_model = InferenceModel(
      self.models_folder, camera_chain, model_config)
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
    inference_device = self.inference_model.get_target_device()

    # Validate inputs
    if decode_device not in ['CPU', 'GPU', 'AUTO']:
      raise ValueError(f"Unsupported decode device: {decode_device}. Supported values are 'CPU', 'GPU', 'AUTO'.")

    # Decoder selection
    if decode_device == "CPU":
      self.decode = ["decodebin force-sw-decoders=true", "videoconvert"]
    elif decode_device == "GPU":
      self.decode = ["decodebin3", "vapostproc"]
    else:  # AUTO
      self.decode = ["decodebin3"]

    self.memory_uses_va_surfaces = (decode_device != "CPU" and inference_device == "GPU")
    if self.memory_uses_va_surfaces:
      self.memory_caps = ["video/x-raw(memory:VAMemory)"]
      self.preprocessing_backend = "va-surface-sharing"
    else:
      self.memory_caps = ["video/x-raw"]
      if inference_device == "GPU":
        self.preprocessing_backend = "opencv"
      else:
        self.preprocessing_backend = ""

    self.post_gpu_inference_conversion = (inference_device == "GPU")

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
      # TODO: use souphttpsrc when available in DLSPS
      return [
        f'curlhttpsrc location={source} name=source',
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
    pipeline_components.extend(self.memory_caps)
    pipeline_components.extend(self.undistort)
    pipeline_components.extend(self.timestamp)

    # Set preprocessing backend and generate model chain
    if self.preprocessing_backend:
      self.inference_model.set_preprocessing_backend(self.preprocessing_backend)
    model_chain = self.inference_model.serialize()
    # TODO: add support for custom input video format in model config. For now it is ignored
    pipeline_components.extend(model_chain)

    # TODO: optimize queue latency with leaky and max-size-buffers parameters
    pipeline_components.extend(["queue"])
    pipeline_components.extend(self.metadata_conversion)
    if self.post_gpu_inference_conversion:
      pipeline_components.extend([
          "vapostproc",
          "video/x-raw,format=BGRA"
      ])
    # SceneScape metadata adapter and publisher
    pipeline_components.extend(self.adapter)
    pipeline_components.extend(self.sink)
    return ' ! '.join(pipeline_components)


def generate_pipeline_string_from_dict(form_data_dict):
  """Generate camera pipeline string from form data dictionary and model config.
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

  pipeline = PipelineGenerator(form_data_dict, model_config).generate()
  return pipeline


class PipelineConfigGenerator:
  """Generates a DLSPS configuration JSON file from camera settings.
  If the camera_pipeline is not provided, it will be generated using
  the generate_pipeline_string_from_dict function.
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
    if not camera_settings.get('camera_pipeline'):
      self.pipeline = generate_pipeline_string_from_dict(camera_settings)
    else:
      self.pipeline = camera_settings['camera_pipeline']
    self.metadata_policy = 'detectionPolicy'  # hardcoded for now

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
