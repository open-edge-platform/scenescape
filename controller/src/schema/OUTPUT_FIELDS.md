<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Controller Output Message Fields

Reference table derived from sample output files in this directory.

Symbols: ✓ present, — absent.

---

## Top-Level Message Fields

| Field                    | Type                                      | `data/scene` | `regulated/scene` | Region Event | Tripwire Event |
| ------------------------ | ----------------------------------------- | :----------: | :---------------: | :----------: | :------------: |
| `timestamp`              | string (ISO 8601)                         |      ✓       |         ✓         |      ✓       |       ✓        |
| `id`                     | string (UUID)                             |      ✓       |         ✓         |      —       |       —        |
| `name`                   | string                                    |      ✓       |         ✓         |      —       |       —        |
| `rate`                   | number                                    |      ✓       |         —         |      —       |       —        |
| `scene_rate`             | number                                    |      —       |         ✓         |      —       |       —        |
| `rate`                   | object `{camera_id: number}`              |      —       |         ✓         |      —       |       —        |
| `unique_detection_count` | integer                                   |      ✓       |         —         |      —       |       —        |
| `objects`                | array of track objects                    |      ✓       |         ✓         |      ✓       |       ✓        |
| `scene_id`               | string (UUID)                             |      —       |         —         |      ✓       |       ✓        |
| `scene_name`             | string                                    |      —       |         —         |      ✓       |       ✓        |
| `region_id`              | string (UUID)                             |      —       |         —         |      ✓       |       —        |
| `region_name`            | string                                    |      —       |         —         |      ✓       |       —        |
| `tripwire_id`            | string (UUID)                             |      —       |         —         |      —       |       ✓        |
| `tripwire_name`          | string                                    |      —       |         —         |      —       |       ✓        |
| `counts`                 | object `{category: integer}`              |      —       |         —         |      ✓       |       ✓        |
| `entered`                | array of `{object: track, dwell: number}` |      —       |         —         |      ✓       |       ✓        |
| `exited`                 | array of `{object: track, dwell: number}` |      —       |         —         |      ✓       |       ✓        |
| `metadata`               | object (region/tripwire geometry)         |      —       |         —         |      ✓       |       ✓        |

**Notes on `rate`**: In `data/scene` the field is a single number (scene processing rate in Hz).
In `regulated/scene` the field is a per-camera map `{camera_id: framerate}`.

**Notes on `entered`/`exited`**: Each element wraps a full track object: `{"object": {…}, "dwell": <seconds>}`.
Both arrays are present in region and tripwire events; they may be empty (`[]`) when no state change occurred.

**Notes on `metadata`**: Shape differs by event type:

| Key          |     Region event     |  Tripwire event   |
| ------------ | :------------------: | :---------------: |
| `title`      |          ✓           |         ✓         |
| `uuid`       |          ✓           |         ✓         |
| `points`     | ✓ (polygon vertices) | ✓ (two endpoints) |
| `area`       |   ✓ (`"poly"`, …)    |         —         |
| `fromSensor` |     ✓ (boolean)      |         —         |

---

## Track Object Fields (`objects[*]`, `entered[*].object`, `exited[*].object`)

| Field            | Type                                          | `data/scene` | `regulated/scene` | Region Event | Tripwire Event |
| ---------------- | --------------------------------------------- | :----------: | :---------------: | :----------: | :------------: |
| `id`             | string (UUID)                                 |      ✓       |         ✓         |      ✓       |       ✓        |
| `type`           | string                                        |      ✓       |         ✓         |      ✓       |       ✓        |
| `category`       | string                                        |      ✓       |         ✓         |      ✓       |       ✓        |
| `confidence`     | number                                        |      ✓       |         ✓         |      ✓       |       ✓        |
| `translation`    | array[3] of number                            |      ✓       |         ✓         |      ✓       |       ✓        |
| `size`           | array[3] of number                            |      ✓       |         ✓         |      ✓       |       ✓        |
| `velocity`       | array[3] of number                            |      ✓       |         ✓         |      ✓       |       ✓        |
| `rotation`       | array[4] of number                            |      ✓       |         ✓         |      ✓       |       ✓        |
| `visibility`     | array of string                               |      ✓       |         ✓         |      ✓       |       ✓        |
| `center_of_mass` | object `{x,y,width,height}`                   |      ✓       |         ✓         |      ✓       |       ✓        |
| `similarity`     | number or null                                |      ✓       |         ✓         |      ✓       |       ✓        |
| `first_seen`     | string (ISO 8601)                             |      ✓       |         ✓         |      ✓       |       ✓        |
| `metadata`       | object (semantic attributes)                  |      ✓       |         ✓         |      ✓       |       ✓        |
| `camera_bounds`  | object `{camera_id: {x,y,width,height}}`      |      ✓       |         ✓         |      ✓       |       ✓        |
| `regions`        | object `{region_id: {entered: timestamp}}`    |      ✓       |         ✓         |      ✓       |       —        |
| `sensors`        | object `{sensor_id: [[timestamp, value], …]}` |      ✓       |         ✓         |      ✓       |       —        |
| `direction`      | integer (`1` or `-1`)                         |      —       |         —         |      —       |       ✓        |

**Notes on `metadata`**: Propagated from camera detection metadata when visual analytics
(e.g. age, gender) are configured. Each attribute follows `{label, model_name, confidence?}`.
The `reid` attribute has a special difference from camera input: in scene output
`reid.embedding_vector` is a **2D float array** (`[[...numbers...]]`), whereas in camera
input it is a base64-encoded string. `metadata` may be absent when no semantic analytics
are running.

**Notes on `camera_bounds`**: Present in all formats; may be an empty object (`{}`) when
no camera is currently observing the track (e.g. when `visibility` is `[]`).

**Notes on `regions`/`sensors`**: Absent from tripwire event track objects.
In `exited[*].object` from region events, `regions` may be an empty object (`{}`).
`sensors` is present only when sensor readings have been tagged to the track.

**Notes on `direction`**: Indicates which side of the tripwire the object crossed toward.
`1` = positive direction, `-1` = negative direction.

---

## Sample Files

| Format          | Sample file                                                      |
| --------------- | ---------------------------------------------------------------- |
| Data scene      | `data_scene.json`, `data_scene_semantic_metadata.json`           |
| Regulated scene | `regulated_scene.json`, `regulated_scene_sematnic_metadata.json` |
| Region event    | `event_region_objects.json`                                      |
| Tripwire event  | `event_tripwire.json`                                            |
