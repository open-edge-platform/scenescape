# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
from pathlib import Path
import os
import sys
import cv2

# Compute the absolute path to the target directory
ppl_generator_path = os.path.abspath(
  os.path.join(
    os.path.dirname(__file__),
    '../../manager/src/django'))
sys.path.insert(0, ppl_generator_path)

from ppl_generator import PipelineConfigGenerator, PipelineGenerator


class PipelineRunner:

  docker_compose_file = './docker-compose-ppl.yaml'
  input_folder_mount = '/sample_data'

  def __init__(self, camera_settings: dict, config_folder: str, paths: dict):
    self.camera_settings = camera_settings
    self.paths = paths
    model_config = self._load_model_config(
      camera_settings.get('modelconfig', ''), config_folder)
    self.ppl_generator = PipelineGenerator(camera_settings, model_config)
    # pipeline field will be set on UI level automatically or manually
    # adjusted by user
    camera_settings['camera_pipeline'] = self.ppl_generator.generate()
    self.config_generator = PipelineConfigGenerator(camera_settings)

  def generate_config_file(self, filepath: str):
    config_str = self.config_generator.get_config_as_json()
    with open(filepath, 'w') as f:
      f.write(config_str)
    print(f"Pipeline config written to {filepath}")

  def run(self):
    PipelineRunner._write_env_file(self.paths, './.env')
    self.run_containers()

  def run_containers(self):
    command = [
      'docker',
      'compose',
      '-f',
      PipelineRunner.docker_compose_file,
      'up',
      '-d']
    os.execvp(command[0], command)

  def _write_env_file(env_vars: dict, filepath: str):
    with open(filepath, 'w') as f:
      for key, value in env_vars.items():
        f.write(f'{key}={value}\n')

  def _load_model_config(
      self,
      model_config_name: str,
      model_configs_folder: str) -> dict:
    """
    Loads the model configuration from the specified path in camera settings.
    """
    if model_config_name:
      model_config_path = Path(model_configs_folder) / model_config_name
      with open(model_config_path, 'r') as f:
        return json.load(f)
    else:
      return {}


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Run the pipeline with specified settings.")
  parser.add_argument(
    '--camera-settings',
    default='./sample_camera_settings_file.json',
    help='Path to camera settings JSON file (default: ./sample_camera_settings_file.json)')
  parser.add_argument('--output', default='',
                      help='Output folder (default: none)')
  parser.add_argument('--input', default='../../sample_data',
                      help='Input folder (default: ../../sample_data)')
  parser.add_argument('--config_folder', default='./',
                      help='Model config folder (default: ./)')
  args = parser.parse_args()

  camera_settings_path = args.camera_settings
  output_folder = args.output
  input_folder = args.input
  config_folder = args.config_folder

  if output_folder:
    os.makedirs(output_folder, exist_ok=True)
    # Uncomment it if access issues occur with the mounted volume
    # os.chmod(output_folder, 0o777)

  root_folder = os.environ.get('ROOT_DIR', '../../')
  secrets_folder = os.environ.get('SECRETS_DIR', '../../manager/secrets')

  if not camera_settings_path or not os.path.isfile(camera_settings_path):
    raise FileNotFoundError(
      "CAMERA_SETTINGS argument (--camera-settings) must be set to a valid file path.")
  with open(camera_settings_path, 'r') as f:
    camera_settings = json.load(f)
  camera_numerical_fields = [
    'intrinsics_fx',
    'intrinsics_fy',
    'intrinsics_cx',
    'intrinsics_cy',
    'distortion_k1',
    'distortion_k2',
    'distortion_p1',
    'distortion_p2',
    'distortion_k3']
  for field in camera_numerical_fields:
    if field in camera_settings:
      try:
        camera_settings[field] = float(camera_settings[field])
      except ValueError:
        raise ValueError(
          f"Camera setting '{field}' must be a numerical value.")
  paths = {
    'SECRETS_DIR': os.path.abspath(secrets_folder),
    'ROOT_DIR': os.path.abspath(root_folder),
    'INPUT_DIR': os.path.abspath(input_folder),
    'OUTPUT_DIR': os.path.abspath(output_folder),
  }
  runner = PipelineRunner(camera_settings, config_folder, paths)
  runner.generate_config_file('./dlsps-config.json')
  runner.run()
