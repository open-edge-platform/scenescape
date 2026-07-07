# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run all three BlackBox evaluation configs in a single timestamped session.

All results land under a shared session directory:

  <base_output_path>/<YYYYMMDD_HHMMSS>/
    Controller-Immediate/
    Controller-Time-Chunking/
    Tracker-Service/

Usage:
  python run_black_box_evaluation.py
  python run_black_box_evaluation.py --output /custom/output/path
  python run_black_box_evaluation.py --dataset wildtrack

Programmatic use:

  from run_black_box_evaluation import run_all
  results = run_all()  # list of (run_name, metrics|Exception)
"""

import argparse
import sys
import tempfile
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

# Available config sets, keyed by dataset name.  The legacy Unity dataset is the
# default; Wildtrack is an additional set that can be selected manually.
_CONFIG_DIRS = {
  "unity": "black_box_unity",
  "wildtrack": "black_box_wildtrack",
}
DEFAULT_DATASET = "unity"

_CONFIG_FILES = [
  "black_box_controller_immediate.yaml",
  "black_box_controller_tc.yaml",
  "black_box_tracker_service.yaml",
]


def configs_for(dataset: str = DEFAULT_DATASET) -> list[Path]:
  """Return the ordered list of config paths for *dataset*."""
  try:
    config_dir = _CONFIG_DIRS[dataset]
  except KeyError:
    raise ValueError(
      f"Unknown dataset {dataset!r}; choose from {sorted(_CONFIG_DIRS)}"
    ) from None
  return [
    _SCRIPT_DIR / "pipeline_configs" / config_dir / name
    for name in _CONFIG_FILES
  ]

DEFAULT_OUTPUT_BASE = _SCRIPT_DIR / "output" / "black-box-evaluation"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_config(config_path: Path, session_output: Path, image_tag: str | None = None) -> dict:
  """Load *config_path*, set its output base to *session_output*, run it.

  If *image_tag* is given, the tag portion of the harness ``container_image``
  is replaced with that value.  When *None* the tag from the YAML file is used
  unchanged (intended for manual runs where the user edits the YAML directly).

  Returns the metrics dict from PipelineEngine.evaluate().
  """
  with open(config_path) as f:
    cfg = yaml.safe_load(f)

  # Redirect output into the shared session directory.
  # PipelineEngine will append run-ID as a subdirectory.
  cfg["pipeline"]["output"]["path"] = str(session_output)

  # Resolve data_path relative to _SCRIPT_DIR so this function works
  # regardless of the caller's working directory.
  dataset_cfg = cfg.get("dataset", {}).get("config", {})
  raw_path = dataset_cfg.get("data_path", "")
  if raw_path and not Path(raw_path).is_absolute():
    cfg["dataset"]["config"]["data_path"] = str(
      (_SCRIPT_DIR / raw_path).resolve()
    )

  # Resolve tracker_config_path the same way.
  harness_cfg = cfg.get("harness", {}).get("config", {})

  # Override the container image tag when one is supplied.
  if image_tag is not None:
    raw_image = harness_cfg.get("container_image", "")
    if raw_image:
      image_name = raw_image.split(":")[0]
      cfg["harness"]["config"]["container_image"] = f"{image_name}:{image_tag}"

  raw_tracker_cfg = harness_cfg.get("tracker_config_path", "")
  if raw_tracker_cfg and not Path(raw_tracker_cfg).is_absolute():
    cfg["harness"]["config"]["tracker_config_path"] = str(
      (_SCRIPT_DIR / raw_tracker_cfg).resolve()
    )

  # Write the patched config to a temp file so load_configuration() can
  # persist the config copy and run full validation.
  with tempfile.NamedTemporaryFile(
    mode="w", suffix=".yaml", prefix=config_path.stem + "_", delete=False
  ) as tmp:
    yaml.safe_dump(cfg, tmp)
    tmp_path = tmp.name

  try:
    engine = PipelineEngine()
    engine.load_configuration(tmp_path)
    engine.run()
    metrics = engine.evaluate()
    print(f"\nResults saved to: {engine._output_path}")
    return metrics
  finally:
    Path(tmp_path).unlink(missing_ok=True)


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
# Public API
# ---------------------------------------------------------------------------

def run_all(
  image_tag: str | None = None,
  output_dir: Path | None = None,
  dataset: str = DEFAULT_DATASET,
) -> list[tuple[str, dict | Exception]]:
  """Run all black-box evaluation configs and return results.

  Args:
    image_tag:  Override the container image tag in every harness config.
                When *None* the tag already present in each YAML file is used
                (intended for manual runs where the user edits the YAML).
    output_dir: Base directory for session output.  Defaults to
                ``DEFAULT_OUTPUT_BASE``.
    dataset:    Config set to run (``"unity"`` by default, or ``"wildtrack"``).

  Returns:
    List of ``(run_name, metrics_dict)`` pairs.  On failure for a run the
    second element is the raised :class:`Exception`.
  """
  session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
  session_output = Path(output_dir or DEFAULT_OUTPUT_BASE) / session_ts
  session_output.mkdir(parents=True, exist_ok=True)
  print(f"Session output: {session_output}")

  results: list[tuple[str, dict | Exception]] = []
  for config_path in configs_for(dataset):
    run_name = config_path.stem
    print(f"\n{'─' * 60}")
    print(f"  Running: {config_path.name}")
    print(f"{'─' * 60}")
    try:
      metrics = _run_config(config_path, session_output, image_tag)
      results.append((run_name, metrics))
    except Exception as exc:
      traceback.print_exc()
      results.append((run_name, exc))

  _print_summary(session_output, results)
  return results


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
      "--dataset", choices=sorted(_CONFIG_DIRS), default=DEFAULT_DATASET,
      help=f"Config set / dataset to run (default: {DEFAULT_DATASET})",
  )
  args = parser.parse_args()

  results = run_all(output_dir=args.output, dataset=args.dataset)
  failed = sum(1 for _, r in results if isinstance(r, Exception))
  return failed


if __name__ == "__main__":
  sys.exit(main())
