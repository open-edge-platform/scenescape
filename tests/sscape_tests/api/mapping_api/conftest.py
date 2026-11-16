#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Re-export the mapping test double used by the contract check.

The fixture lives in the mapping unit-test conftest. Importing that module
reuses it instead of copying the mock into this tree. It is not loaded as a
pytest plugin, so its session hooks do not apply here.
"""

import importlib.util

from tests.sscape_tests.api.common import repo_root

_MAPPING_CONFTEST = repo_root(__file__) / "mapping" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location(
  "mapping_tests_conftest_for_contract", _MAPPING_CONFTEST)
if _spec is None or _spec.loader is None:
  raise ImportError(f"cannot load mapping test fixtures from {_MAPPING_CONFTEST}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

mock_model = _module.mock_model
