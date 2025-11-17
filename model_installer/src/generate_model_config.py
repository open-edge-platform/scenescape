# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model Configuration Generator

This module provides functionality to generate model_config.json files for Intel SceneScape
from available AI models in intel/ and public/ subfolders.

The main function generate_model_config() automatically discovers models, classifies them
by type, assigns metadata policies, and generates the configuration file with shorter
model names for easier reference in pipeline configurations.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple


# Model name mapping for shorter, more convenient names
_MODEL_NAME_MAP = {
  # Intel models
  "age-gender-recognition-retail-0013": "agegender",
  "horizontal-text-detection-0001": "textdetect",
  "human-pose-estimation-0001": "pose",
  "pedestrian-and-vehicle-detector-adas-0001": "pedveh",
  "person-attributes-recognition-crossroad-0238": "personattr",
  "person-detection-retail-0013": "retail",
  "person-reidentification-retail-0277": "reid",
  "person-vehicle-bike-detection-2000": "pvb2000",
  "person-vehicle-bike-detection-2001": "pvb2001",
  "person-vehicle-bike-detection-2002": "pvb2002",
  "person-vehicle-bike-detection-crossroad-0078": "pvbcross78",
  "person-vehicle-bike-detection-crossroad-1016": "pvbcross16",
  "text-recognition-0012": "textrec",
  "vehicle-license-plate-detection-barrier-0106": "platedetect",
  "vehicle-attributes-recognition-barrier-0042": "vehattr",
  "vehicle-detection-0200": "veh0200",
  "vehicle-detection-0201": "veh0201",
  "vehicle-detection-0202": "veh0202",
  "vehicle-detection-adas-0002": "vehadas",
  # Public models
  "text-recognition-resnet-fc": "textresnet",
}


def _get_available_models(models_path: str) -> List[Tuple[str, str, str]]:
  """
  Get list of available models in the folder structure.
  Returns list of tuples: (model_path, model_name, precision)
  """
  models = []
  models_path = Path(models_path)

  # Check both intel and public folders
  for subfolder_name in ['intel', 'public']:
    subfolder = models_path / subfolder_name
    if subfolder.exists():
      for xml_file in subfolder.rglob("*.xml"):
        # Get relative path from models root and work with that
        relative_path = xml_file.relative_to(models_path)
        path_parts = relative_path.parts

        # Expect structure: subfolder_name/model_name/precision/file.xml
        if len(path_parts) >= 4 and path_parts[0] == subfolder_name:
          model_name = path_parts[1]
          precision = path_parts[2]
          models.append((str(relative_path), model_name, precision))

  return models


def _classify_model_type(model_name: str) -> Tuple[str, str]:
  """
  Classify model type and return (model_type, metadata_policy).

  Returns:
    model_type: 'detect', 'inference', or 'classify'
    metadata_policy: One of the policies from sscape_adapter.py
  """
  model_name_lower = model_name.lower()

  # Detection models
  if any(keyword in model_name_lower for keyword in [
    'detection', 'detector', 'detect'
  ]):
    if 'text' in model_name_lower or 'horizontal-text' in model_name_lower:
      return 'detect', 'ocrPolicy'
    else:
      return 'detect', 'detectionPolicy'

  # Re-identification models
  elif 'reidentification' in model_name_lower or 'reid' in model_name_lower:
    return 'inference', 'reidPolicy'

  # Recognition/classification models
  elif any(keyword in model_name_lower for keyword in [
    'recognition', 'attributes', 'classification'
  ]):
    if 'text' in model_name_lower:
      return 'classify', 'ocrPolicy'
    else:
      return 'classify', 'classificationPolicy'

  # TODO: identify the correct policy for the pose estimation models
  # Pose estimation
  elif 'pose' in model_name_lower:
    return 'inference', 'detection3DPolicy'

  # Default to detection with detectionPolicy
  else:
    return 'detect', 'detectionPolicy'


def _find_model_proc_file(models_path: str, model_path: str, model_name: str) -> str:
  """
  Find the model processor JSON file in the same directory as the XML file.

  Args:
    models_path: Root models path
    model_path: Relative path to the XML file
    model_name: Name of the model

  Returns:
    Relative path to the JSON file if it exists, None otherwise
  """
  models_path = Path(models_path)
  xml_file_path = models_path / model_path

  # Get the directory containing the XML file
  model_dir = xml_file_path.parent

  # Look for JSON file with the same name as the model
  json_file = model_dir / f"{model_name}.json"

  if json_file.exists():
    # Return relative path from models root
    return str(json_file.relative_to(models_path))

  return None


def generate_model_config(models_path: str, output_file: str, prefer_precision: str = "FP16") -> Dict:
  """
  Generate the model configuration dictionary and save it to model_configs subfolder.

  Args:
    models_path: Path to the folder containing 'intel' and 'public' subfolders
    output_file: Name of the output file (will be placed in model_configs subfolder)
    prefer_precision: Preferred precision (FP16 or FP32)

  Returns:
    Dictionary containing the model configuration
  """
  models_path = Path(models_path)

  if not models_path.exists():
    print(f"Error: Models path '{models_path}' does not exist.")
    return {}

  if not (models_path / "intel").exists() and not (models_path / "public").exists():
    print(f"Error: Neither 'intel' nor 'public' folders found in '{models_path}'.")
    return {}

  models = _get_available_models(str(models_path))

  if not models:
    print("No models found in the specified path.")
    return {}

  # Group models by name and select preferred precision
  model_dict = {}
  for model_path, model_name, precision in models:
    if model_name not in model_dict:
      model_dict[model_name] = []
    model_dict[model_name].append((model_path, precision))

  config = {}

  for model_name, model_variants in model_dict.items():
    # Prefer specified precision, fallback to any available
    selected_model = None
    for model_path, precision in model_variants:
      if precision == prefer_precision:
        selected_model = (model_path, precision)
        break

    if not selected_model:
      # Use the first available if preferred precision not found
      selected_model = model_variants[0]

    model_path, precision = selected_model
    model_type, metadata_policy = _classify_model_type(model_name)

    # Find the actual model processor file if it exists
    model_proc_path = _find_model_proc_file(str(models_path), model_path, model_name)

    # Create config name using mapping if available, otherwise use default behavior
    if model_name in _MODEL_NAME_MAP:
      config_name = _MODEL_NAME_MAP[model_name]
    else:
      config_name = model_name.replace('-', '_')

    # Build the configuration
    model_config = {
      "type": model_type,
      "params": {
        "model": model_path
      },
      "adapter-params": {
        "metadatagenpolicy": metadata_policy
      }
    }

    # Add model_proc if JSON file exists (for any model type)
    if model_proc_path:
      model_config["params"]["model_proc"] = model_proc_path

    config[config_name] = model_config

  # Create model_configs directory and save the file
  output_dir = models_path / "model_configs"
  output_dir.mkdir(exist_ok=True)
  output_path = output_dir / output_file

  with open(output_path, 'w') as f:
    json.dump(config, f, indent=2)

  print(f"Generated configuration with {len(config)} models:")
  for name, conf in config.items():
    policy = conf['adapter-params']['metadatagenpolicy']
    model_path = conf['params']['model']
    print(f"  {name}: {policy} ({model_path})")

  print(f"\nConfiguration saved to: {output_path}")

  return config
