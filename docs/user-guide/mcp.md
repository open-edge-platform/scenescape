<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Remote MCP

Manager provides a stateless JSON Streamable HTTP endpoint at
`https://web.scenescape.intel.com/mcp` (no trailing slash), implemented by the
`mcp_server` module and `thin-mcp==0.2.1`. It runs in the existing Python 3.11
Manager process. Rebuild the Manager image to install the dependency and include
the module; no database migrations or additional service is required.

## Architecture

![REST clients call known endpoints; AI agents discover and call MCP tools through the new mcp_server module inside Manager.](_assets/mcp-architecture.svg)

The blue components are added by this integration. Manager's existing HTTPS
endpoint, API-token authentication, ORM models, and PostgreSQL database are reused.
The tools read configuration directly through the ORM; they do not call the REST
API or access live tracking state.

## Why MCP for agents?

MCP lets agents discover tool descriptions and schemas through `tools/list`,
select a tool for the task, and invoke it through `tools/call`. New tools can
become available without a dedicated client integration for each operation,
which can shorten delivery cycles. See the
[MCP tool model](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

Clients must refresh discovery and may require tool approval; this server does
not push tool-list changes. Discovery reduces client coupling, but existing tool
contracts still need compatibility care for cached schemas and saved workflows.

## Authentication and connection

Configure your MCP client with:

```text
URL: https://<your-manager-host>/mcp
Transport: Streamable HTTP
Authorization: Bearer <Manager API token>
```

Use a token from `/api/v1/auth` and trust your deployment's TLS certificate.
`Authorization: Token <token>` is also accepted. The client must support explicit
headers; session cookies and OAuth/browser sign-in are not supported.

Active authenticated users can use the exposed MCP tools.

## Tools

This initial PR provides just two read-only tools to get started with persisted
scene configuration:

| Tool          | Arguments                  | Result                            |
| ------------- | -------------------------- | --------------------------------- |
| `list_scenes` | Optional `limit`, `offset` | Scene summaries and `next_offset` |
| `get_scene`   | Required `scene_id` UUID   | One scene summary                 |

Example: list up to 10 scenes.

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "list_scenes",
    "arguments": { "limit": 10 }
  }
}
```

Pages default to 25 scenes (maximum 25). Pass `next_offset` to continue; `null`
means the end of results or the offset limit of 500. These tools do not expose
live tracking or video.

## Endpoint controls

The `MCP_*` Django settings below apply specifically to `/mcp`; they do not
change Manager's REST API or file-upload limits. The endpoint reuses Manager's
API tokens, Django cache, and existing host validation.

### Request size limiting

`MCP_MAX_REQUEST_SIZE` defaults to **64 KiB** (`64 * 1024` bytes), independently
of Django's global upload limit. The parser reads at most the limit plus one byte
and rejects oversized bodies with **HTTP 413**.

### Throttling rate

`MCP_THROTTLE_RATE` defaults to **`120/min` per authenticated user**. Exceeding it
returns **HTTP 429** with `Retry-After`. It uses Django's configured cache;
with the default local-memory cache, the limit applies separately to each worker.
Use a shared cache for a shared limit.

### Allowed hosts and origins

- **Hosts:** Manager's existing `ALLOWED_HOSTS` setting validates the destination
  host. There is no separate MCP host allowlist.
- **Origins:** `/mcp` explicitly checks the caller's `Origin` because token-based
  DRF authentication does not apply Django's CSRF origin checks. Requests without
  `Origin` are accepted. Otherwise it must match the request's scheme and host,
  or an exact entry in `MCP_ALLOWED_ORIGINS` (default: empty list).

These are Django settings, not automatically read environment variables.

### Request and response format

Supported MCP revisions: `2025-03-26`, `2025-06-18`, `2025-11-25`, and `2026-07-28`.
The endpoint returns JSON responses and HTTP 202 for notifications, with no
sessions or SSE stream. GET and DELETE return HTTP 405.

Send one JSON-RPC object with `Content-Type: application/json`; batches are
unsupported. Responses use `Cache-Control: no-store`. HTTP failures use DRF-style
`{"detail": "..."}` responses; MCP parsing and protocol errors use JSON-RPC
error envelopes. Unexpected failures return a generic error.

## Development and verification

See the [module extension guide](../../manager/src/mcp_server/AGENTS.md) for the
code structure and steps to add a tool. The
[test guide](../../manager/tests/mcp_server/README.md) describes the isolated
Python 3.11 suite run by pre-merge CI and All Tests.

Run the isolated tests without native geometry, a database, or Docker:

```bash
uv run --no-project --python 3.11 \
  --with-requirements manager/tests/mcp_server/requirements.txt \
  python -m pytest manager/tests/mcp_server -q
```

The isolated suite mocks token lookups and ORM queries. The
[Django integration suite](../../tests/sscape_tests/mcp_server/test_mcp_django.py)
also exercises `/mcp` with real models, migrations, tokens, and a SQLite test
database. For deployment verification, rebuild Manager and exercise initialization,
discovery, and tool calls through your deployment's HTTPS endpoint.
