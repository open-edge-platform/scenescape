# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run all three BlackBox evaluation configs in a single timestamped session.

All results land under a shared session directory:

  <base_output_path>/<YYYYMMDD_HHMMSS>/
    Controller-NO-Time-Chunking/
    Controller-Time-Chunking/
    Tracker-Service/

Usage (from tools/tracker/evaluation/):
  python run_black_box_evaluation.py
  python run_black_box_evaluation.py --output /custom/output/path
  python run_black_box_evaluation.py --image-tag 2026.1.0-rc1.1
"""

import argparse
import csv
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml

# Make sure the evaluation package root is on sys.path.
sys.path.insert(0, str(Path(__file__).parent))

from pipeline_engine import PipelineEngine

# ---------------------------------------------------------------------------
# Configs to run (in order)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent

CONFIGS = [
    _SCRIPT_DIR / "pipeline_configs" / "black_box" / "black_box_controller_no_tc.yaml",
    _SCRIPT_DIR / "pipeline_configs" / "black_box" / "black_box_controller_tc.yaml",
    _SCRIPT_DIR / "pipeline_configs" / "black_box" / "black_box_tracker_service.yaml",
]

DEFAULT_OUTPUT_BASE = _SCRIPT_DIR / "output" / "black-box-evaluation"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_config(config_path: Path, session_output: Path, image_tag: str | None = None) -> dict:
  """Load *config_path*, set its output base to *session_output*, run it.

  If *image_tag* is given, the tag portion of the harness ``container_image``
  is replaced with that value so the locally-built images are used.

  Returns the metrics dict from PipelineEngine.evaluate().
  """
  with open(config_path) as f:
    cfg = yaml.safe_load(f)

  # Redirect output into the shared session directory.
  # PipelineEngine will append run_name as a subdirectory.
  cfg["pipeline"]["output"]["path"] = str(session_output)

  if image_tag:
    existing = cfg["harness"]["config"].get("container_image", "")
    image_name = existing.rsplit(":", 1)[0] if ":" in existing else existing
    cfg["harness"]["config"]["container_image"] = f"{image_name}:{image_tag}"

  engine = PipelineEngine()
  # Inject patched config directly so we don't need a temp file.
  engine._config = cfg
  engine._create_run_output_directory()
  engine._dataset = engine._create_component("dataset")
  engine._harness = engine._create_component("harness")
  engine._evaluators = [
      engine._create_component("evaluators", index=i)
      for i in range(len(cfg["evaluators"]))
  ]
  engine._configure_dataset()
  engine._configure_harness()
  engine._configure_evaluators()

  engine.run()
  metrics = engine.evaluate()
  print(f"\nResults saved to: {engine._output_path}")
  return metrics


def _save_metrics_csv(session_output: Path, results: list[tuple[str, dict | Exception]]) -> Path:
  """Write all successful evaluation results to *session_output*/metrics.csv.

  CSV columns: run_name, evaluator, metric, value

  Returns the path to the written CSV file.
  """
  csv_path = session_output / "metrics.csv"
  with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["run_name", "evaluator", "metric", "value"])
    for run_name, result in results:
      if isinstance(result, Exception):
        continue
      for evaluator, metrics in result.items():
        for metric, value in metrics.items():
          writer.writerow([run_name, evaluator, metric, value])
  return csv_path


def _print_summary(session_output: Path, results: list[tuple[str, dict | Exception]]) -> None:
  """Print a compact per-config metrics table."""
  divider = "=" * 72
  print(f"\n{divider}")
  print(f"  Session: {session_output}")
  print(divider)

  for run_name, result in results:
    print(f"\n  [{run_name}]")
    if isinstance(result, Exception):
      print(f"    FAILED: {result}")
    else:
      for evaluator, metrics in result.items():
        print(f"    {evaluator}:")
        for metric, value in metrics.items():
          print(f"      {metric}: {value:.4f}" if isinstance(value, float) else f"      {metric}: {value}")

  print(f"\n{divider}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
  parser = argparse.ArgumentParser(description="Run all BlackBox evaluation configs.")
  parser.add_argument(
      "--output", default=DEFAULT_OUTPUT_BASE,
      help=f"Base output directory (default: {DEFAULT_OUTPUT_BASE})",
  )
  parser.add_argument(
      "--image-tag", default=None, dest="image_tag",
      help="Override the container image tag in every harness config (e.g. from version.txt)",
  )
  args = parser.parse_args()

  session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
  session_output = Path(args.output) / session_ts
  session_output.mkdir(parents=True, exist_ok=True)
  print(f"Session output: {session_output}")

  results: list[tuple[str, dict | Exception]] = []

  for config_path in CONFIGS:
    run_name = config_path.stem
    print(f"\n{'─' * 60}")
    print(f"  Running: {config_path.name}")
    print(f"{'─' * 60}")
    try:
      metrics = _run_config(config_path, session_output, args.image_tag)
      results.append((run_name, metrics))
    except Exception as exc:
      traceback.print_exc()
      results.append((run_name, exc))

  _print_summary(session_output, results)
  csv_path = _save_metrics_csv(session_output, results)
  print(f"Metrics CSV: {csv_path}")
  failed = sum(1 for _, r in results if isinstance(r, Exception))
  return failed


if __name__ == "__main__":
  sys.exit(main())
