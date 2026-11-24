<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Extending MCP

This Python 3.11 module runs inside Manager. Follow the repository
[instructions](../../../.github/copilot-instructions.md) and
[Manager guide](../../Agents.md). Keep protocol handling in thin-mcp;
SceneScape owns authentication, permissions, and configuration queries.

## Add a tool

1. Define validated arguments and explicit public result fields in `schemas.py`.
   Derive inputs from `Arguments`; reuse UUID and pagination validation.
2. Add a bounded ORM read in `queries.py`, with stable ordering and valid
   continuation pages. Exclude credentials, stream URLs, and raw model dumps.
3. Follow `tools/scenes.py`: register a typed adapter with argument/result models
   and `READ_ANNOTATIONS`. Import new domain modules in
   `tools/__init__.py`; the shared registry lives in `tools_registry.py`.
4. Add positive and negative cases in `manager/tests/mcp_server/`, including
   permissions, invalid input, missing objects, field selection, and boundaries.
5. Update the [MCP guide](../../../docs/user-guide/mcp.md). Run the
   [focused tests](../../tests/mcp_server/README.md),
   `make complexity-check SERVICE=manager`, `make indent-check`, and
   `make prettier-check`. Follow repository Python lint guidance.

`api.py` wires DRF hooks from `transport.py`; `core.py` validates the MCP request
with Pydantic and delegates dispatch to thin-mcp.
DRF token authentication and `IsAuthenticated` enforce access before dispatch;
the core and tool registry are internal and assume an authenticated caller.
Any additional transport must enforce authentication before invoking them.
Annotations describe tools, not access permissions. Current tools read
persisted configuration. Writes and live tracking require a separate design.
For transport or deployment changes, rebuild Manager and verify through HTTPS
with a real MCP client as described in the MCP guide.
