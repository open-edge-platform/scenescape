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
"""

import argparse
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

def _run_config(config_path: Path, session_output: Path) -> dict:
  """Load *config_path*, set its output base to *session_output*, run it.

  Returns the metrics dict from PipelineEngine.evaluate().
  """
  with open(config_path) as f:
    cfg = yaml.safe_load(f)

  # Redirect output into the shared session directory.
  # PipelineEngine will append run_name as a subdirectory.
  cfg["pipeline"]["output"]["path"] = str(session_output)

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
      metrics = _run_config(config_path, session_output)
      results.append((run_name, metrics))
    except Exception as exc:
      traceback.print_exc()
      results.append((run_name, exc))

  _print_summary(session_output, results)
  failed = sum(1 for _, r in results if isinstance(r, Exception))
  return failed


if __name__ == "__main__":
  sys.exit(main())
