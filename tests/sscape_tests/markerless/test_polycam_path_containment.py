# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import zipfile
from unittest.mock import patch

import pytest

from auto_camera_calibration_model import CalibrationScene
from markerless_camera_calibration_controller import MarkerlessCameraCalibrationController


def makeScene(name, polycam_data=None):
  scene = CalibrationScene(
      uid="f1b9b1b0-1b1b-1b1b-1b1b-1b1b1b1b1b1b", name=name)
  scene.polycam_data = polycam_data
  return scene


@pytest.fixture
def controller():
  return MarkerlessCameraCalibrationController(calibration_data_interface=None)


@pytest.mark.parametrize("malicious_name", [
    "../../reloc/hloc/extractors",
    "..",
    "/etc",
    "a/../../b",
])
def test_preprocess_polycam_dataset_rejects_escaping_name(tmp_path, controller, malicious_name, monkeypatch):
  """! A scene name that resolves outside datasets/ must be rejected before extraction. """
  monkeypatch.chdir(tmp_path)
  zip_path = tmp_path / "polycam.zip"
  with zipfile.ZipFile(zip_path, "w") as zf:
    zf.writestr("keyframes/marker.txt", "harmless")
  scene = makeScene(malicious_name, polycam_data=str(zip_path))

  with pytest.raises(ValueError):
    controller.preprocess_polycam_dataset(scene)

  datasets_root = tmp_path / "datasets"
  if datasets_root.exists():
    for path in datasets_root.rglob("*"):
      assert path.resolve().is_relative_to(datasets_root.resolve())


def test_is_within_datasets_root_allows_safe_name(controller, tmp_path, monkeypatch):
  """! A normal scene name is accepted by the containment check. """
  monkeypatch.chdir(tmp_path)
  assert controller._is_within_datasets_root(
      tmp_path / "datasets" / "my-scene")
  assert controller._is_within_datasets_root(
      tmp_path / "datasets" / "sub" / "dir")


def test_is_within_datasets_root_rejects_escape(controller, tmp_path, monkeypatch):
  """! Direct unit check of the containment helper used by both extraction and cleanup. """
  monkeypatch.chdir(tmp_path)
  assert not controller._is_within_datasets_root(
      tmp_path / "datasets" / ".." / ".." / "etc")


def test_reset_scene_skips_rmtree_for_escaping_output_dir(controller, tmp_path, monkeypatch):
  """! reset_scene must not delete a directory outside datasets/, even if output_dir is poisoned. """
  monkeypatch.chdir(tmp_path)
  outside_dir = tmp_path / "outside"
  outside_dir.mkdir()

  scene = makeScene("my-scene")
  scene.output_dir = str(outside_dir)

  with patch("shutil.rmtree") as mocked_rmtree:
    controller.reset_scene(scene)
    mocked_rmtree.assert_not_called()

  assert outside_dir.is_dir()
