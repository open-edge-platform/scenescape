# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from tools.reid_evaluation.evaluate import (
    build_parser, calibrate_threshold, load_manifest, run_evaluation, score_queries, summarize,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE = REPO_ROOT / "tools/reid_evaluation/examples/smoke.json"


def samples():
  return [
      {"id": "ga", "identity": "a", "camera": "gallery", "split": "gallery", "embedding": [1, 0]},
      {"id": "gb", "identity": "b", "camera": "gallery", "split": "gallery", "embedding": [0, 1]},
      {"id": "qa", "identity": "a", "camera": "query", "split": "test", "embedding": [1, 0]},
      {"id": "qb", "identity": "b", "camera": "query", "split": "test", "embedding": [0, 1]},
      {"id": "qu", "identity": "unknown", "camera": "query",
       "split": "test", "embedding": [-1, -1]},
  ]


def test_known_and_unknown_metrics_have_correct_denominators():
  metrics, predictions = summarize(score_queries(samples()), 0.5)
  assert metrics["rank1"] == 1
  assert metrics["mAP"] == 1
  assert metrics["known_queries"] == 2
  assert metrics["unknown_queries"] == 1
  assert metrics["true_identification_rate"] == 1
  assert metrics["unknown_false_accept_rate"] == 0
  assert predictions[-1]["predicted_identity"] is None


def test_wrong_identity_and_unknown_accepts_are_not_counted_as_successes():
  data = samples()
  data[2]["embedding"] = [0, 1]
  data[-1]["embedding"] = [1, 0]
  metrics, _ = summarize(score_queries(data), 0.5)
  assert metrics["rank1"] == 0.5
  assert metrics["mAP"] == 0.75
  assert metrics["known_misidentification_rate"] == 0.5
  assert metrics["unknown_false_accept_rate"] == 1


def test_same_camera_positives_are_skipped_not_reclassified_as_unknown():
  data = samples()
  data[2]["camera"] = "gallery"
  metrics, _ = summarize(score_queries(data), 0.5)
  assert metrics["skipped_queries"] == 1
  assert metrics["known_queries"] == 1
  assert metrics["unknown_queries"] == 1


@pytest.mark.parametrize("embedding", [[0, 0], [float("nan"), 1], [float("inf"), 0], [], [1, 2, 3]])
def test_invalid_embeddings_are_rejected(embedding):
  data = samples()
  data[2]["embedding"] = embedding
  with pytest.raises(ValueError):
    score_queries(data)


def test_calibration_uses_separate_queries_and_requires_unknowns():
  data = samples()
  for sample in data[2:]:
    sample["split"] = "calibration"
  rows = score_queries(data, split="calibration")
  threshold, metrics = calibrate_threshold(rows, target_false_accept_rate=0)
  assert -1 <= threshold <= 1
  assert metrics["unknown_false_accept_rate"] == 0
  assert metrics["true_identification_rate"] == 1
  with pytest.raises(ValueError, match="known and unknown"):
    calibrate_threshold([row for row in rows if row["known"]])


def test_l2_threshold_direction_and_empty_gallery():
  metrics, _ = summarize(score_queries(samples(), metric="L2"), 0.1, "L2")
  assert metrics["true_identification_rate"] == 1
  assert metrics["unknown_false_accept_rate"] == 0
  with pytest.raises(ValueError):
    score_queries(samples()[2:])


def test_multiple_relevant_gallery_entries_have_standard_average_precision():
  data = samples()
  data.append({"id": "gc", "identity": "a", "camera": "gallery", "split": "gallery",
               "embedding": [-1, 0]})
  row = score_queries(data)[0]
  assert row["average_precision"] == pytest.approx((1 + 2 / 3) / 2)


def test_same_track_is_excluded_even_when_same_camera_is_allowed():
  data = samples()
  data[0].update(camera="query", track_id="same")
  data[2]["track_id"] = "same"
  rows = score_queries(data, cross_camera=False)
  assert rows[0]["skipped"]


def test_impossible_false_accept_target_is_reported():
  data = samples()
  data[-1]["embedding"] = [1, 0]
  with pytest.raises(ValueError, match="cannot be met"):
    calibrate_threshold(score_queries(data), target_false_accept_rate=0)


def test_duplicate_ids_and_invalid_thresholds_are_rejected():
  data = samples()
  data[2]["id"] = data[0]["id"]
  with pytest.raises(ValueError, match="unique"):
    score_queries(data)
  for threshold in (float("nan"), float("inf"), -2, 2):
    with pytest.raises(ValueError):
      summarize(score_queries(samples()), threshold)


def test_cli_writes_auditable_reports_and_cached_comparison(tmp_path):
  first = tmp_path / "baseline"
  args = build_parser().parse_args(
      ["--manifest", str(SMOKE), "--output", str(first), "--calibrate"])
  report = run_evaluation(args)
  assert report["threshold_source"] == "calibration"
  assert report["runtime"]["inference_ms"] is None
  assert report["unique_count_error"] is None
  assert any("SYNTHETIC" in warning for warning in report["warnings"])
  for name in ("report.json", "scorecard.csv", "scorecard.md", "predictions.csv",
               "threshold_sweep.csv", "embeddings.json"):
    assert (first / name).is_file()
  second = tmp_path / "candidate"
  args = build_parser().parse_args([
      "--manifest", str(first / "embeddings.json"), "--output", str(second), "--calibrate",
      "--baseline", str(first / "report.json"),
  ])
  compared = run_evaluation(args)
  assert compared["comparison"]["metric_delta"]["rank1"] == 0
  assert compared["comparison"]["metric_delta"]["unknown_false_accept_rate"] == 0
  with pytest.raises(ValueError, match="already exists"):
    run_evaluation(args)


def test_calibration_rejects_identity_leakage_and_mismatched_baselines(tmp_path):
  manifest = json.loads(SMOKE.read_text())
  manifest["samples"][-1]["identity"] = manifest["samples"][-3]["identity"]
  leaked = tmp_path / "leaked.json"
  leaked.write_text(json.dumps(manifest))
  args = build_parser().parse_args(
      ["--manifest", str(leaked), "--output", str(tmp_path / "out"), "--calibrate"])
  with pytest.raises(ValueError, match="disjoint"):
    run_evaluation(args)
  baseline = tmp_path / "unrelated.json"
  baseline.write_text(json.dumps({"dataset": {"protocol_sha256": "different"}}))
  args = build_parser().parse_args([
      "--manifest", str(SMOKE), "--output", str(tmp_path / "out"), "--baseline", str(baseline),
  ])
  with pytest.raises(ValueError, match="different dataset"):
    run_evaluation(args)
  assert not args.output.exists()


def test_manifest_rejects_mixed_sources_and_duplicate_source_images(tmp_path):
  manifest = json.loads(SMOKE.read_text())
  manifest["samples"][0]["image"] = "crop.jpg"
  path = tmp_path / "manifest.json"
  path.write_text(json.dumps(manifest))
  with pytest.raises(ValueError, match="exactly one"):
    load_manifest(path)
  del manifest["samples"][0]["image"]
  manifest["samples"][0]["source_image_sha256"] = "same-image"
  manifest["samples"][-1]["source_image_sha256"] = "same-image"
  path.write_text(json.dumps(manifest))
  with pytest.raises(ValueError, match="multiple splits"):
    load_manifest(path)


def test_module_entrypoint_runs_without_a_live_stack(tmp_path):
  result = subprocess.run([
      sys.executable, "-m", "tools.reid_evaluation.evaluate", "--manifest", str(SMOKE),
      "--output", str(tmp_path / "run"),
  ], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
  assert result.returncode == 0, result.stderr
  assert "SYNTHETIC SMOKE" in result.stderr
  assert json.loads(result.stdout)["model"] == "synthetic-unit-vectors-not-a-trained-model"


def test_csv_exports_escape_formula_like_person_labels(tmp_path):
  manifest = json.loads(SMOKE.read_text())
  for sample in manifest["samples"]:
    if sample["identity"] == "person-b":
      sample["identity"] = "=untrusted-label"
  path = tmp_path / "manifest.json"
  path.write_text(json.dumps(manifest))
  output = tmp_path / "run"
  args = build_parser().parse_args(["--manifest", str(path), "--output", str(output)])

  run_evaluation(args)

  with (output / "predictions.csv").open() as stream:
    rows = list(csv.DictReader(stream))
  assert rows[0]["identity"] == "'=untrusted-label"
  assert rows[0]["candidate"] == "'=untrusted-label"


def test_openvino_crop_inference_records_preprocessing_and_model_hashes(tmp_path):
  ov = pytest.importorskip("openvino")
  image_module = pytest.importorskip("PIL.Image")
  from tools.reid_evaluation.inference import extract_embeddings

  pixels = ov.opset13.parameter([1, 3, 2, 2], np.float32)
  pooled = ov.opset13.reduce_mean(pixels, ov.opset13.constant([2, 3]), keep_dims=False)
  model_path = tmp_path / "synthetic.xml"
  ov.save_model(ov.Model([pooled], [pixels]), model_path, compress_to_fp16=False)
  image_module.new("RGB", (4, 4), (10, 20, 30)).save(tmp_path / "crop.png")
  rows = [{"id": "sample", "identity": "a", "camera": "cam", "split": "gallery", "image": "crop.png"}]

  prepared, model, runtime = extract_embeddings(rows, tmp_path, model_path, warmup=1)

  np.testing.assert_array_equal(prepared[0]["embedding"], [30, 20, 10])
  assert "image" not in prepared[0]
  assert len(model["xml_sha256"]) == 64
  assert len(model["bin_sha256"]) == 64
  assert model["preprocessing"]["color_order"] == "BGR"
  assert runtime["inference_ms"]["p50"] >= 0
