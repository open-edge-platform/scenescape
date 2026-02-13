<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Tracker Evaluation Pipeline – AI Agent Guide

## Mission & Scope
- Provide an offline, scriptable harness for benchmarking tracker implementations against canonical datasets and evaluation toolkits.
- Coordinate dataset adapters, tracker harnesses, and evaluator plugins through a single Pipeline Engine defined in [pipeline_engine.py](pipeline_engine.py).

## Constraints
- Phase 1 constraints:
  - configuration may list multiple evaluators, but only the first entry is executed. Fail fast if more than one evaluator is configured.
  - only batch mode is supported (read/process/write all data at once), although class interfaces and I/O utilities may use streaming API underneath

## Quick Links
- Architecture & flow: [docs/design/tracker-evaluation-pipeline.md](../../docs/design/tracker-evaluation-pipeline.md)
- Main tracker evaluation README (canonical formats, usage, CLI): [README.md](README.md)
- ADR context: [docs/adr/0009-tracking-evaluation.md](../../docs/adr/0009-tracking-evaluation.md)
- Example configuration: [examples/metric_test_evaluation.yaml](examples/metric_test_evaluation.yaml)

## Folders structure
- `.venv/` – local virtual environment for running pytest and CLI commands (never commit contents).
- `base/` – shared abstractions wiring datasets, harnesses, and evaluators; reference here before extending component folders.
- `datasets/` – dataset component group; hosts canonical dataset base class implementations plus concrete adapters, with component-specific regression tests living under `datasets/tests/`.
- `harnesses/` – tracker harness component group; contains harness base classes and service-specific runners, with harness-focused suites under `harnesses/tests/`.
- `evaluators/` – evaluator component group; includes evaluator base classes and metric adapters (e.g., TrackEval) and keeps evaluator regression tests in `evaluators/tests/`.
- `pipeline_configs/` – sample YAML pipelines used by `pipeline_engine.py` for smoke and regression tests.
- `tests/` – pytest suites covering pipeline engine plus per-component integration tests.
- `utils/` – reusable helpers (format converters, stream loaders) shared across component groups.

## Code Entry Points
- **Pipeline orchestration**: [pipeline_engine.py](pipeline_engine.py) (methods `load_configuration()`, `run()`, `evaluate()`, CLI via `python -m pipeline_engine <config>`).
- **Component base classes** (implement to extend pipeline):
  - Dataset: [src/base/tracking_dataset.py](src/base/tracking_dataset.py)
  - Harness: [src/base/tracker_harness.py](src/base/tracker_harness.py)
  - Evaluator: [src/base/tracker_evaluator.py](src/base/tracker_evaluator.py)
- **TrackEval adapter & helpers**: [src/evaluators/trackeval_evaluator.py](src/evaluators/trackeval_evaluator.py), [src/utils/format_converters/](src/utils/format_converters/).

## Guidelines for Adding New Component or Updating Existing One
1. **Understand requirements**
   - Review the design doc and main README sections relevant to datasets, harnesses, or evaluators you plan to modify.
   - Confirm whether changes affect canonical formats; if yes, update main README and converters accordingly.
2. **Implement / modify components**
   - Add new classes under `<component_group>/` and register them via YAML `class` paths.
   - Keep constructors side-effect free; configuration happens through explicit setters invoked by PipelineEngine.
   - If tools/tracker/evaluation/utils do not include utilites for reading / writing / converting common data formats (json, jsonl, csv), do not implement custom logic in the component. Instead loop in human and suggest extending the utilities with a new function
3. **Update configuration & docs**
   - Provide a sample entry in `pipeline_configs/*.yaml` (existing or a new file) demonstrating new options.
   - Record limitations or new behaviors in README (“Phase 1 Limitations” or relevant section).
4. **Run tests**
   - Run unit tests covering the changed component(s)
   - Run integration tests
   - Run full pipeline test with `pipeline_engine.py`

## Running Tests

- Use .venv for running: `cd tools/tracker/evaluation && source .venv/bin/activate`, loop in human if venv is not found
- Unit & integration:  `pytest tests/ -q --tb=short`.
- PipelineEngine test: `pytest tests/test_pipeline_engine.py -v`.
- Full pipeline test via CLI `python pipeline_engine.py pipeline_configs/metric_test_evaluation.yaml` to ensure dataset → harness → evaluator flow succeeds.

## I/O, Data Formats and Conversions

- Reading and writing to files should use primitives from `tools/tracker/evaluation/utils/format_converters.py` optimized for speed and high data volume.
- Filesystem I/O should use streaming API where possible to support large files and optimize for memory usage

## Key Guidelines
- Favor declarative configuration; add new knobs to YAML and plumb them through component `set_*` or `configure_*` methods.
- Ensure dataset iterators and harness processors stream data when possible; avoid loading entire sequences into memory unless documented.
- Canonical format changes require synchronized updates to converters, README, and any datasets/evaluators using them.
