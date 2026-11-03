# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace

import numpy as np
import pytest

from tools.reid_evaluation.evaluate import load_manifest, score_queries
from tools.reid_evaluation.physicalai import _observations, export_physicalai, main


def _object(identity=1, box=None):
  return {"object_type": "Person", "object_id": identity,
          "2d_bounding_box_visible": {"Camera_0": box or [2, 2, 20, 28],
                                      "Camera_1": box or [2, 2, 20, 28]}}


def _scene(tmp_path):
  cv2 = pytest.importorskip("cv2")
  for camera in ("Camera_0", "Camera_1"):
    path = tmp_path / f"{camera}.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (32, 32))
    assert writer.isOpened()
    for frame in range(4):
      pixels = np.full((32, 32, 3), 30 + frame * 30, dtype=np.uint8)
      writer.write(pixels)
    writer.release()
  truth = tmp_path / "ground_truth.json"
  truth.write_text(json.dumps({str(frame): [_object()] for frame in range(4)}))
  mapping = tmp_path / "videos.json"
  mapping.write_text(json.dumps({camera: f"{camera}.avi" for camera in ("Camera_0", "Camera_1")}))
  return SimpleNamespace(
    scene="physicalai-2025-fixture", object_type="Person", frame_step=1, max_frames=4,
    query_gap_frames=2, minimum_area=0, output=tmp_path / "export",
    ground_truth=truth, videos=mapping, gallery_camera="Camera_0")


def test_real_video_extraction_and_cross_camera_scoring(tmp_path):
  args = _scene(tmp_path)
  result = export_physicalai(args)
  manifest = load_manifest(args.output / "manifest.json")
  assert result["samples_by_split"] == {"gallery": 1, "test": 2}
  samples = manifest["samples"]
  assert [s["frame"] for s in samples] == [0, 2, 3]
  assert samples[0]["identity"] == "physicalai-2025-fixture:1"
  assert len({s["id"] for s in samples}) == 3
  cv2 = pytest.importorskip("cv2")
  for sample in samples:
    crop = cv2.imread(sample["image"])
    assert crop.shape[:2] == (26, 18)
    assert abs(float(crop.mean()) - (30 + sample["frame"] * 30)) < 5
    sample["embedding"] = [1, 0]
  assert all(row["correct"] for row in score_queries(samples))
  assert manifest["dataset"]["excluded_observations"] == {
    "extra_gallery_camera_observation": 3, "query_before_gap": 2}
  with pytest.raises(ValueError, match="already exists"):
    export_physicalai(args)
  args.output = tmp_path / "repeat"
  export_physicalai(args)
  assert [s["id"] for s in load_manifest(args.output / "manifest.json")["samples"]] == [
    s["id"] for s in samples]


@pytest.mark.parametrize("box", [[1, 2, 0, 5], [0, 0, float("nan"), 4], [0, 1], "bad"])
def test_invalid_ground_truth_boxes_fail(box):
  with pytest.raises(ValueError, match="bounding box"):
    _observations({"0": [_object(box=box)]}, {"Camera_0": "a"}, "Person", 1, 1)


def test_duplicate_objects_and_invalid_frames_fail():
  with pytest.raises(ValueError, match="Duplicate object"):
    _observations({"0": [_object(), _object()]}, {"Camera_0": "a"}, "Person", 1, 1)
  with pytest.raises(ValueError, match="frame IDs"):
    _observations({"invalid": []}, {}, "Person", 1, 1)
  with pytest.raises(ValueError, match="No sampled"):
    _observations({"0": [_object()]}, {"other": "a"}, "Person", 1, 1)


def test_actual_spaced_annotation_keys_and_ambiguous_fields():
  obj = {key.replace("_", " "): value for key, value in _object(identity=0).items()}
  rows = _observations({"0": [obj]}, {"Camera_0": "video"}, "Person", 1, 1)
  assert rows[0]["identity"] == 0
  assert rows[0]["box"] == [2, 2, 20, 28]
  obj["object_id"] = 1
  with pytest.raises(ValueError, match="Ambiguous"):
    _observations({"0": [obj]}, {"Camera_0": "video"}, "Person", 1, 1)


@pytest.mark.parametrize("problem", ["video", "gallery", "no-test", "truncated", "small"])
def test_export_failures_do_not_write_success_manifest(tmp_path, problem):
  args = _scene(tmp_path)
  if problem == "video":
    (tmp_path / "Camera_1.avi").unlink()
  elif problem == "gallery":
    args.gallery_camera = "missing"
  elif problem == "no-test":
    args.query_gap_frames = 100
  elif problem == "small":
    args.minimum_area = 10000
  else:
    args.ground_truth.write_text(json.dumps({"10": [_object()]}))
  with pytest.raises(ValueError):
    export_physicalai(args)
  assert not (args.output / "manifest.json").exists()


def test_cli_export(tmp_path, capsys):
  args = _scene(tmp_path)
  assert main([
    "--ground-truth", str(args.ground_truth), "--videos", str(args.videos),
    "--scene", args.scene, "--gallery-camera", args.gallery_camera,
    "--frame-step", "1", "--query-gap-frames", "2", "--minimum-area", "0",
    "--output", str(args.output),
  ]) == 0
  assert json.loads(capsys.readouterr().out)["samples"] == 3
