<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Running Tests

Prefer the narrowest pytest path that covers changed tests. Broad `make run_*` targets are for suite sweeps. Runtime verification / rebuild rules: `.github/skills/test-verification-gate/SKILL.md`.

```bash
# Setup (from repo root)
make setup-tests

# Make targets
make run_basic_acceptance_tests
make run_standard_tests
make run_functional_tests
make run_ui_tests
make run_unit_tests
make run_metric_tests
make run_performance_tests
make run_stability_tests HOURS=24

# Narrow pytest (tests/.venv activated)
pytest tests/sscape_tests/geometry/test_point.py
pytest tests/functional/test_roi_mqtt.py
pytest tests/ui/test_out_of_box.py
pytest tests/ -m basic_acceptance

# Backends / logs
pytest tests/functional --backend=docker          # default
pytest tests/functional --backend=kubernetes
pytest tests/functional --backend=all
pytest tests/functional --collect-container-logs=failed   # default
pytest tests/functional --collect-container-logs=all
pytest tests/functional --collect-container-logs=none
```
