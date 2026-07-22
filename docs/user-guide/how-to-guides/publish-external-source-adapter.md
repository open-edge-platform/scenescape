<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Publish Observations from an External Source Adapter

This guide shows how to write a small converter (adapter) that takes a source's
native output — for example MAVLink, ROS 2, NMEA, CAN, a vendor UWB/RTLS JSON
feed, or proprietary robot telemetry — and publishes it as Scenescape
`external_source` messages over authenticated MQTT.

The field-level contract, pose-trust rules, identity guidance, and full JSON
examples live in
[External Source Input Message Format](../microservices/controller/data_formats.md#external-source-input-message-format).
This page is procedure only; do not treat snippets here as a second copy of the
schema.

## What You Will Build

```text
Native source  -->  converter script  -->  MQTT broker
                         |                      |
                         |                      v
                         |           scenescape/external/{publisher_id}/{thing_type}
                         |                      |
                         |                      v
                         +------------->  Scene Controller (binds to scenes)
```

The converter owns all translation from the source's ID scheme, units, and
coordinate frame into the Scenescape contract. The Scene Controller does not
maintain a per-publisher ID-mapping cache.

Publish under your persistent `source_id` (topic path = publisher id). Scene
membership is consumer-side binding (`wgs84` geospatial auto-attach, or
`CONTROLLER_EXTERNAL_SOURCE_BINDINGS`). See
[ADR 14](../../adr/0014-unified-external-source-ingestion.md).

## Prerequisites

- A running Scenescape deployment with MQTT broker reachability.
- A persistent publisher id (`source_id`) and the object category topic segment
  (`thing_type`, for example `person` or `vehicle`).
- MQTT credentials and the Scenescape CA certificate used by the broker.
- If the converter will publish `reference_frame: wgs84` poses: at least one
  scene must have valid four-corner geospatial calibration. See
  [Configure Geospatial Coordinates](./build-a-scene/configure-geospatial-coordinates.md).
- If the converter will publish `reference_frame: scene` poses: the converter's
  `source_id` must appear in `CONTROLLER_TRUSTED_POSITIONING_SOURCES` (see
  [Scene Controller](../microservices/controller/controller.md)).

Familiarity with the source protocol and with JSON/MQTT is assumed. Architecture
background:
[ADR 14 — Unified External-Source Ingestion](../../adr/0014-unified-external-source-ingestion.md).

## Mapping Checklist

Work through these steps for your source. Follow the linked anchors for required
fields and examples; do not invent alternate shapes.

1. **Choose a persistent `source_id`** for the publishing agent or service.
   Prefer a hardware-rooted or MAC-based identifier. See
   [Choosing a `source_id`](../microservices/controller/data_formats.md#choosing-a-source_id-self-identification-for-agents).

2. **Build the top-level message** with `timestamp`, `source_id`, and `objects`
   (pose is optional once cached). See
   [External Source Top-Level Fields](../microservices/controller/data_formats.md#external-source-top-level-fields).

3. **Decide the pose reference frame**:
   - `wgs84` — global geopose from GNSS/INS; any source may publish it when the
     scene is geo-referenced.
   - `scene` — pose already in scene-local coordinates; privileged and rejected
     unless the `source_id` is trusted for positioning.
   Details:
   [External Source Pose Fields](../microservices/controller/data_formats.md#external-source-pose-fields-pose).

4. **Map each native observation** to an `objects[*]` entry with a required
   string `id`, `category`, and `translation` in the **source's local frame**
   (relative to the source origin described by `pose`). Optional `size`,
   `rotation`, `confidence`, and `metadata` follow the same contract. See
   [External Detection Object Fields](../microservices/controller/data_formats.md#external-detection-object-fields-objects).

5. **Keep object `id` values persistent and unique** within your source. They
   are trusted as global track identity by default, with cross-source collision
   detection. Do not mint a fresh UUID on every process restart. See
   [Trusted Identity by Default, with Collision Detection](../microservices/controller/data_formats.md#trusted-identity-by-default-with-collision-detection).

6. **Resolve coordinate conventions in the converter**, not in the controller:
   - Quaternions are `(x, y, z, w)`.
   - Object `translation` is metres relative to the source local origin.
   - Pose places that origin in either WGS84 (`lat_long_alt`) or scene-local
     (`translation`), matching `reference_frame`.

## Pose Reuse

After a successful pose is cached for `(bound_scene_uid, source_id)`, later messages may
omit `pose` and reuse the cached transform. A message with `pose` and an empty
`objects` array refreshes the cache without ingesting observations.

If no usable transform is available, or a pose fails trust/geo checks, the
controller drops the message and logs a rejection reason. See
[Pose Caching and Message Ordering](../microservices/controller/data_formats.md#pose-caching-and-message-ordering).

## Minimal MQTT Publish Skeleton

The following skeleton shows authenticated publish using
`scene_common.mqtt.PubSub` (the same helper used by Scenescape tests). Replace
`map_native_message` with your protocol-specific conversion. It is not a
production MAVLink/ROS/NMEA adapter.

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Minimal external-source publisher skeleton.

Replace map_native_message() with conversion from your source's native format
into the external_source contract documented in
docs/user-guide/microservices/controller/data_formats.md.
"""

import json
import os
import time

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

SCENE_ID = os.environ.get("SCENESCAPE_SCENE_ID", "")  # optional; for ops notes / manual bindings
THING_TYPE = os.environ.get("SCENESCAPE_THING_TYPE", "person")
SOURCE_ID = os.environ["SCENESCAPE_SOURCE_ID"]
BROKER = os.environ.get("SCENESCAPE_BROKER", "localhost")
BROKER_PORT = int(os.environ.get("SCENESCAPE_BROKER_PORT", "1883"))
# "user:password" or path to a JSON auth file accepted by PubSub
MQTT_AUTH = os.environ["SCENESCAPE_MQTT_AUTH"]
ROOT_CERT = os.environ["SCENESCAPE_ROOT_CERT"]


def map_native_message(native):
  """Convert one native sample into an external_source payload dict.

  Must include timestamp, source_id, and objects; include pose when needed.
  See data_formats.md for the canonical field definitions and examples.
  """
  raise NotImplementedError("map your native fields here")


def main():
  pubsub = PubSub(MQTT_AUTH, None, ROOT_CERT, BROKER, port=BROKER_PORT)
  pubsub.connect()
  pubsub.loopStart()
  topic = PubSub.formatTopic(
    PubSub.DATA_EXTERNAL, scene_id=SOURCE_ID, thing_type=THING_TYPE)

  while True:
    native = read_next_native_sample()  # your source I/O
    payload = map_native_message(native)
    payload.setdefault("timestamp", get_iso_time())
    payload.setdefault("source_id", SOURCE_ID)
    pubsub.publish(topic, json.dumps(payload))
    time.sleep(0.1)


def read_next_native_sample():
  raise NotImplementedError("read from MAVLink, ROS, UWB JSON, etc.")


if __name__ == "__main__":
  main()
```

Environment variables keep credentials out of source. Never hard-code passwords
or certificates in the converter. Topic path uses `SOURCE_ID`; optional
`SCENE_ID` is only for documenting manual
`CONTROLLER_EXTERNAL_SOURCE_BINDINGS` entries.

## Validate the Integration

1. Start the converter against a deployment that has a geo-calibrated scene
   (for `wgs84`) or a manual binding plus trusted positioning `source_id`
   (for `scene`).
2. Confirm messages arrive on
   `scenescape/external/{publisher_id}/{thing_type}` (MQTT client or broker logs).
3. Watch `scenescape/data/scene/{scene_id}/{thing_type}` (or the 3D UI) for
   ingested objects whose `id` matches what the converter published.
4. If nothing appears, check Scene Controller logs for pose/identity rejection
   reasons listed under
   [Pose Caching and Message Ordering](../microservices/controller/data_formats.md#pose-caching-and-message-ordering).

End-to-end MQTT coverage that exercises this path lives in
[`tests/functional/test_external_source_ingest.py`](https://github.com/open-edge-platform/scenescape/blob/main/tests/functional/test_external_source_ingest.py).

## Out of Scope

The adapter and this guide do **not** cover:

- Footprint-based multi-scene handoff policy (platform **binding** Future Work,
  [ADR 14](../../adr/0014-unified-external-source-ingestion.md))
- Cross-source fusion or camera/external deduplication
- Stronger trust-domain join / MQTT ACL hardening beyond same-authority certs
  (ADR 14 Future Work — discuss with security)

## See Also

- [External Source Input Message Format](../microservices/controller/data_formats.md#external-source-input-message-format)
- [Scene Controller](../microservices/controller/controller.md)
- [ADR 14 — Unified External-Source Ingestion](../../adr/0014-unified-external-source-ingestion.md)
- [Integrate Cameras and Sensors](./integrate-cameras-and-sensors.md)
- Example MAVLink adapter:
  [`tools/external_source_adapters/`](../../../tools/external_source_adapters/README.md)
  (`mavlink_to_external_source.py`)
