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
  - the only supported dataset is Metric Test Dataset

## Quick Links

- Architecture & flow: [docs/design/tracker-evaluation-pipeline.md](../../../docs/design/tracker-evaluation-pipeline.md)
- Main tracker evaluation README (canonical formats, usage, CLI): [README.md](README.md)
- ADR context: [docs/adr/0009-tracking-evaluation.md](../../../docs/adr/0009-tracking-evaluation.md)
- Example configuration: [pipeline_configs/metric_test_evaluation.yaml](pipeline_configs/metric_test_evaluation.yaml)

## Folders structure

- `.venv/` – local virtual environment for running pytest and CLI commands (never commit contents).
- `base/` – shared abstractions wiring datasets, harnesses, and evaluators; reference here before extending component folders.
- `datasets/` – dataset component group; hosts concrete dataset adapters
  - `datasets/tests/` - component-specific unit tests
- `harnesses/` – tracker harness component group; hosts concrete harness adapters with service-specific runners
  - `harnesses/tests/` - component-specific unit tests
- `evaluators/` – evaluator component group; hosts concrete metrics evaluation adapters (e.g., TrackEval wrapper)
  - `evaluators/tests/` - component-specific unit tests
- `pipeline_configs/` – sample YAML pipelines used by `pipeline_engine.py` for smoke and regression tests.
- `tests/` – pytest suites covering pipeline engine plus per-component integration tests.
- `utils/` – reusable helpers (format converters, stream loaders) shared across component groups.

## Datasets

- **MetricTestDataset**: `datasets/metric_test_dataset.py`
  - dataset location in the repository: `../../../tests/system/metric/dataset/`
    It contains:
    - ground-truth file
    - scene configuration in non-canonical format (however accepted by SceneControllerHarness implementation)
    - JSONL files with camera detections for 1, 10 and 30 FPS in canonical format
    - input camera videos (currently unused)

Check `datasets/README.md` for more details

## Harnesses

- **SceneControllerHarness**: `harnesses/scene_controller_harness/scene_controller_harness.py`
  - The wrapper for scene controller that runs Python script `run_tracker.py` in the scene-controller container.
  - Dependent on internal implementation: loads configuration file and calls API of SceneScape classes from scene_common and controller modules.
  - Uses separate frame ingestion logic depending on enabling time-chunking in the configuration.

Check `harnesses/README.md` for more details

## Evaluators

- **TrackEvalEvaluator**: `evaluators/trackeval_evaluator.py`
  Wraps TrackEval library, provides tracker output format conversion and delivers state of the art tracking metrics.

Check `evaluators/README.md` for more details

## Code Entry Points

- **Pipeline orchestration**: [pipeline_engine.py](pipeline_engine.py) (methods `load_configuration()`, `run()`, `evaluate()`, CLI via `python -m pipeline_engine <config>`).
- **Component base classes** (implement to extend pipeline):
  - Dataset: [base/tracking_dataset.py](base/tracking_dataset.py)
  - Harness: [base/tracker_harness.py](base/tracker_harness.py)
  - Evaluator: [base/tracker_evaluator.py](base/tracker_evaluator.py)
- **TrackEval adapter & helpers**: [evaluators/trackeval_evaluator.py](evaluators/trackeval_evaluator.py), [utils/format_converters/](./utils/format_converters.py).

## Guidelines for Adding New Component or Updating Existing One

1. **Understand requirements**
   - Review the design doc and main README sections relevant to datasets, harnesses, or evaluators you plan to modify.
   - Confirm whether changes affect canonical formats; if yes, update main README and converters accordingly.
2. **Implement / modify components**
   - Add new classes under `<component_group>/` and register them via YAML `class` paths.
   - Keep constructors side-effect free; configuration happens through explicit setters invoked by PipelineEngine.
   - If tools/tracker/evaluation/utils do not include utilites for reading / writing / converting common data formats (json, jsonl, csv), do not implement custom logic in the component. Instead loop in human and suggest extending the utilities with a new function
   - Update `requirements.txt` if new dependencies are added
3. **Add / update unit tests**
   - Add or update unit tests specific for this component that cover added / modified code
   - Update integration / pipeline engine tests if component interfaces or configuration is affected
4. **Update configuration & docs**
   - Provide a sample entry in `pipeline_configs/*.yaml` (existing or a new file) demonstrating new options.
   - Record limitations or new behaviors in README (“Phase 1 Limitations” or relevant section).
5. **Run tests**
   - Run unit tests covering the changed component(s)
   - Run integration tests
   - Run full pipeline test with `pipeline_engine.py`

## Tests

### Structure

- `datasets/tests/` - component-specific unit tests
- `harnesses/tests/` - component-specific unit tests
- `evaluators/tests/` - component-specific unit tests
- `tests/` – pytest suites covering format converters, pipeline engine plus per-component integration tests.

### Running tests

- Use .venv for running: `cd tools/tracker/evaluation && source .venv/bin/activate`, loop in human if venv is not found
- Unit tests: `pytest . -v -m "not integration"`
- Integration tests: `pytest . -v -m "integration"`
- Unit & integration: `pytest tests/ -q --tb=short`.
- PipelineEngine test: `pytest tests/test_pipeline_engine.py -v`.
- Full pipeline test via CLI `python pipeline_engine.py pipeline_configs/metric_test_evaluation.yaml` to ensure dataset → harness → evaluator flow succeeds.

## I/O, Data Formats and Conversions

- Reading and writing to files should use primitives from `tools/tracker/evaluation/utils/format_converters.py` optimized for speed and high data volume.
- Filesystem I/O should use streaming API where possible to support large files and optimize for memory usage

## Key Guidelines

- Favor declarative configuration; add new knobs to YAML and plumb them through component `set_*` or `configure_*` methods.
- Ensure dataset iterators and harness processors stream data when possible; avoid loading entire sequences into memory unless documented.
- Canonical format changes require synchronized updates to converters, README, and any datasets/evaluators using them.
