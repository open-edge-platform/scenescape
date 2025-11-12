# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import os
import cv2

from manager.ppl_generator import PipelineConfigGenerator, PipelineGenerator

def load_camera_settings(filepath: str) -> dict:
  if not os.path.isfile(filepath):
    raise FileNotFoundError(
      "CAMERA_SETTINGS argument (--camera-settings) must be set to a valid file path.")
  with open(filepath, 'r') as f:
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
  return camera_settings

def generate_dlsps_config(camera_settings_path: str, model_configs_folder: str, output_path: str, dump_dls_metadata: bool = False):
  camera_settings = load_camera_settings(camera_settings_path)

  os.environ['MODEL_CONFIGS_FOLDER'] = model_configs_folder
  metadata_output_file = os.environ.get('METADATA_OUTPUT_FILE', '/tmp/metadata_output.json')
  config_generator = PipelineConfigGenerator(camera_settings)
  # this will rewrite the pipeline to write DLS metadata to a file
  if dump_dls_metadata:
    config_generator.pipeline_generator.set_timestamper([]).set_adapter([]).set_sink(['gvametapublish name=destination', 'appsink sync=true'])
    config_generator.update_pipeline_string()
    config_generator.set_metadata_destination(output_type="file", output_path=metadata_output_file)
  print("Model chain: ", config_generator.pipeline_generator.get_model_chain())
  print("Pipeline: ", config_generator.pipeline_generator.generate())
  print("Metadata format:", "DLStreamer" if dump_dls_metadata else "SceneScape")

  config_str = config_generator.get_config_as_json()
  with open(output_path, 'w') as f:
    f.write(config_str)
  print(f"Pipeline config written to {output_path}")
  return

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Run the pipeline with specified settings.")
  parser.add_argument(
    '--camera-settings',
    default='./sample_camera_settings.json',
    help='Path to camera settings JSON file (default: ./sample_camera_settings.json)')
  parser.add_argument('--config_folder', default='./',
                      help='Model config folder (default: ./)')
  parser.add_argument('--output_path', default='./dlsps-config.json',
                      help='Path to output file (default: ./dlsps-config.json)')
  parser.add_argument(
    '--dump-dls-metadata', default=False, action='store_true',
    help='If set, the pipeline will be configured to dump DLS metadata to a file.')
  args = parser.parse_args()

  generate_dlsps_config(args.camera_settings, args.config_folder, args.output_path, args.dump_dls_metadata)
