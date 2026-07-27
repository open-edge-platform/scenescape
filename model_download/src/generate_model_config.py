# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Model configuration generator for the model_download flow.
Creates additional config files for dlstreamer-pipeline-server based on the models available in
the model_download volume."""

import argparse
import json
from pathlib import Path

_MODEL_NAME_MAP = {
  "age-gender-recognition-retail-0013": "agegender",
  "person-attributes-recognition-crossroad-0238": "personattr",
  "person-detection-retail-0013": "retail",
  "person-reidentification-retail-0277": "reid",
  "person-vehicle-bike-detection-crossroad-1016": "pvbcross16",
  "vehicle-attributes-recognition-barrier-0042": "vehattr",
}


def _parse_subfolders(subfolders_raw: str) -> list[str]:
  subfolders = [item.strip() for item in subfolders_raw.split(",") if item.strip()]
  if not subfolders:
    raise ValueError("At least one subfolder must be provided")
  return subfolders


def _get_available_models(models_path: str, subfolders: list[str]) -> list[tuple[str, str, str]]:
  """
  Get list of available models in the folder structure.
  Returns list of tuples: (model_path, model_name, precision)
  """
  models = []
  models_path = Path(models_path)

  for subfolder_name in subfolders:
    subfolder = models_path / subfolder_name
    if subfolder.exists():
      for xml_file in subfolder.rglob("*.xml"):
        relative_path = xml_file.relative_to(models_path)
        path_parts = relative_path.parts

        # Expect structure: subfolder_name/model_name/precision/file.xml
        if len(path_parts) >= 4 and path_parts[0] == subfolder_name:
          model_name = path_parts[1]
          precision = path_parts[2]
          models.append((str(relative_path), model_name, precision))

  return models


def _classify_model_type(model_name: str) -> tuple[str, str]:
  """
  Classify model type and return (model_type, metadata_policy).
  """
  model_name_lower = model_name.lower()

  if any(keyword in model_name_lower for keyword in ["detection", "detector", "detect"]):
    if "text" in model_name_lower or "horizontal-text" in model_name_lower:
      return "detect", "ocrPolicy"
    return "detect", "detectionPolicy"

  if "reidentification" in model_name_lower or "reid" in model_name_lower:
    return "inference", "reidPolicy"

  if any(keyword in model_name_lower for keyword in ["recognition", "attributes", "classification"]):
    if "text" in model_name_lower:
      return "classify", "ocrPolicy"
    return "classify", "classificationPolicy"

  if "pose" in model_name_lower:
    return "detect", "detectionPolicy"

  return "detect", "detectionPolicy"


def _find_model_proc_file(models_path: str, model_path: str, model_name: str) -> str:
  """
  Find the model processor JSON file in the same directory as the XML file.
  """
  models_path = Path(models_path)
  xml_file_path = models_path / model_path
  model_dir = xml_file_path.parent
  json_file = model_dir / f"{model_name}.json"

  if json_file.exists():
    return str(json_file.relative_to(models_path))

  return None


def generate_model_config(
    models_path: str,
    output_file: str,
    prefer_precision: str = "FP16",
    subfolders: list[str] | None = None,
) -> dict:
  """
  Generate the model configuration dictionary and save it to model_configs subfolder.
  """
  models_path = Path(models_path)
  subfolders = subfolders or ["omz", "intel", "public"]

  if not models_path.exists():
    print(f"Error: Models path '{models_path}' does not exist.")
    return {}

  if not any((models_path / subfolder).exists() for subfolder in subfolders):
    print(f"Error: None of the expected subfolders {subfolders} found in '{models_path}'.")
    return {}

  models = _get_available_models(str(models_path), subfolders)
  if not models:
    print("No models found in the specified path.")
    return {}

  model_dict = {}
  for model_path, model_name, precision in models:
    if model_name not in model_dict:
      model_dict[model_name] = []
    model_dict[model_name].append((model_path, precision))

  config = {}

  for model_name, model_variants in model_dict.items():
    selected_model = None
    for model_path, precision in model_variants:
      if precision == prefer_precision:
        selected_model = (model_path, precision)
        break

    if not selected_model:
      selected_model = model_variants[0]

    model_path, precision = selected_model
    model_type, metadata_policy = _classify_model_type(model_name)
    model_proc_path = _find_model_proc_file(str(models_path), model_path, model_name)

    if model_name in _MODEL_NAME_MAP:
      config_name = _MODEL_NAME_MAP[model_name]
    else:
      config_name = model_name.replace("-", "_")

    model_config = {
      "type": model_type,
      "params": {
        "model": model_path
      },
      "adapter-params": {
        "metadatagenpolicy": metadata_policy
      }
    }

    if model_proc_path:
      model_config["params"]["model_proc"] = model_proc_path

    config[config_name] = model_config

  output_dir = models_path / "model_configs"
  output_dir.mkdir(exist_ok=True)
  output_path = output_dir / output_file

  with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2)

  print(f"Generated configuration with {len(config)} models:")
  for name, conf in config.items():
    policy = conf["adapter-params"]["metadatagenpolicy"]
    model_path = conf["params"]["model"]
    print(f"  {name}: {policy} ({model_path})")

  print(f"\nConfiguration saved to: {output_path}")
  return config


def _build_arg_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser()
  parser.add_argument("--models-path", type=str, default="/models")
  parser.add_argument("--output-file", type=str, default="model_config.json")
  parser.add_argument("--prefer-precision", type=str, default="FP32")
  parser.add_argument("--subfolders", type=str, default="omz,intel,public")
  return parser


def main() -> int:
  parser = _build_arg_parser()
  args = parser.parse_args()

  try:
    subfolders = _parse_subfolders(args.subfolders)
    config = generate_model_config(
      models_path=args.models_path,
      output_file=args.output_file,
      prefer_precision=args.prefer_precision,
      subfolders=subfolders,
    )
  except ValueError as exc:
    print(f"Error: {exc}")
    return 2

  return 0 if config else 1


if __name__ == "__main__":
  raise SystemExit(main())
