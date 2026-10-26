<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Re-ID Service

The Re-ID service packages the existing Re-ID database contract and VDMS and
Qdrant adapters as a standalone deployable service. This extraction keeps
adapter behavior unchanged and adds a backend-neutral gRPC boundary.

## Current Scope

The service provides health, `FindMatches`, `FindSchemaMetadata`, manual
`PurgeExpired`, and `IngestStats` wrappers alongside Tracker MQTT ingestion.
The Controller still uses compatible `controller.reid*` imports for its
in-process path. Controller retirement, POI APIs, gallery management, and
trajectory export are follow-on work.

## Baseline gRPC Contract

The authoritative declaration is `reid/proto/reid.proto`, service
`scenescape.reid.ReIDService`. All five RPCs are unary calls with
`google.protobuf.Struct` requests and responses. Method names and existing
response fields remain compatible with the initial service. `Health.ready`
is additive; `IngestStats` is now explicitly declared as well as implemented.

| RPC                  | Request                                                                  | Response                                                                                                                        |
| -------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `Health`             | `{}`                                                                     | `{"status":"ok","ready":true,"connected":true,"backend":"VDMSDatabase","ingest_enabled":false}`                                 |
| `FindMatches`        | `{"object_type":"person","reid_vectors":[[1,0,0]],"set_name":"gallery"}` | `{"matches":[[{"uuid":"gid-1","rvid":"track-1","_distance":0.8}]]}`                                                             |
| `FindSchemaMetadata` | `{"set_name":"gallery"}` or `{}` for the configured set                  | `{"metadata":[true,3,"IP"]}`; absent set: `{"metadata":[false,null,null]}`                                                      |
| `PurgeExpired`       | `{}`                                                                     | `{"result":2}` when the reclaimed count is known; `{"result":null}` when it is unknown                                          |
| `IngestStats`        | `{}`                                                                     | `{"enabled":false}` when disabled; otherwise `{"enabled":true,...snapshot}` with `counters`, `matchers`, and `unique_id_counts` |

The examples use three-element vectors only for brevity. `FindMatches` requires
a rectangular numeric matrix with 1-1024 rows, 1-4096 dimensions, and finite
float32 vectors. Inner-product normalization additionally requires nonzero
vectors; L2 permits zero vectors. If the adapter has configured dimensions, every row
must match them. `object_type` and an optional `set_name` must be nonempty
strings of at most 256 characters without NUL bytes. An omitted or null
`set_name` selects the configured set. Optional `k_neighbors` is an integer
from 1 to 1000; omitting it preserves the adapter default. Optional `constraints`
is an object of the existing confidence-bearing metadata filters, for example
`{"gender":{"label":"female","confidence":0.95}}`. Reserved identity/persist
fields remain ignored by the adapters; constraints cannot override `object_type`,
`set_name`, `k_neighbors`, `reid_vectors`, or internal call/threshold controls.
Unknown top-level request fields are rejected.
These are queries only: no enrollment, schema creation, or general-gallery
write RPC is exposed.

`matches` preserves the adapter's per-vector result lists and similarity metric
semantics. An empty per-vector list means no usable match, not backend failure.
Schema metadata remains an array of existence, dimensions, and metric; unknown
backend metadata values may be null. Manual purge uses the existing TTL reclaim
semantics, not arbitrary deletion. Disabled TTL returns `result: 0`; successful
Qdrant purge returns null because its API does not supply a deleted count.

`Health` performs a read-only availability probe on every call. It does not
require a populated gallery or create a schema. A reachable backend returns
`status: "ok"`, `ready: true`, and `connected: true`; a failed probe returns
`status: "degraded"`, `ready: false`, and `connected: false`, still with an OK
gRPC status. A successful Health RPC establishes process liveness; callers must
inspect `ready` for readiness. `IngestStats` is local process state and remains
available during a backend outage. Its counts are process-local, not durable
gallery statistics.

| gRPC status        | Meaning                                                                                                    |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `OK`               | Valid operation completed, including empty matches, disabled ingest/TTL, absent schema, or degraded Health |
| `INVALID_ARGUMENT` | Missing, unsupported, or malformed request fields                                                          |
| `UNAVAILABLE`      | Matching, schema lookup, or purge failed against the backend; no fabricated empty success                  |
| `INTERNAL`         | Unexpected service failure; private exception details are not returned                                     |
| `UNIMPLEMENTED`    | RPC is not part of the baseline contract, including gallery-write methods                                  |

### Python Client

`reid.client.ReIDClient` accepts a caller-owned channel, defaults to a five-second
deadline for every call, and propagates `grpc.RpcError` unchanged. The caller
owns channel security and closure; the client does not silently open a plaintext
connection. For example, when the endpoint has a TLS terminator:

```python
from pathlib import Path
import grpc
from reid.client import ReIDClient

credentials = grpc.ssl_channel_credentials(Path("/run/secrets/reid-ca.pem").read_bytes())
with grpc.secure_channel("reid.example.com:443", credentials) as channel:
	client = ReIDClient(channel, timeout=5.0)
	readiness = client.health()
	metadata = client.find_schema_metadata()
	statistics = client.ingest_stats()
```

The service's current listener itself remains plaintext on `REID_SERVICE_PORT`;
it has no application-layer authorization. Do not expose it to untrusted callers.
Deployment security must restrict access, including to manual purge; use an
authenticated TLS proxy when remote access is required. Native listener TLS and
authorization are separate work, not a reason to bypass deployment controls.

### Contract Verification

Run the host-only transport tests with the test dependencies installed:

```bash
tests/.venv/bin/python -m pytest tests/sscape_tests/reid/test_api.py
make complexity-check SERVICE=reid
```

The tests send protobuf requests over a real loopback gRPC channel to the server
with real VDMS and Qdrant adapters. Only database clients are mocked; success,
invalid input, backend errors, outage/recovery, proto/client/handler parity, and
absence of general-gallery writes are checked. This is not a live-database or
deployment TLS verification.

## Identity State and Counting

The service publishes identity state and completed decisions on
`scenescape/data/reid/{scene_id}/{category}`. Messages retain `track_id`, `gid`,
`matched`, and `similarity`, and include `reid_state` and `unique_id_count`.
The four states preserve Controller behavior:

- `pending_collection`: gathering features or waiting for a query result.
- `matched`: an accepted match has assigned the gid.
- `query_no_match`: a query completed without an accepted match, including live-gid collisions.
- `reid_disabled`: matching is disabled; tracks retain their local identity.

`matched: false` alone does not indicate a completed no-match decision. Consumers
must inspect `reid_state`. Analytics preserves these states in regulated and
region output, and marks undecided Tracker objects as `pending_collection`.

The cumulative counter is owned by each scene/category matcher and resets when
the service restarts. It increments when a track is first registered without a
usable embedding or while ReID is disabled, and when a query has no accepted
match. A later no-match after an initially missing embedding increments it again,
as in the Controller. A no-match result after a track leaves also increments it.
It is not current occupancy or a count derived from terminal states.

`IngestStats` exposes per-matcher `unique_id_counts` and their aggregate in
`counters.unique_id_count`. Analytics forwards the applicable matcher count as
the existing `unique_detection_count` field in regulated scene messages.

## Configuration

The service uses `REID_DATABASE` (`VDMS` or `QDRANT`), `REID_HOSTNAME`,
`REID_PORT`, `REID_USE_TLS`, the existing Re-ID certificate variables, and
`REID_DESCRIPTOR_TTL_SECS`. `REID_SERVICE_PORT` selects the gRPC port and
defaults to `50051`.

The backend remains the Compose service `reid`; the extracted application is
`reid-service` so existing backend overrides continue to work.

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source

:::
hide_directive-->
