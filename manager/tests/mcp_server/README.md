<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# MCP unit tests

These tests use real Django/DRF request handling and thin-mcp dispatch, with
token lookups and ORM queries mocked. No database, native geometry, or Docker
is required. `conftest.py` owns import-path setup and isolated Django settings;
run this suite in its own Python process.

From the repository root:

```bash
python3.11 -m venv /tmp/scenescape-mcp-tests
/tmp/scenescape-mcp-tests/bin/python -m pip install -r manager/tests/mcp_server/requirements.txt
/tmp/scenescape-mcp-tests/bin/python -m pytest manager/tests/mcp_server -q
```

The reusable `tests-mcp.yml` workflow runs this directory on Python 3.11 from
both pre-merge CI and All Tests, and uploads a JUnit report. Keep runtime pins
in `requirements.txt` aligned with Manager. Tests cover transport/authentication,
tool contracts, scene field selection, stable ordering, and pagination boundaries.
