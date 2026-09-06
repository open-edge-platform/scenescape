# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared fixtures for model_download unit tests.

Adds model_download/src to sys.path so modules can be imported directly
without Docker or a container install.
"""

import copy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODEL_DOWNLOAD_SRC = _REPO_ROOT / "model_download" / "src"

if str(_MODEL_DOWNLOAD_SRC) not in sys.path:
  sys.path.insert(0, str(_MODEL_DOWNLOAD_SRC))

REAL_MODELS_JSON_PATH = _REPO_ROOT / "model_download" / "models.json"


@pytest.fixture
def real_models_json_path():
  """Path to the shared model_download/models.json used in production."""
  return str(REAL_MODELS_JSON_PATH)


@pytest.fixture
def minimal_model_entry():
  """A single valid model entry with model_downloader + scenescape config."""
  return {
    "model_downloader": {
      "name": "person-detection-retail-0013",
      "hub": "omz",
    },
    "scenescape": {
      "name": "retail",
      "config": {
        "type": "detect",
        "params": {
          "model": "omz/person-detection-retail-0013/FP16/person-detection-retail-0013.xml",
        },
        "adapter-params": {
          "metadatagenpolicy": "detectionPolicy",
        },
      },
    },
  }


@pytest.fixture
def model_entry_with_model_proc(minimal_model_entry):
  """A valid model entry that also includes scenescape.model_proc."""
  entry = copy.deepcopy(minimal_model_entry)
  entry["scenescape"]["model_proc"] = {
    "path": "object_detection/person/person-detection-retail-0013.json",
    "content": {
      "json_schema_version": "2.0.0",
      "input_preproc": [],
      "output_postproc": [
        {"labels": ["", "person"], "converter": "tensor_to_bbox_ssd"},
      ],
    },
  }
  return entry


@pytest.fixture
def valid_models_config(minimal_model_entry):
  """A minimal, fully valid models.json document."""
  return {
    "models": [minimal_model_entry],
    "model_config": {"output_file": "model_config.json"},
  }


@pytest.fixture
def write_json(tmp_path):
  """Writes a dict to a JSON file under tmp_path and returns its path."""
  def _write(data, filename="models.json"):
    file_path = tmp_path / filename
    import json
    file_path.write_text(json.dumps(data), encoding="utf-8")
    return str(file_path)
  return _write


@pytest.fixture
def models_output_dir(tmp_path):
  """A tmp_path directory to use as --models-path for generator output."""
  return tmp_path
