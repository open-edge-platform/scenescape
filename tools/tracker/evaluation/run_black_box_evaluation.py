# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run BlackBox evaluation configs in a single timestamped session.

All results land under a shared session directory:

  <base_output_path>/<YYYYMMDD_HHMMSS>/
    Controller-Immediate/
    Controller-Time-Chunking/
    Tracker-Service/

With ``--association mahalanobis`` the session instead runs the three
mahalanobis jobs (HPHt + filter base R). ``--association both`` runs
euclidean then mahalanobis.

Usage:
  python run_black_box_evaluation.py
  python run_black_box_evaluation.py --output /custom/output/path
  python run_black_box_evaluation.py --dataset wildtrack
  python run_black_box_evaluation.py --dataset rolling_terrain
  python run_black_box_evaluation.py --observation-processor
  python run_black_box_evaluation.py --no-observation-processor
  python run_black_box_evaluation.py --association mahalanobis
  python run_black_box_evaluation.py --association both

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
# default; the other sets can be selected manually.
_CONFIG_DIRS = {
  "unity": "black_box_unity",
  "wildtrack": "black_box_wildtrack",
  "rolling_terrain": "black_box_rolling_terrain",
}
DEFAULT_DATASET = "unity"
DEFAULT_ASSOCIATION = "euclidean"

# Euclidean baseline (legacy meter gate) and mahalanobis (HPHt + R) companion jobs.
_ASSOCIATION_SUFFIX = {
  "euclidean": "",
  "mahalanobis": "_mahalanobis",
}
_BASE_CONFIG_STEMS = [
  "black_box_controller_immediate",
  "black_box_controller_tc",
  "black_box_tracker_service",
]


def _config_file_names(association: str = DEFAULT_ASSOCIATION) -> list[str]:
  """Return YAML filenames for one association method."""
  try:
    suffix = _ASSOCIATION_SUFFIX[association]
  except KeyError:
    raise ValueError(
      f"Unknown association {association!r}; choose from {sorted(_ASSOCIATION_SUFFIX)}"
    ) from None
  return [f"{stem}{suffix}.yaml" for stem in _BASE_CONFIG_STEMS]


# Backward-compatible alias used by unit tests.
_CONFIG_FILES = _config_file_names(DEFAULT_ASSOCIATION)


def configs_for(
  dataset: str = DEFAULT_DATASET,
  association: str = DEFAULT_ASSOCIATION,
) -> list[Path]:
  """Return the ordered list of config paths for *dataset* and *association*.

  ``association="both"`` returns euclidean configs then mahalanobis configs.
  """
  try:
    config_dir = _CONFIG_DIRS[dataset]
  except KeyError:
    raise ValueError(
      f"Unknown dataset {dataset!r}; choose from {sorted(_CONFIG_DIRS)}"
    ) from None

  if association == "both":
    names = _config_file_names("euclidean") + _config_file_names("mahalanobis")
  else:
    names = _config_file_names(association)

  return [
    _SCRIPT_DIR / "pipeline_configs" / config_dir / name
    for name in names
  ]

DEFAULT_OUTPUT_BASE = _SCRIPT_DIR / "output" / "black-box-evaluation"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_observation_processor(cfg: dict, enabled: bool) -> None:
  """Override ``harness.config.observation_processor.enabled`` in a loaded config.

  Raises:
    ValueError: If the config has no ``observation_processor`` block.
  """
  harness_cfg = cfg.get("harness", {}).get("config", {})
  if not isinstance(harness_cfg.get("observation_processor"), dict):
    raise ValueError("config has no harness.config.observation_processor block")
  harness_cfg["observation_processor"]["enabled"] = enabled


def _run_config(
  config_path: Path,
  session_output: Path,
  image_tag: str | None = None,
  observation_processor: bool | None = None,
) -> dict:
  """Load *config_path*, set its output base to *session_output*, run it.

  If *image_tag* is given, the tag portion of the harness ``container_image``
  is replaced with that value.  When *None* the tag from the YAML file is used
  unchanged (intended for manual runs where the user edits the YAML directly).
  If *observation_processor* is not None, it overrides the experimental
  observation processor setting of the config (see ``_set_observation_processor``).
  The effective config is stored in the run's ``config/`` folder.

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

  if observation_processor is not None:
    _set_observation_processor(cfg, observation_processor)

  # Write the effective config under its original name so load_configuration()
  # can persist the config copy and run full validation.
  with tempfile.TemporaryDirectory() as tmp_dir:
    tmp_path = Path(tmp_dir) / config_path.name
    tmp_path.write_text(yaml.safe_dump(cfg))
    engine = PipelineEngine()
    engine.load_configuration(str(tmp_path))
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
# Public API
# ---------------------------------------------------------------------------

def run_all(
  image_tag: str | None = None,
  output_dir: Path | None = None,
  dataset: str = DEFAULT_DATASET,
  observation_processor: bool | None = None,
  association: str = DEFAULT_ASSOCIATION,
) -> list[tuple[str, dict | Exception]]:
  """Run black-box evaluation configs and return results.

  Args:
    image_tag:  Override the container image tag in every harness config.
                When *None* the tag already present in each YAML file is used
                (intended for manual runs where the user edits the YAML).
    output_dir: Base directory for session output.  Defaults to
                ``DEFAULT_OUTPUT_BASE``.
    dataset:    Config set to run (``"unity"`` by default, ``"wildtrack"`` or
                ``"rolling_terrain"``).
    observation_processor: ``True``/``False`` overrides the experimental
                observation processor setting of every config; ``None`` keeps
                each YAML's own setting.
    association:
      ``"euclidean"`` (default baseline), ``"mahalanobis"`` (HPHt + R gate),
      or ``"both"``.

  Returns:
    List of ``(run_name, metrics_dict)`` pairs.  On failure for a run the
    second element is the raised :class:`Exception`.
  """
  session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
  session_output = Path(output_dir or DEFAULT_OUTPUT_BASE) / session_ts
  session_output.mkdir(parents=True, exist_ok=True)
  print(f"Session output: {session_output}")

  results: list[tuple[str, dict | Exception]] = []
  for config_path in configs_for(dataset, association=association):
    run_name = config_path.stem
    print(f"\n{'─' * 60}")
    print(f"  Running: {config_path.name}")
    print(f"{'─' * 60}")
    try:
      metrics = _run_config(config_path, session_output, image_tag, observation_processor)
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
  parser.add_argument(
      "--observation-processor", action=argparse.BooleanOptionalAction, default=None,
      help="Override the experimental observation processor setting of every "
           "config (default: keep each config's own setting)",
  )
  parser.add_argument(
      "--association",
      choices=["euclidean", "mahalanobis", "both"],
      default=DEFAULT_ASSOCIATION,
      help=(
        "Association configs to run: euclidean baseline (default), "
        "mahalanobis (HPHt + R), or both"
      ),
  )
  args = parser.parse_args()

  results = run_all(
    output_dir=args.output,
    dataset=args.dataset,
    observation_processor=args.observation_processor,
    association=args.association,
  )
  failed = sum(1 for _, r in results if isinstance(r, Exception))
  return failed


if __name__ == "__main__":
  sys.exit(main())
