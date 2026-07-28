#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate Scenescape model_config.json from model_download JSON metadata."""

import argparse
import copy
import json
from pathlib import Path

_DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[1] / 'models.json'
_DEFAULT_OUTPUT_FILE = 'model_config.json'


def _load_json(path: str) -> dict[str, object]:
  with open(path, 'r', encoding='utf-8') as handle:
    data = json.load(handle)

  if not isinstance(data, dict):
    raise ValueError('model config file must contain a JSON object')

  return data


def _get_downloader_models(data: dict[str, object]) -> dict[str, dict[str, object]]:
  models = data.get('models')
  if not isinstance(models, list) or not models:
    raise ValueError('models must be a non-empty JSON array')

  by_name = {}
  for index, model_entry in enumerate(models):
    if not isinstance(model_entry, dict):
      raise ValueError(f'models[{index}] must be an object')

    model = model_entry.get('model_downloader')
    if not isinstance(model, dict):
      raise ValueError(f'models[{index}].model_downloader must be an object')

    name = model.get('name')
    if not isinstance(name, str) or not name:
      raise ValueError(f'models[{index}].model_downloader.name must be a non-empty string')

    if name in by_name:
      raise ValueError(f'model name must be unique for Scenescape config lookup: {name}')

    by_name[name] = model

  return by_name


def _get_model_config_section(data: dict[str, object]) -> dict[str, object]:
  section = data.get('model_config')
  if section is None:
    return {}
  if not isinstance(section, dict):
    raise ValueError('model_config must be an object')
  return section


def _get_model_config_entries(
    models: object,
) -> list[dict[str, object]]:
  if not isinstance(models, list):
    raise ValueError('models must be a JSON array')

  entries = []
  for index, model in enumerate(models):
    if not isinstance(model, dict):
      raise ValueError(f'models[{index}] must be an object')

    scenescape = model.get('scenescape')
    if scenescape is None:
      continue

    if not isinstance(scenescape, dict):
      raise ValueError(f'models[{index}].scenescape must be an object')

    downloader_model = model.get('model_downloader')
    model_name = '<unknown>'
    if isinstance(downloader_model, dict):
      model_name = str(downloader_model.get('name', '<unknown>'))

    if 'name' not in scenescape or 'config' not in scenescape:
      raise ValueError(
        f'Model {model_name} must include both scenescape.name and scenescape.config '
        'to generate model_config entry'
      )
    entries.append(model)

  if not entries:
    raise ValueError('No models include Scenescape config metadata')

  return entries


def _resolve_output_file(section: dict[str, object], output_file: str | None) -> str:
  if output_file:
    return output_file

  configured_output = section.get('output_file', _DEFAULT_OUTPUT_FILE)
  if not isinstance(configured_output, str) or not configured_output:
    raise ValueError('model_config.output_file must be a non-empty string')
  return configured_output


def _build_config_entry(
    entry: dict[str, object],
    downloader_models: dict[str, dict[str, object]],
) -> tuple[str, dict[str, object]]:
  downloader_model = entry.get('model_downloader')
  if not isinstance(downloader_model, dict):
    raise ValueError('Each model entry must include model_downloader object')

  model_name = downloader_model.get('name')
  if not isinstance(model_name, str) or not model_name:
    raise ValueError('Each model_downloader entry must include a non-empty name')

  scenescape = entry.get('scenescape')
  if not isinstance(scenescape, dict):
    raise ValueError(f'Model {model_name} must include scenescape object')

  scenescape_name = scenescape.get('name')
  if not isinstance(scenescape_name, str) or not scenescape_name:
    raise ValueError(f'Model {model_name} scenescape.name must be a non-empty string')

  if model_name not in downloader_models:
    raise ValueError(f'model_config entry references unknown model name: {model_name}')

  config = scenescape.get('config')
  if not isinstance(config, dict):
    raise ValueError(f'Model {model_name} scenescape.config must be an object')

  output_config = copy.deepcopy(config)
  params = output_config.setdefault('params', {})
  if not isinstance(params, dict):
    raise ValueError(f'model_config entry {model_name} config.params must be an object')

  adapter_params = output_config.get('adapter-params')
  if not isinstance(adapter_params, dict):
    raise ValueError(f'model_config entry {model_name} config.adapter-params must be an object')

  model_path = params.get('model')
  if not isinstance(model_path, str) or not model_path:
    raise ValueError(f'Model {model_name} scenescape.config.params.model must be a non-empty string')

  return scenescape_name, output_config


def generate_model_config_from_models(
    models_path: str,
    config_file: str,
    output_file: str | None = None,
) -> dict[str, object]:
  """Generate model_config.json from shared model download configuration."""
  models_path_obj = Path(models_path)
  if not models_path_obj.exists():
    raise ValueError(f"Models path '{models_path_obj}' does not exist")

  data = _load_json(config_file)
  downloader_models = _get_downloader_models(data)
  section = _get_model_config_section(data)
  entries = _get_model_config_entries(data.get('models'))
  output_file = _resolve_output_file(section, output_file)

  config = {}
  for entry in entries:
    scenescape_name, output_config = _build_config_entry(
      entry,
      downloader_models,
    )
    if scenescape_name in config:
      raise ValueError(f'Duplicate scenescape_name in model_config: {scenescape_name}')
    config[scenescape_name] = output_config

  output_dir = models_path_obj / 'model_configs'
  output_dir.mkdir(exist_ok=True)
  output_path = output_dir / output_file

  with open(output_path, 'w', encoding='utf-8') as handle:
    json.dump(config, handle, indent=2)

  print(f'Generated configuration with {len(config)} models:')
  for name, conf in config.items():
    model_path = conf['params']['model']
    print(f'  {name}: {model_path}')

  print(f'\nConfiguration saved to: {output_path}')
  return config


def _build_arg_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser()
  parser.add_argument('--models-path', type=str, default='/models')
  parser.add_argument('--config-file', type=str, default=str(_DEFAULT_CONFIG_FILE))
  parser.add_argument('--output-file', type=str, default=None)
  return parser


def main() -> int:
  parser = _build_arg_parser()
  args = parser.parse_args()

  try:
    generate_model_config_from_models(
      models_path=args.models_path,
      config_file=args.config_file,
      output_file=args.output_file,
    )
  except (OSError, ValueError, json.JSONDecodeError) as exc:
    print(f'Error: {exc}')
    return 1

  return 0


if __name__ == '__main__':
  raise SystemExit(main())


