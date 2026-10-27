# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import csv
import json

import pytest

from tools.reid_evaluation.datasets import import_csv, import_market1501, main, write_manifest
from tools.reid_evaluation.evaluate import load_manifest, score_queries


def _market(root):
  for folder, names in {
    "bounding_box_train": ["9999_c1s1_000001_00.jpg"],
    "bounding_box_test": ["0001_c1s1_000001_00.jpg", "0000_c2s1_000001_00.jpg",
                          "-1_c1s1_000002_00.jpg"],
    "query": ["0001_c2s1_000003_00.jpg"],
  }.items():
    directory = root / folder
    directory.mkdir(parents=True)
    for name in names:
      (directory / name).write_bytes(name.encode())


def _csv(root, rows):
  path = root / "labels.csv"
  with path.open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=["id", "image", "identity", "camera", "split"])
    writer.writeheader()
    writer.writerows(rows)
  return path


def test_market_import_preserves_labels_and_ignores_training_and_junk(tmp_path):
  _market(tmp_path)
  output = tmp_path / "manifest.json"
  result = write_manifest(import_market1501(tmp_path), output)
  manifest = load_manifest(output)
  assert result["samples"] == 3
  assert result["dataset"]["excluded_junk_samples"] == 1
  assert result["samples_by_split"] == {"gallery": 2, "test": 1}
  assert {s["identity"] for s in manifest["samples"]} == {"market1501:0", "market1501:1"}
  assert len({s["id"] for s in manifest["samples"]}) == 3
  assert [s["id"] for s in import_market1501(tmp_path)["samples"]] == [
    s["id"] for s in manifest["samples"]]
  for sample in manifest["samples"]:
    sample["embedding"] = [1, 0] if sample["identity"].endswith(":1") else [0, 1]
  assert score_queries(manifest["samples"])[0]["correct"]
  with pytest.raises(FileExistsError):
    write_manifest(manifest, output)


@pytest.mark.parametrize("problem", ["missing", "empty", "filename", "query-zero"])
def test_invalid_market_layout_rejected(tmp_path, problem):
  _market(tmp_path)
  query = tmp_path / "query"
  if problem in {"missing", "empty"}:
    for image in query.iterdir():
      image.unlink()
    if problem == "missing":
      query.rmdir()
  else:
    name = "bad.jpg" if problem == "filename" else "0000_c1s1_000001_00.jpg"
    (query / name).write_bytes(b"image")
  with pytest.raises(ValueError):
    import_market1501(tmp_path)


def test_csv_import_and_cli_write_compatible_manifest(tmp_path, capsys):
  (tmp_path / "g.png").write_bytes(b"gallery")
  (tmp_path / "q.png").write_bytes(b"query")
  rows = [
    {"id": "g", "image": "g.png", "identity": "a", "camera": "1", "split": "gallery"},
    {"id": "q", "image": "q.png", "identity": "a", "camera": "2", "split": "test"},
  ]
  annotations = _csv(tmp_path, rows)
  output = tmp_path / "out.json"
  assert main(["csv", "--annotations", str(annotations), "--name", "example",
               "--output", str(output)]) == 0
  assert json.loads(capsys.readouterr().out)["samples"] == 2
  samples = load_manifest(output)["samples"]
  assert samples[0]["identity"] == "example:a"
  assert samples[0]["image"] == str(tmp_path / "g.png")
  assert import_csv(annotations, "other")["samples"][0]["id"] != samples[0]["id"]


@pytest.mark.parametrize("problem", ["duplicate-id", "duplicate-image", "missing-image",
                                    "empty-label", "split", "no-gallery", "leakage"])
def test_invalid_csv_does_not_write_manifest(tmp_path, problem):
  for name in ("g.png", "q.png"):
    (tmp_path / name).write_bytes(name.encode())
  rows = [
    {"id": "g", "image": "g.png", "identity": "a", "camera": "1", "split": "gallery"},
    {"id": "q", "image": "q.png", "identity": "a", "camera": "2", "split": "test"},
  ]
  if problem == "duplicate-id":
    rows[1]["id"] = "g"
  elif problem == "duplicate-image":
    rows[1]["image"] = "g.png"
  elif problem == "missing-image":
    rows[1]["image"] = "missing.png"
  elif problem == "empty-label":
    rows[1]["identity"] = " "
  elif problem == "split":
    rows[1]["split"] = "training"
  elif problem == "no-gallery":
    rows[0]["split"] = "test"
  else:
    (tmp_path / "c.png").write_bytes(b"calibration")
    rows.append({"id": "c", "image": "c.png", "identity": "a", "camera": "3",
                 "split": "calibration"})
  annotations = _csv(tmp_path, rows)
  output = tmp_path / "out.json"
  with pytest.raises(ValueError):
    write_manifest(import_csv(annotations, "example"), output)
  assert not output.exists()


@pytest.mark.parametrize("contents", ["image,identity\nx,a\n",
                                      "image,identity,camera,split\nx,a\n",
                                      "image,identity,camera,split\nx,a,1,test,extra\n"])
def test_malformed_csv_rejected(tmp_path, contents):
  path = tmp_path / "labels.csv"
  path.write_text(contents)
  with pytest.raises(ValueError):
    import_csv(path, "example")
