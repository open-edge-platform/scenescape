<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Scene Metadata (Investigator-First) — Timescale Event Log, SQL Graph Projection, MCP

## Goal

Deliver a **Scene Metadata** service that gives investigator agents a durable,
queryable history of tracking and **spatial analytics** (regions and tripwires),
with **operator** and **integrator** personas supported on the same read path.
Storage is **TimescaleDB** (PostgreSQL extension). **Graph traversals** use
relational edge tables and SQL—no property-graph database.

This plan implements **Option A** primary ingest (`scenescape/data/scene/{scene_id}/{category}`)
for track lifecycle milestones, with the explicit clarification that **investigator
MVP requires full-fidelity analytics event ingest** on
`scenescape/event/region/...` and `scenescape/event/tripwire/...` in the same
milestone—not a later phase.

Related: [ADR 13 Phase 1–2](../../docs/adr/0013-controller-breakdown-microservices.md)
(Scene State Persistence + Scene Graph foundation),
[work-with-spatial-analytics-data.md](../../docs/user-guide/how-to-guides/work-with-spatial-analytics-data.md).

---

## Non-goals (initial milestones)

- Replacing Manager PostgreSQL or ReID vector stores (VDMS/Qdrant).
- Logging every high-rate `track_updated` geometry frame (milestones only on scene stream).
- MCP write tools (POI enroll, config changes).
- Stream Manager / video clip correlation.
- Treating Lab_000 geometry as person appearance attributes. That dataset has
  no clothing or gender labels.
- Checking the person-attribute IR or the PhysicalAI files into git.

---

## Architecture

```text
MQTT (broker)
  ├─ scenescape/data/scene/{scene_id}/{category}     → track lifecycle normalizer
  └─ scenescape/event/{region|tripwire}/...          → analytics normalizer (full fidelity)
           ↓
    scene-metadata ingest
           ↓
  TimescaleDB hypertable `scenescape_events`
           ↓
  SQL graph projection → `scenescape_graph_edges`
           ↓
  Query HTTP API (/v1/...)
           ↓
  MCP server (stdio) — investigator tools first
```

**Deployment name:** `scene-metadata` (Python service, `scene_metadata` package).

---

## Event envelope (canonical row)

| Field | Purpose |
| ----- | ------- |
| `event_id` | UUID primary key |
| `occurred_at` | Source timestamp (RFC 3339) |
| `ingested_at` | Ingest time |
| `deployment_id` | Hard partition (default `default`) |
| `event_type` | See table below |
| `scene_id`, `region_id`, `tripwire_id` | Spatial context |
| `track_id`, `identity_id` | `id` vs global `gid` when present |
| `source_topic`, `source_message_id` | Idempotent ingest |
| `payload` | JSONB remainder |

### Event types (investigator MVP)

| `event_type` | Source |
| ------------ | ------ |
| `track_started`, `track_lost` | Derived from `data/scene` snapshots |
| `region_enter`, `region_exit`, `region_count` | `event/region/.../count` (entered/exited arrays) |
| `region_objects` | `event/region/.../objects` |
| `tripwire_cross` | `event/tripwire/.../objects` |
| `attribute_observed` | Written by the person-attribute check (not by MQTT ingest) |

MQTT ingest does not invent attribute names. A classifier's
`classificationPolicy` object is queryable from whatever event payload stored
it. `HAS_ATTRIBUTE` edges are projected only from `attribute_observed`.

The Lab_000 loader also writes `config_scene`, `config_camera`,
`camera_visible`, `reid_link`, and `reid_at_crossing`. Those rows are the
dataset scene, not the analytics MQTT contract. ReID there is the dataset
global object id (`score` 1.0, `method` `ground_truth_object_id`), not an
embedding from VDMS or Qdrant.

Future: `identity_assigned`, `reid_match` (reid-service / decision topic).

---

## Timescale schema

- Hypertable: `scenescape_events` partitioned on `occurred_at`.
- Indexes: `(deployment_id, scene_id, occurred_at)`, `(identity_id, occurred_at)`,
  `(region_id, occurred_at)`, `(tripwire_id, occurred_at)`, `(event_type, occurred_at)`.
- Primary key `(occurred_at, event_id)`. Timescale requires the partition column in every unique index.
- Dedup: unique `(occurred_at, deployment_id, source_topic, source_message_id)`.
  `ON CONFLICT DO NOTHING` does not rewrite a payload.
- Reads that share a timestamp order by `occurred_at`, then `source_message_id`.

### Graph projection (SQL, not graph DB)

Table `scenescape_graph_edges`:

- Columns: `relation`, `src_kind`, `src_id`, `dst_kind`, `dst_id`, `scene_id`,
  `valid_from`, `valid_to`, `payload`.
- Relations: `SEEN_IN` (track → scene), `ENTERED` / `EXITED` (identity → region),
  `CROSSED` (identity → tripwire), `HAS_ATTRIBUTE` (identity → `name=label`).
- `HAS_ATTRIBUTE` copies `name`, `label`, `model_name`, and `confidence` from
  each metadata object on `attribute_observed`. The key `reid` and empty labels
  are skipped. A new attribute name needs no schema change.

Projector runs synchronously on ingest for MVP; batch repair job is a follow-up.

---

## Ingest (Option A + analytics)

### Scene track stream (`data/scene`)

- Subscribe: `scenescape/data/scene/+/+`.
- Per `(deployment_id, scene_id, category)` maintain active track id set.
- **Emit:**
  - `track_started` when a track `id` appears.
  - `track_lost` when a track disappears from the snapshot.
- **Do not** emit per-frame `track_updated` in MVP.
- Map `identity_id` from object `id` when it is a global gid; retain local track id separately when both exist.

### Analytics events (investigator-required)

- Subscribe: `scenescape/event/region/+/+/+` and `scenescape/event/tripwire/+/+/+`.
- **No sampling** — every discrete region/tripwire event is stored.
- Parse `entered` / `exited` on count events; tripwire payloads per
  [work-with-spatial-analytics-data.md](../../docs/user-guide/how-to-guides/work-with-spatial-analytics-data.md).

---

## Query API (HTTP, v1)

Investigator-first endpoints:

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/v1/events/query` | Filter by time, scene, types, identity, region, tripwire, and an `attributes` map |
| `GET` | `/v1/identities/{identity_id}/timeline` | Fused track + region + tripwire ordering |
| `GET` | `/v1/regions/{region_id}/activity` | Enter/exit/count in window |
| `GET` | `/v1/tripwires/{tripwire_id}/crossings` | Ordered crossings |
| `GET` | `/v1/health` | Operator: DB + ingest lag |

Graph (SQL):

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/v1/graph/identities/{id}/regions` | Regions linked via `ENTERED`/`EXITED` |
| `GET` | `/v1/graph/identities/{id}/tripwires` | Tripwires linked via `CROSSED` |
| `GET` | `/v1/graph/identities/{id}/attributes` | `HAS_ATTRIBUTE` edges (`name`, `label`, `model_name`, `confidence`) |

`attributes` is a map of metadata name to label. There is no allowlist. A
match is a classificationPolicy object whose `label` equals the requested
string, or a scalar string, number, or boolean under that key. An empty name
is HTTP 422. At most 16 filters.

Auth is not implemented. Bearer auth and mTLS remain follow-up.

---

## MCP layer (stdio)

Server: `python -m scene_metadata.mcp_server`

Investigator tools (ship first):

- `query_events` — optional `attributes` map (any payload metadata name → label; no allowlist)
- `identity_attributes` — `HAS_ATTRIBUTE` edges projected from stored metadata
- `identity_timeline`
- `region_activity`
- `tripwire_crossings`

Operator tools (same backend, narrower defaults):

- `get_system_status` (wraps `/v1/health` + recent ingest stats)

Integrator tools (read-only v1):

- `query_events` with filters on `external_*` when those types exist later

Persona gating: `SCENE_METADATA_MCP_PERSONAS=investigator,operator,integrator` (default all).

---

## As built

- Retail CPU pipeline (`sample_data/demo_scenes/Retail/retail-config.json`)
  runs `gvaclassify` on `person-attributes-recognition-crossroad-0238` after
  person detection (`inference-region=1`) and sets `metadatagenpolicy` to
  `classificationPolicy`. The `personattr` model entry uses the same policy.
  GPU, NPU, and ReID retail pipelines were left detection-only.
- Attribute accuracy is the model's own scores against MCP. Official heads, in
  order: `is_male`, `has_bag`, `has_hat`, `has_longsleeves`, `has_longpants`,
  `has_longhair`, `has_coat_jacket`. Label `true` means the score is greater
  than 0.5. `confidence` is the raw score. `model_name` is the model id.
- The check uses OpenVINO on CPU and the Open Model Zoo 2023.0 FP32 IR. The
  IR already applies mean, scale, and BGR channel order. Input is a 160×80
  BGR frame in 0..255. Later OMZ releases publish a stub XML; the downloader
  keeps the 2023.0 files (XML above 200 KB, weights above 80 MB).
- Lab_000 is a scene, map, camera, region, tripwire, and ReID check. The north
  region is `y > 0` (`lab-north`). The tripwire is `x = -2.5`
  (`x-minus-2-5`). The loader does not write appearance metadata.
- Replication steps for a person or an agent are in
  [scene_metadata/README.md](../../scene_metadata/README.md). Host Python
  against Timescale is the path that matches this tree. Rebuild
  `intel/scenescape-scene-metadata` before expecting a previously built image
  to contain the attribute and Lab_000 code.

---

## Phased delivery

| Phase | Deliverable | Exit criteria |
| ----- | ----------- | ------------- |
| **0** | This plan + service skeleton in repo | Plan merged; package builds |
| **1** | Timescale schema, ingest, store | Unit tests for normalizers; DB integration test |
| **2** | Query API + graph projection | Timeline API returns region + tripwire + track events |
| **3** | MCP investigator tools | Cursor can call `identity_timeline` against a running stack |
| **4** | Compose profile + docs | Demo stack ingests from analytics-enabled scene |

Phases 0–3 and the investigator MQTT path of phase 4 are implemented.
`sample_data/compose/compose.scene-metadata-override.yml` and
`tests/compose/compose.scene-metadata.yml` start Timescale and an anonymous
Mosquitto. The test compose file does not publish the database port; the
replication README publishes `5432` with `docker run`.

Also implemented after phase 4: generic attribute queries, `HAS_ATTRIBUTE`
projection, the Retail CPU person-attribute stage, the Lab_000 scene loader,
and the model-versus-MCP attribute check.

A full SceneScape analytics container is not required for the ingest contract.
The topics match the analytics publisher.

---

## Recorded results

Host: cloud agent, Python 3.12, TimescaleDB (PostgreSQL 16) on `127.0.0.1:5433`,
OpenVINO 2025.3.0 CPU. Times below are America/Phoenix (UTC−7).

### MQTT ingest (2026-10-26)

Published `scenescape/data/scene/...`, `scenescape/event/region/.../count`, and
`scenescape/event/tripwire/.../objects`. `GET /v1/identities/{id}/timeline`
returned `track_started`, `region_enter`, and `tripwire_cross`. The SQL graph
returned `ENTERED` and `CROSSED`. MCP tools `identity_timeline`,
`region_activity`, `tripwire_crossings`, and `get_system_status` read that API.

### Person attributes (2026-10-26, 1:13 AM)

`python3 -m scene_metadata.person_attribute_check` exited 0. It inserted 4
events and called MCP `query_events` and `identity_attributes`. For each
frame, the model line matched `attribute_observed`, `track_started`, and the
`HAS_ATTRIBUTE` graph on label, `model_name`, and confidence. JSONB reordered
keys. `model_name` was `person-attributes-recognition-crossroad-0238`.

| Head | person-green | person-red |
| ---- | ------------ | ---------- |
| `is_male` | false, 0.25091282 | true, 0.91730267 |
| `has_bag` | true, 0.51775378 | false, 0.21933748 |
| `has_hat` | false, 2.8409744e-05 | true, 0.81346083 |
| `has_longsleeves` | true, 0.77797538 | true, 0.52968919 |
| `has_longpants` | true, 0.88323599 | true, 0.8879841 |
| `has_longhair` | true, 0.7849791 | false, 0.038466193 |
| `has_coat_jacket` | true, 0.70212173 | false, 0.38306418 |

`is_male=false` returned person-green. `is_male=true` returned person-red.
`has_longsleeves=false` returned nobody. `is_male=false` together with
`has_bag=true` returned person-green.

Pytest, same morning: 12 passed
(`test_person_attribute_accuracy.py`, `test_attribute_query.py`) in 0.68s.
The generic filter accepted `scarf_color=crimson` and rejected an empty
attribute name with HTTP 422. An earlier combined run the same morning,
including the two Lab_000 tests, was 14 passed in 1.92s.

A later OpenVINO build may change the last digits. The check passes when MCP
returns the scores that local run produced. The table is the 2025.3.0 record.

### Lab_000 scene, region, tripwire, and ReID (2026-10-26, 1:16 AM)

`test_physicalai_investigator.py` and `test_physicalai_reid_queries.py`:
2 passed in 1.37s. Expectations are recomputed from the downloaded
`ground_truth.json`, then compared with the query API. Dataset:
`nvidia/PhysicalAI-SmartSpaces`, `MTMC_Tracking_2025/val/Lab_000`, 9000 frames,
3 people, 10 cameras (`Camera_0000` through `Camera_0009`). Anchor camera on
every track is `Camera_0000`. Each person has 10 `reid_link` rows at score 1.0.

| Identity | North entries | Tripwire crossings | Cameras linked before first north entry | First crossing |
| -------- | ------------- | ------------------ | --------------------------------------- | -------------- |
| person-0 | 5 | 3 | 0 (already inside at frame 0) | frame 2275, 7 cameras visible, 10 linked |
| person-1 | 1 | 2 | 10 (entry at frame 202) | frame 3387, 5 cameras visible, 10 linked |
| person-2 | 1 | 3 | 9 (entry at frame 925) | frame 1054, 8 cameras visible, 10 linked |

North is `y > 0`. The tripwire is `x = -2.5`. "Before" means a `reid_link`
whose frame is strictly less than the first `region_enter`.

---

## Testing

- **Unit:** topic parsers, normalizers, dedup keys, timeline merge (`tests/sscape_tests/scene_metadata/`).
- **Integration:** Timescale; ingest sample payloads; query timeline. Compose file: `tests/compose/compose.scene-metadata.yml`.
- **Attribute accuracy:** `python3 -m scene_metadata.person_attribute_check`, then `test_person_attribute_accuracy.py`. Pass means MCP returned the model's labels and confidences.
- **Lab_000:** `test_physicalai_investigator.py` and `test_physicalai_reid_queries.py` after the README download. Pass means the API matches counts recomputed from `ground_truth.json`.
- **Functional (follow-up):** Full `SCENESCAPE_SPEC` profile with analytics publishing.

---

## Operations

- Env: `SCENE_METADATA_DATABASE_URL`, `SCENE_METADATA_DEPLOYMENT_ID`, MQTT vars aligned with analytics/reid (`BROKER`, auth, certs).
- Retention: configurable `SCENE_METADATA_RETENTION_DAYS` (Timescale drop_chunks policy follow-up).
- Metrics: ingest rate, lag (`ingested_at - occurred_at`), projection errors (OTel follow-up).

---

## Open decisions

1. Shared Postgres vs dedicated Timescale instance for edge demos (MVP: dedicated DB in compose profile).
2. When to add `reid-service` decision topic ingest for `identity_assigned`.
3. Materialized views for hot graph queries vs on-demand SQL only (start on-demand).
4. Bearer auth and mTLS for the query API (not in the current server).
5. Closed: attribute accuracy is model output versus MCP. Lab_000 is not an appearance-attribute oracle.
