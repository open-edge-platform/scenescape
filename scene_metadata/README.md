<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Metadata Service

Investigator-first event log (TimescaleDB) and SQL graph projection for
Scenescape, with an MCP stdio server on top.

Plan, including recorded results:
[`.github/plans/scene-metadata-investigator-mcp-timescale.md`](../.github/plans/scene-metadata-investigator-mcp-timescale.md)

This file is the replication procedure. Run it from the repository root on a
machine with Docker, Python 3.11 or newer (verified on 3.12), and internet
access. A command that exits 0 passed. Do not commit the model weights or the
dataset.

## 1. Start Timescale

The test compose file starts Timescale and Mosquitto and does not publish the
database port. For host Python, publish port 5432:

```bash
docker run -d --name scene-metadata-db \
  -e POSTGRES_USER=scenescape \
  -e POSTGRES_PASSWORD=scenescape \
  -e POSTGRES_DB=scene_metadata \
  -p 5432:5432 \
  timescale/timescaledb:latest-pg16
until docker exec scene-metadata-db pg_isready -U scenescape -d scene_metadata; do
  sleep 2
done
```

The first connection applies `scene_metadata/sql/001_init.sql`. If port 5432 is
taken, change the host port and the URL below together.

## 2. Install Python packages

```bash
python3 -m pip install -r scene_metadata/requirements-runtime.txt
python3 -m pip install 'openvino==2025.3.0' numpy pytest httpx
```

`openvino` and `numpy` are only for the person-attribute check. They are not
runtime requirements of the service. `httpx` is what the FastAPI test client
uses. Pin `mcp` below 2; `requirements-runtime.txt` already does
(`mcp>=1.12,<2`).

## 3. Environment

```bash
export PYTHONPATH=scene_common/src:scene_metadata/src
export SCENE_METADATA_DATABASE_URL=postgresql://scenescape:scenescape@127.0.0.1:5432/scene_metadata
```

`tests/conftest.py` inserts those two source trees for pytest. The export
still matters for `python3 -m scene_metadata...`. Repo root on `sys.path`
would otherwise shadow `scene_common`.

## 4. Person-attribute accuracy

This check does not use the SmartSpaces dataset. Lab_000 tracks have no
appearance attributes. It downloads the Open Model Zoo 2023.0 FP32 IR (about
87 MB), scores two fixed 160×80 BGR frames on CPU, stores that metadata, and
calls the MCP tools.

```bash
python3 -m scene_metadata.person_attribute_check
```

Pass:

- Exit code 0.
- The last line is `MCP returned the labels and confidences produced by the model.`
- For each identity, the `model` line and the `attribute_observed`,
  `track_started`, and `graph` lines carry the same label, confidence, and
  `model_name`. JSONB may print the keys in a different order.
- `is_male=false` lists only `person-green`, `is_male=true` lists only
  `person-red`, and `has_longsleeves=false` lists nobody.

A head is `true` only when its score is greater than 0.5. `confidence` is the
raw score. `model_name` is `person-attributes-recognition-crossroad-0238`.
Heads, in model order: `is_male`, `has_bag`, `has_hat`, `has_longsleeves`,
`has_longpants`, `has_longhair`, `has_coat_jacket`.

The IR is cached in `scene_metadata/.cache/` (gitignored) or in
`PERSON_ATTR_MODEL_DIR`. The downloader rejects the stub XML that later OMZ
releases publish (XML under 200 KB or weights under 80 MB).

Recorded on 2026-10-26 at 1:13 AM America/Phoenix, OpenVINO 2025.3.0, CPU.
The check exited 0.

| Head              | person-green         | person-red         |
| ----------------- | -------------------- | ------------------ |
| `is_male`         | false, 0.25091282    | true, 0.91730267   |
| `has_bag`         | true, 0.51775378     | false, 0.21933748  |
| `has_hat`         | false, 2.8409744e-05 | true, 0.81346083   |
| `has_longsleeves` | true, 0.77797538     | true, 0.52968919   |
| `has_longpants`   | true, 0.88323599     | true, 0.8879841    |
| `has_longhair`    | true, 0.7849791      | false, 0.038466193 |
| `has_coat_jacket` | true, 0.70212173     | false, 0.38306418  |

If a newer OpenVINO changes a score, keep the local model output as the
expected value. The check fails when MCP differs from that output. Do not edit
the stored payload or the assertion to force a match.

Then run the pytest suite. It skips the database cases without
`SCENE_METADATA_DATABASE_URL`, and it skips the model round-trip until the IR
from the command above is on disk.

```bash
python3 -m pytest -q \
  tests/sscape_tests/scene_metadata/test_person_attribute_accuracy.py \
  tests/sscape_tests/scene_metadata/test_attribute_query.py
```

Recorded the same morning: 12 passed in 0.68 seconds. The generic filter
matched `scarf_color=crimson`, a name that does not appear in the query
server, and rejected an empty attribute name with HTTP 422. Query modules
(`attributes.py`, `store.py`, `query_app.py`, `mcp_server.py`,
`projection.py`) do not name the model heads.

`query_events` takes an `attributes` map of metadata name to label. A match is
a classificationPolicy object whose `label` equals the requested value, or a
scalar stored under that key.

```json
{ "attributes": { "is_male": "true", "scarf_color": "crimson" } }
```

## 5. Lab_000 scene, region, tripwire, and ReID

Optional. Needs the same Timescale URL. The files are not in git.
[nvidia/PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces)
is CC-BY-4.0. Download annotations only. Videos are not required.

```bash
DEST=tools/reid_evaluation/output/physicalai-lab-data
BASE=https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/resolve/main/MTMC_Tracking_2025/val/Lab_000
mkdir -p "$DEST"
for name in calibration.json ground_truth.json map.png; do
  curl -L --fail "$BASE/$name?download=true" -o "$DEST/$name"
done
```

`tools/reid_evaluation/.gitignore` ignores `output/`. The tests read that
directory, or `PHYSICALAI_LAB_DIR` when it is set.

```bash
python3 -m pytest -q \
  tests/sscape_tests/scene_metadata/test_physicalai_investigator.py \
  tests/sscape_tests/scene_metadata/test_physicalai_reid_queries.py
```

Pass: 2 passed. Each test recomputes counts from `ground_truth.json` and
compares them with the query API. The loader does not write appearance
metadata.

Recorded on 2026-10-26 at 1:16 AM America/Phoenix: 2 passed in 1.37 seconds.
9000 frames, 3 people, cameras `Camera_0000` through `Camera_0009`. Every
track's anchor is `Camera_0000`. Each person has 10 `reid_link` rows with
score 1.0. That id is the dataset object id, not an embedding model. North is
`y > 0` (`lab-north`). The tripwire is `x = -2.5` (`x-minus-2-5`). Cameras
"before" the north entry are `reid_link` rows whose frame is strictly earlier
than the first `region_enter`.

| Identity | North entries | Tripwire crossings | Cameras linked before first north entry | First crossing                   |
| -------- | ------------- | ------------------ | --------------------------------------- | -------------------------------- |
| person-0 | 5             | 3                  | 0 (already inside at frame 0)           | frame 2275, 7 visible, 10 linked |
| person-1 | 1             | 2                  | 10 (entry at frame 202)                 | frame 3387, 5 visible, 10 linked |
| person-2 | 1             | 3                  | 9 (entry at frame 925)                  | frame 1054, 8 visible, 10 linked |

An earlier combined pytest the same morning (attribute suites plus these two
tests) was 14 passed in 1.92 seconds.

## 6. Run the service

```bash
make scene_metadata
export SCENE_METADATA_MQTT_ENABLED=false
python3 -m scene_metadata.server
```

MCP stdio, against a running API:

```bash
export SCENE_METADATA_API_URL=http://127.0.0.1:8080
python3 -m scene_metadata.mcp_server
```

Investigator tools: `query_events`, `identity_timeline`, `region_activity`,
`tripwire_crossings`, `identity_attributes`. Operator: `get_system_status`.
Personas default to `investigator,operator,integrator`
(`SCENE_METADATA_MCP_PERSONAS`).

Rebuild `intel/scenescape-scene-metadata` after pulling this tree before
expecting an older image to contain the attribute or Lab_000 code. The checks
above use host Python and do not need that image.

Ingest topics:

- `scenescape/data/scene/+/+` — `track_started` / `track_lost`
- `scenescape/event/region/+/+/+` — region analytics, full fidelity
- `scenescape/event/tripwire/+/+/+` — tripwire crossings, full fidelity

With Mosquitto from `tests/compose/compose.scene-metadata.yml`:

1. `SCENE_METADATA_MQTT_ENABLED=true BROKER=127.0.0.1:1883 python3 -m scene_metadata.server`
2. Publish `scenescape/data/scene/{scene}/person`, `scenescape/event/region/{scene}/{region}/count`, and `scenescape/event/tripwire/{scene}/{tripwire}/objects`.
3. `GET /v1/identities/{id}/timeline` returns `track_started`, `region_enter`, and `tripwire_cross`.
