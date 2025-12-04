# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import os
from pathlib import Path
import cv2
import numpy as np
from .common_types import PipelineGenerationValueError
from .pipeline_generator import PipelineGenerator

# TODO: Move the method to pipeline_generator.py
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
    raise PipelineGenerationValueError(
      f"Model config file '{model_config_path}' does not exist.")

  with open(model_config_path, 'r') as f:
    model_config = json.load(f)

  return PipelineGenerator(form_data_dict, model_config)


# TODO: Consider how to get rid of this method, otherwise move the method to pipeline_generator.py.
def generate_pipeline_string_from_dict(form_data_dict):
  """Generate camera pipeline string from form data dictionary and model config."""
  return create_pipeline_generator_from_dict(form_data_dict).generate()


class PipelineConfigGenerator:
  """Generates a DLSPS configuration JSON file from camera settings"""

  # TODO: move to a separate JSON file
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

  def __init__(self, camera_settings: dict, publish_frame: bool = True):
    self.name = camera_settings['name']
    self.camera_id = camera_settings['sensor_id']
    self.pipeline_generator = create_pipeline_generator_from_dict(camera_settings)
    self.metadata_policy = self.pipeline_generator.get_metadata_policy()

    # Deep copy to avoid mutating the class-level template
    self.config_dict = copy.deepcopy(
      PipelineConfigGenerator.CONFIG_TEMPLATE)

    pipeline_cfg = self.config_dict["config"]["pipelines"][0]
    pipeline_cfg["name"] = self.name

    use_camera_pipeline = camera_settings.get('use_camera_pipeline', False)
    user_provided_pipeline = camera_settings.get('camera_pipeline', '') if use_camera_pipeline else ''
    self.update_pipeline_string(user_provided_pipeline)

    if 'cameraundistort' in self.pipeline:
      intrinsics = self.get_camera_intrinsics_matrix(camera_settings)
      dist_coeffs = self.get_camera_dist_coeffs(camera_settings)
      pipeline_cfg["payload"]["parameters"]["undistort_config"] = self.generate_undistort_config_xml(
        intrinsics, dist_coeffs)

    pipeline_cfg["payload"]["parameters"]["camera_config"]["cameraid"] = self.camera_id
    pipeline_cfg["payload"]["parameters"]["camera_config"]["metadatagenpolicy"] = self.metadata_policy

  def generate_undistort_config_xml(self,
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

  def set_metadata_destination(self, output_path: str, output_type: str = "file", output_format: str = "json-lines"):
    """
    Sets the metadata destination in the pipeline.
    """
    pipeline_cfg = self.config_dict["config"]["pipelines"][0]
    pipeline_cfg["payload"]["destination"] = {"metadata": {"format": output_format, "type": output_type, "path": output_path}}
    return

  def update_pipeline_string(self, new_pipeline: str = ''):
    """
    Updates the pipeline string in the configuration.
    """
    if not new_pipeline:
      self.pipeline = self.pipeline_generator.generate()
    else:
      self.pipeline = new_pipeline
    self.config_dict["config"]["pipelines"][0]["pipeline"] = self.pipeline
    return

  @property
  def pipeline_generator(self) -> PipelineGenerator:
    return self._pipeline_generator

  @pipeline_generator.setter
  def pipeline_generator(self, value: PipelineGenerator):
    self._pipeline_generator = value
