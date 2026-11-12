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

## Authentication and connection

Configure an MCP client with your deployment's HTTPS `/mcp` URL and an
`Authorization: Bearer <token>` header. The credential is an existing Manager
API token obtained through `/api/v1/auth`. The existing `Authorization: Token
<token>` scheme is also accepted. Session cookies are not accepted for MCP.

All active authenticated users have the same configuration read access as the
Manager REST API. This endpoint exposes only read operations; the API token
retains its existing permissions on other Manager endpoints. This initial
integration does not implement OAuth discovery or browser authorization, so
clients must support explicitly configured token headers.

For example, with `SCENESCAPE_API_TOKEN` set in your shell:

```bash
curl --fail-with-body https://web.scenescape.intel.com/mcp \
  --header "Authorization: Bearer ${SCENESCAPE_API_TOKEN}" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"inventory-client","version":"1"}}}'

curl --fail-with-body https://web.scenescape.intel.com/mcp \
  --header "Authorization: Bearer ${SCENESCAPE_API_TOKEN}" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --header 'MCP-Protocol-Version: 2025-11-25' \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

Use a CA trusted by your client (or configure your deployment's CA explicitly).
The endpoint supports MCP revisions `2025-03-26`, `2025-06-18`, `2025-11-25`, and
`2026-07-28`, with header validation delegated to thin-mcp. It returns JSON
responses and HTTP 202 for notifications; it does not maintain sessions or offer
an SSE stream. GET and DELETE return HTTP 405.

## Tools

| Tool           | Arguments                                   | Result                                                         |
| -------------- | ------------------------------------------- | -------------------------------------------------------------- |
| `list_scenes`  | `limit`, `offset`                           | Scene ID, name, map type, scale, tracker configuration         |
| `get_scene`    | Required `scene_id` UUID                    | One scene with the same summary fields                         |
| `list_cameras` | Optional `scene_id` UUID, `limit`, `offset` | Sensor ID, name, scene ID, pose lock                           |
| `list_regions` | Optional `scene_id` UUID, `limit`, `offset` | Region UUID, name, scene ID, height, volumetric flag, ROI type |

Lists default to 25 items, with a hard maximum of 25. Results contain `items`
and `next_offset`; pass a non-null `next_offset` as the next request's `offset`.
Offsets must be between 0 and 100000. Pages have a stable identifier order;
configuration changes between requests may shift offset pagination. Unknown
arguments are rejected. A missing scene returns a tool execution error.

For example, call `list_cameras` with
`{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_cameras","arguments":{"limit":10,"offset":0}}}`.

These tools return persisted configuration. They do not report live occupancy,
tracking state, video, or camera health. Stream URLs, credentials, files, raw
configuration blobs, and user records are excluded from results.

## Transport controls

Requests must contain one JSON-RPC object with `Content-Type: application/json`.
The maximum request size is 64 KiB. Batches are unsupported. Responses use
`Cache-Control: no-store`; unexpected failures return a generic error.

Requests without an Origin header are accepted. Browser origins must match the
request origin or an exact string in the Django setting `MCP_ALLOWED_ORIGINS`
(default: empty list). Configure additional origins only when required.
Django's existing `ALLOWED_HOSTS` validation also applies.

The Django setting `MCP_THROTTLE_RATE` defaults to `120/min` per user. Throttling
uses the configured Django cache and returns HTTP 429 with `Retry-After`. With
the default local-memory cache this limit applies separately to each worker;
use a shared cache for a shared limit.

## Development and verification

The module keeps transport and authentication in `api.py`, protocol dispatch in
`core.py`, bounded ORM projections in `queries.py`, and typed adapters in
`tools/`. `tools_registry.py` owns the registry. Domain imports in
`tools/__init__.py` determine discovery order. Tools check active authentication
before executing queries and declare read-only annotations.

Run the isolated tests without native geometry, a database, or Docker:

```bash
uv run --no-project --python 3.11 \
  --with thin-mcp==0.2.1 --with Django==5.2.17 \
  --with djangorestframework==3.18.2 --with pytest \
  python -m pytest manager/tests/mcp_server -q
```

The tests use real Django/DRF HTTP handling and thin-mcp dispatch, with token
lookups and domain queries mocked. Import-path setup lives in the local
`conftest.py`. To verify the deployed stack after rebuilding Manager, run the
authenticated initialization, discovery, and tool-call examples above against
your deployment.
