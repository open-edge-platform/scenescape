# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run in each Mapping test image without downloading model weights."""

import importlib
import importlib.metadata
import importlib.util
import os
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest
import torch


@pytest.fixture(scope="module")
def runtime_model():
  model_type = os.environ["MODEL_TYPE"]
  module = importlib.import_module(f"{model_type}_model")
  model_class = module.MapAnythingModel if model_type == "mapanything" else module.VGGTModel
  return model_class(device="cpu")


@pytest.mark.parametrize("package,version", [
  ("Pillow", "13.0.0"),
  ("torch", "2.13.0"),
])
def test_security_versions_installed(package, version):
  assert importlib.metadata.version(package).split("+")[0] == version


def test_runtime_dependencies_consistent():
  result = subprocess.run(
    [sys.executable, "-m", "pip", "check"], capture_output=True, text=True, check=False
  )
  assert result.returncode == 0, result.stdout + result.stderr


def test_demo_ui_not_installed():
  assert importlib.util.find_spec("gradio") is None


def test_audio_dependency_not_installed():
  assert importlib.util.find_spec("torchaudio") is None


@pytest.mark.parametrize("size", [(64, 64), (96, 64), (64, 96)])
def test_model_preprocessing_with_patched_pillow(runtime_model, size):
  image = Image.new("RGB", size, color=(20, 40, 60))
  processed = runtime_model._preprocess_images([image])
  tensor = processed[0]["img"] if runtime_model.model_name == "mapanything" else processed[0]
  assert tensor.shape[:2] == (1, 3)
  assert tensor.shape[-2] > 0 and tensor.shape[-1] > 0
  assert torch.isfinite(tensor).all()
  assert not runtime_model.is_loaded


@pytest.mark.parametrize("output_format", ["mesh", "pointcloud"])
def test_model_export_without_demo_dependencies(runtime_model, output_format):
  x, y = np.meshgrid(np.arange(4) * 0.01, np.arange(4) * 0.01)
  points = np.stack([x, y, np.ones_like(x)], axis=-1)[None].astype(np.float32)
  predictions = {
    "world_points": points,
    "world_points_from_depth": points.copy(),
    "world_points_conf": np.ones((1, 4, 4), dtype=np.float32),
    "images": np.full((1, 4, 4, 3), 0.5, dtype=np.float32),
    "final_masks": np.ones((1, 4, 4), dtype=bool),
    "extrinsic": np.eye(4, dtype=np.float32)[None, :3],
  }
  scene = runtime_model.create_output({"predictions": predictions}, output_format=output_format)
  assert scene.geometry
  assert scene.export(file_type="glb").startswith(b"glTF")


def test_visualization_rejects_invalid_predictions(runtime_model):
  module_name = (
    "mapanything.utils.viz" if runtime_model.model_name == "mapanything" else "visual_util"
  )
  visualization = importlib.import_module(module_name)
  with pytest.raises(ValueError, match="dictionary"):
    visualization.predictions_to_glb([])
