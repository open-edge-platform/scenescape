# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evaluate labeled ReID embeddings without writing to a live gallery."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import sys
import time

import numpy as np

DEFAULT_MODEL = "person-reidentification-retail-0277"
SPLITS = {"gallery", "calibration", "test"}


def score_queries(samples, split="test", metric="COSINE", cross_camera=True):
  """Rank eligible gallery samples for each query, excluding self/track leakage."""
  metric = metric.upper()
  if metric not in {"COSINE", "L2"}:
    raise ValueError("Metric must be COSINE or L2")
  if split not in {"calibration", "test"}:
    raise ValueError("Queries must use the calibration or test split")
  seen = set()
  dimensions = None
  vectors = {}
  for sample in samples:
    for key in ("id", "identity", "camera"):
      if not isinstance(sample.get(key), str) or not sample[key].strip():
        raise ValueError(f"Each sample requires a non-empty {key}")
    if sample["id"] in seen:
      raise ValueError("Sample IDs must be unique across all splits")
    seen.add(sample["id"])
    if sample.get("split") not in SPLITS:
      raise ValueError("Invalid sample split")
    vector = np.asarray(sample.get("embedding"), dtype=np.float64)
    if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all():
      raise ValueError("Embeddings must be non-empty finite numeric vectors")
    if dimensions is not None and vector.size != dimensions:
      raise ValueError("All embeddings in a run must have the same dimensions")
    dimensions = vector.size
    if metric == "COSINE":
      norm = np.linalg.norm(vector)
      if not math.isfinite(norm) or norm == 0:
        raise ValueError("Cosine embeddings require a finite, non-zero norm")
      vector = vector / norm
    vectors[sample["id"]] = vector

  gallery = sorted((sample for sample in samples if sample["split"] == "gallery"),
                   key=lambda sample: sample["id"])
  queries = [sample for sample in samples if sample["split"] == split]
  if not gallery or not queries:
    raise ValueError(f"Evaluation requires gallery and {split} samples")
  gallery_identities = {sample["identity"] for sample in gallery}
  rows = []
  for query in queries:
    eligible = [sample for sample in gallery
                if (not cross_camera or sample["camera"] != query["camera"])
                and not (query.get("track_id") not in (None, "")
                         and sample.get("track_id") == query["track_id"]
                         and sample["camera"] == query["camera"])]
    known = query["identity"] in gallery_identities
    if not eligible or (known and not any(
            sample["identity"] == query["identity"] for sample in eligible)):
      rows.append({"id": query["id"], "identity": query["identity"], "skipped": True})
      continue
    matrix = np.stack([vectors[sample["id"]] for sample in eligible])
    vector = vectors[query["id"]]
    scores = (np.clip(matrix @ vector, -1.0, 1.0) if metric == "COSINE"
              else np.linalg.norm(matrix - vector, axis=1))
    if not np.isfinite(scores).all():
      raise ValueError("Scoring produced non-finite distances; check embedding magnitudes")
    order = np.argsort(-scores if metric == "COSINE" else scores, kind="stable")
    relevant = np.asarray([eligible[index]["identity"] == query["identity"] for index in order])
    ranks = np.flatnonzero(relevant) + 1
    average_precision = float(np.mean(np.arange(1, len(ranks) + 1) / ranks)) if known else None
    rows.append({
        "id": query["id"], "identity": query["identity"], "camera": query["camera"],
        "known": known, "skipped": False, "candidate": eligible[order[0]]["identity"],
        "score": float(scores[order[0]]), "correct": bool(relevant[0]),
        "rank1": bool(relevant[0]) if known else None, "average_precision": average_precision,
    })
  return rows


def summarize(rows, threshold, metric="COSINE"):
  """Compute retrieval and open-set identification metrics with explicit denominators."""
  metric = metric.upper()
  if metric not in {"COSINE", "L2"} or not math.isfinite(threshold):
    raise ValueError("A supported metric and finite threshold are required")
  if (metric == "COSINE" and not -1 <= threshold <= 1) or (metric == "L2" and threshold < 0):
    raise ValueError("Threshold is outside the metric's valid range")
  predictions = []
  for row in rows:
    if row["skipped"]:
      continue
    accepted = row["score"] >= threshold if metric == "COSINE" else row["score"] <= threshold
    predictions.append({**row, "accepted": accepted,
                        "predicted_identity": row["candidate"] if accepted else None})
  known = [row for row in predictions if row["known"]]
  unknown = [row for row in predictions if not row["known"]]
  correct = sum(row["accepted"] and row["correct"] for row in known)
  wrong = sum(row["accepted"] and not row["correct"] for row in known)
  rejected = sum(not row["accepted"] for row in known)
  false_accepts = sum(row["accepted"] for row in unknown)

  def rate(count, total):
    return count / total if total else None

  return {
      "query_count": len(rows), "evaluated_queries": len(predictions),
      "skipped_queries": len(rows) - len(predictions),
      "known_queries": len(known), "unknown_queries": len(unknown),
      "rank1": rate(sum(row["rank1"] for row in known), len(known)),
      "mAP": float(np.mean([row["average_precision"] for row in known])) if known else None,
      "correct_known_accepts": correct, "known_misidentifications": wrong,
      "known_rejections": rejected, "unknown_false_accepts": false_accepts,
      "true_identification_rate": rate(correct, len(known)),
      "known_misidentification_rate": rate(wrong, len(known)),
      "known_rejection_rate": rate(rejected, len(known)),
      "false_negative_identification_rate": rate(wrong + rejected, len(known)),
      "unknown_false_accept_rate": rate(false_accepts, len(unknown)),
  }, predictions


def calibrate_threshold(rows, metric="COSINE", target_false_accept_rate=0.01):
  """Choose an operating point on calibration data, never on the test split."""
  metric = metric.upper()
  if not 0 <= target_false_accept_rate <= 1:
    raise ValueError("Target false accept rate must be between 0 and 1")
  usable = [row for row in rows if not row["skipped"]]
  if not any(row["known"] for row in usable) or not any(not row["known"] for row in usable):
    raise ValueError("Calibration requires eligible known and unknown queries")
  candidates = {row["score"] for row in usable}
  direction = math.inf if metric == "COSINE" else -math.inf
  candidates.update(float(np.nextafter(score, direction)) for score in list(candidates))
  candidates.update({-1.0, 1.0} if metric == "COSINE" else {0.0})
  best = None
  for threshold in sorted(candidates):
    if (metric == "COSINE" and not -1 <= threshold <= 1) or threshold < 0 and metric == "L2":
      continue
    metrics, _ = summarize(rows, threshold, metric)
    if metrics["unknown_false_accept_rate"] > target_false_accept_rate:
      continue
    quality = (metrics["true_identification_rate"], -metrics["known_misidentification_rate"],
               -metrics["unknown_false_accept_rate"], -threshold if metric == "COSINE" else threshold)
    if best is None or quality > best[0]:
      best = (quality, threshold, metrics)
  if best is None:
    raise ValueError("Requested false-accept target cannot be met with a valid threshold")
  return best[1], best[2]


def load_manifest(path):
  """Load an image or cached-embedding manifest without guessing identity labels."""
  path = Path(path)
  with path.open() as stream:
    manifest = json.load(stream)
  if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list):
    raise ValueError("Manifest must be an object containing a samples list")
  if not manifest["samples"]:
    raise ValueError("Manifest samples must not be empty")
  modes = set()
  image_splits = {}
  for sample in manifest["samples"]:
    if not isinstance(sample, dict):
      raise ValueError("Each sample must be an object")
    modes.add("embedding" in sample)
    if ("embedding" in sample) == ("image" in sample):
      raise ValueError("Each sample must contain exactly one of image or embedding")
    for key in ("id", "identity", "camera", "split"):
      if not isinstance(sample.get(key), str) or not sample[key].strip():
        raise ValueError(f"Each sample requires a non-empty {key}")
    if sample["split"] not in SPLITS:
      raise ValueError("Sample split must be gallery, calibration, or test")
    image_hash = sample.get("source_image_sha256")
    if image_hash:
      if image_hash in image_splits and image_splits[image_hash] != sample["split"]:
        raise ValueError("The same source image appears in multiple splits")
      image_splits[image_hash] = sample["split"]
  if len(modes) != 1:
    raise ValueError("Do not mix images and cached embeddings in one run")
  return manifest


def _write_csv(path, rows, fieldnames):
  with path.open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
      escaped = {}
      for key, value in row.items():
        if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@"))
                                       or value.startswith(("\t", "\r", "\n"))):
          value = "'" + value
        escaped[key] = value
      writer.writerow(escaped)


def _format_metric(value):
  return "not measured" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)


def write_reports(output, report, predictions, sweep, samples):
  """Write auditable scorecards, per-query decisions, calibration curves, and embeddings."""
  output.mkdir(parents=True, exist_ok=False)
  (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
  _write_csv(output / "predictions.csv", predictions,
             ["id", "identity", "camera", "known", "candidate", "score", "accepted",
              "predicted_identity", "correct", "rank1", "average_precision"])
  _write_csv(output / "threshold_sweep.csv", sweep,
             ["threshold", "true_identification_rate", "known_misidentification_rate",
              "known_rejection_rate", "unknown_false_accept_rate"])
  flat = {"model": report["model"]["name"], "version": report["model"]["version"],
          "embedding_dimensions": report["embedding_dimensions"], "metric": report["metric"],
          "threshold": report["threshold"], "threshold_source": report["threshold_source"],
          "preprocessing": json.dumps(report["model"]["preprocessing"], sort_keys=True),
          "xml_sha256": report["model"].get("xml_sha256"),
          "dataset_protocol_sha256": report["dataset"]["protocol_sha256"],
          "inference_mean_ms": (report["runtime"]["inference_ms"] or {}).get("mean"),
          "peak_process_rss_mib": report["runtime"]["peak_process_rss_mib"],
          "unique_count_error": None, **report["metrics"]}
  _write_csv(output / "scorecard.csv", [flat], list(flat))
  cached = {"dataset": report["dataset"]["description"],
            "model": report["model"], "samples": samples}
  (output / "embeddings.json").write_text(json.dumps(cached, indent=2, allow_nan=False) + "\n")
  lines = ["# ReID Model Scorecard", "", f"Model: **{report['model']['name']}**",
           f"Version: `{report['model']['version']}`", "",
           f"Metric: {report['metric']}; threshold: {report['threshold']:.6g}; "
           f"embedding dimensions: {report['embedding_dimensions']}", "",
           "| Metric | Value |", "| --- | --- |"]
  lines.extend(f"| {key} | {_format_metric(value)} |" for key, value in report["metrics"].items())
  lines.extend(["", "## Preprocessing", "", "```json",
                json.dumps(report["model"]["preprocessing"], indent=2), "```",
                "", "## Runtime", "", "```json",
                json.dumps(report["runtime"], indent=2), "```"])
  lines.extend(["", "## Limitations", ""])
  lines.extend(f"- {warning}" for warning in report["warnings"])
  (output / "scorecard.md").write_text("\n".join(lines) + "\n")


def run_evaluation(args):
  """Run fixed-threshold or separately calibrated evaluation and optional baseline comparison."""
  from tools.reid_evaluation.inference import extract_embeddings, file_sha256

  started = time.perf_counter()
  cpu_started = time.process_time()
  manifest_path = Path(args.manifest).resolve()
  output = Path(args.output).resolve()
  if output.exists():
    raise ValueError("Output directory already exists; use a new directory for each run")
  manifest = load_manifest(manifest_path)
  samples = manifest["samples"]
  image_mode = "image" in samples[0]
  if args.calibrate:
    calibration_ids = {sample["identity"] for sample in samples if sample["split"] == "calibration"}
    test_ids = {sample["identity"] for sample in samples if sample["split"] == "test"}
    if calibration_ids & test_ids:
      raise ValueError("Calibration and test identities must be disjoint")
  if image_mode:
    if not args.model:
      raise ValueError("Image manifests require --model pointing to an OpenVINO IR .xml")
    samples, model, runtime = extract_embeddings(
        samples, manifest_path.parent, args.model, args.device, args.color_order, args.layout,
        args.pixel_scale, args.mean, args.std, args.warmup, args.output_name)
    model["name"] = args.model_name or Path(args.model).stem
    model["version"] = args.model_version or "artifact-sha256:" + model["xml_sha256"][:12]
  else:
    if args.model:
      raise ValueError("Cached embedding manifests do not run --model inference")
    model = manifest.get("model", {})
    if not isinstance(model, dict) or not all(model.get(key) for key in ("name", "version", "preprocessing")):
      raise ValueError("Cached embeddings require model name, version, and preprocessing metadata")
    runtime = {"source": "cached_embeddings", "inference_ms": None,
               "preprocessing_ms": None, "serial_inference_crops_per_second": None}
  test_rows = score_queries(samples, "test", args.metric, not args.allow_same_camera)
  if not any(not row["skipped"] for row in test_rows):
    raise ValueError("No eligible test queries remain after camera/track exclusions")
  threshold = args.threshold
  configured_metrics, _ = summarize(test_rows, threshold, args.metric)
  calibration_metrics = None
  sweep = []
  if args.calibrate:
    calibration_rows = score_queries(
        samples, "calibration", args.metric, not args.allow_same_camera)
    threshold, calibration_metrics = calibrate_threshold(
        calibration_rows, args.metric, args.target_false_accept_rate)
    for candidate in sorted({row["score"] for row in calibration_rows if not row["skipped"]} | {threshold}):
      measured, _ = summarize(calibration_rows, candidate, args.metric)
      sweep.append({"threshold": candidate, **measured})
  metrics, predictions = summarize(test_rows, threshold, args.metric)
  protocol = {"cross_camera_only": not args.allow_same_camera,
              "samples": [{key: sample.get(key) for key in
                           ("id", "identity", "camera", "split", "track_id", "source_image_sha256")}
                          for sample in sorted(samples, key=lambda sample: sample["id"])]}
  protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
  warnings = [
      "Offline crop/embedding retrieval only; not a full SceneScape tracker/ReID replay.",
      "Unique-count error, GPU utilization, and end-to-end decision latency are not measured.",
      "Threshold calibration targets observed unknown-query false accepts, not a population guarantee.",
      "L2 is Euclidean distance here; do not reuse thresholds from squared-distance backends.",
      "Same-camera gallery entries are excluded by default; ties use stable gallery sample-ID order.",
  ]
  if metrics["unknown_queries"] == 0:
    warnings.append("No unknown test identities: unknown false-accept rate cannot be measured.")
  if metrics["unknown_queries"] < 100:
    warnings.append(
        "Fewer than 100 unknown test queries: low false-accept estimates are poorly supported.")
  if not image_mode:
    warnings.append(
        "Cached model metadata is user-supplied; inference timing was not measured in this run.")
  description = manifest.get("dataset", {"name": manifest_path.stem})
  if isinstance(description, dict) and description.get("synthetic"):
    warnings.append("SYNTHETIC SMOKE DATA: these numbers are not a real-model accuracy baseline.")
  report = {
      "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
      "model": model, "embedding_dimensions": len(samples[0]["embedding"]),
      "metric": args.metric, "threshold": threshold, "configured_threshold": args.threshold,
      "threshold_source": "calibration" if args.calibrate else "fixed",
      "target_calibration_false_accept_rate": args.target_false_accept_rate if args.calibrate else None,
      "calibration_metrics": calibration_metrics, "configured_threshold_metrics": configured_metrics,
      "metrics": metrics, "unique_count_error": None, "warnings": warnings,
      "dataset": {"description": description, "manifest_sha256": file_sha256(manifest_path),
                  "protocol_sha256": protocol_hash, "cross_camera_only": not args.allow_same_camera,
                  "samples_by_split": dict(Counter(sample["split"] for sample in samples))},
      "runtime": {**runtime, "evaluation_wall_seconds": time.perf_counter() - started,
                  "process_cpu_seconds": time.process_time() - cpu_started,
                  "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                  / (1024 * 1024 if sys.platform == "darwin" else 1024),
                  "python": platform.python_version(), "numpy": np.__version__,
                  "platform": platform.platform(), "machine": platform.machine()},
  }
  if args.baseline:
    with Path(args.baseline).open() as stream:
      baseline = json.load(stream)
    if baseline.get("dataset", {}).get("protocol_sha256") != protocol_hash:
      raise ValueError("Baseline uses a different dataset/exclusion protocol")
    report["comparison"] = {
        "baseline_model": baseline["model"],
        "metric_delta": {key: value - baseline["metrics"][key] for key, value in metrics.items()
                         if value is not None and baseline["metrics"].get(key) is not None},
    }
  write_reports(output, report, predictions, sweep, samples)
  return report


def build_parser():
  """Define a reproducible evaluator CLI with explicit preprocessing controls."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--manifest", required=True, type=Path)
  parser.add_argument("--output", required=True, type=Path)
  parser.add_argument("--model", type=Path, help=f"OpenVINO IR, e.g. {DEFAULT_MODEL}.xml")
  parser.add_argument("--model-name")
  parser.add_argument("--model-version")
  parser.add_argument("--device", default="CPU")
  parser.add_argument("--color-order", choices=("BGR", "RGB"), default="BGR")
  parser.add_argument("--layout", choices=("NCHW", "NHWC"), default="NCHW")
  parser.add_argument("--pixel-scale", type=float, default=1.0)
  parser.add_argument("--mean", type=float, nargs=3, default=(0, 0, 0))
  parser.add_argument("--std", type=float, nargs=3, default=(1, 1, 1))
  parser.add_argument("--warmup", type=int, default=5)
  parser.add_argument("--output-name")
  parser.add_argument("--metric", choices=("COSINE", "L2"), default="COSINE")
  parser.add_argument("--threshold", type=float, default=0.5)
  parser.add_argument("--calibrate", action="store_true")
  parser.add_argument("--target-false-accept-rate", type=float, default=0.01)
  parser.add_argument("--allow-same-camera", action="store_true")
  parser.add_argument("--baseline", type=Path,
                      help="An earlier report.json on the same dataset protocol")
  return parser


def main(argv=None):
  """Evaluate a manifest, writing artifacts only after successful validation."""
  parser = build_parser()
  try:
    report = run_evaluation(parser.parse_args(argv))
  except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
    parser.error(str(error))
  print(json.dumps({"model": report["model"]["name"], "threshold": report["threshold"],
                    "metrics": report["metrics"]}, indent=2, allow_nan=False))
  for warning in report["warnings"]:
    print(f"Note: {warning}", file=sys.stderr)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
