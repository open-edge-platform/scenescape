<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# External Source Adapters

Example converters that map a source's native telemetry into the Scene Controller
`external_source` MQTT contract.

Canonical contract (do not duplicate field tables here):
[`docs/user-guide/microservices/controller/data_formats.md`](../../docs/user-guide/microservices/controller/data_formats.md)
(External Source Input Message Format).

How-to:
[`docs/user-guide/how-to-guides/publish-external-source-adapter.md`](../../docs/user-guide/how-to-guides/publish-external-source-adapter.md).

## MAVLink → external_source

[`mavlink_to_external_source.py`](./mavlink_to_external_source.py) reads
`GLOBAL_POSITION_INT` (fallback `GPS_RAW_INT`) and `ATTITUDE` from a MAVLink
connection and publishes `reference_frame: wgs84` poses. Optionally it also
publishes the vehicle as a tracked object at the source local origin
`[0, 0, 0]`, using the same persistent string for `source_id` and `objects[*].id`.

### Requirements

- Python 3.10+
- Scenescape `scene_common` importable (run from a Scenescape environment)
- Target scene geo-calibrated (required for `wgs84` poses)
- `pymavlink`

```bash
pip install -r tools/external_source_adapters/requirements.txt
```

### Configuration (environment)

| Variable                 | Required | Description                                                                 |
| ------------------------ | :------: | --------------------------------------------------------------------------- |
| `SCENESCAPE_SCENE_ID`    |   Yes    | Target scene id (topic segment)                                             |
| `SCENESCAPE_SOURCE_ID`   |   Yes    | Persistent publisher id (serial, MAC, or deployer-assigned; not a boot UUID) |
| `SCENESCAPE_MQTT_AUTH`   |   Yes    | `user:password` or path to PubSub JSON auth file                            |
| `SCENESCAPE_ROOT_CERT`   |   Yes    | Path to Scenescape CA certificate                                           |
| `SCENESCAPE_THING_TYPE`  |    No    | MQTT `{thing_type}` segment (default `vehicle`)                             |
| `SCENESCAPE_OBJECT_CATEGORY` | No   | Object `category` when publishing self (default = thing type)               |
| `SCENESCAPE_BROKER`      |    No    | Broker host (default `localhost`)                                           |
| `SCENESCAPE_BROKER_PORT` |    No    | Broker port (default `1883`)                                                |
| `MAVLINK_CONNECTION`     |    No    | pymavlink connection string (default `udp:0.0.0.0:14550`)                   |
| `MAVLINK_BAUD`           |    No    | Serial baud when using a device path (default `57600`)                      |
| `PUBLISH_HZ`             |    No    | Publish rate (default `5`)                                                  |
| `PUBLISH_SELF`           |    No    | `true`/`false` — include vehicle object at origin (default `true`)          |
| `POSE_EVERY_N`           |    No    | Include pose every N publishes for cache reuse (default `1`)                |
| `LOG_LEVEL`              |    No    | Logging level (default `INFO`)                                              |

### Usage

```bash
export SCENESCAPE_SCENE_ID="<scene-uid>"
export SCENESCAPE_SOURCE_ID="drone-1"   # prefer hardware/MAC-based id in production
export SCENESCAPE_MQTT_AUTH="user:password"
export SCENESCAPE_ROOT_CERT="/path/to/scenescape-ca.pem"
export MAVLINK_CONNECTION="udp:0.0.0.0:14550"

python tools/external_source_adapters/mavlink_to_external_source.py
```

Examples of `--connection` / `MAVLINK_CONNECTION` values:

- UDP listen (SITL / GCS forward): `udp:0.0.0.0:14550`
- UDP client: `udpout:127.0.0.1:14550`
- Serial: `/dev/ttyUSB0` (set `MAVLINK_BAUD`)
- TCP: `tcp:127.0.0.1:5760`

### Validate

1. Confirm the target scene has valid geospatial calibration.
2. Watch `scenescape/external/{scene_id}/{thing_type}` for published JSON.
3. Watch `scenescape/data/scene/{scene_id}/{thing_type}` (or the 3D UI) for the
   object whose `id` matches `SCENESCAPE_SOURCE_ID`.
4. Check Scene Controller logs for pose rejection reasons if nothing appears
   (see Pose Caching in `data_formats.md`).

### Out of scope

- Scene discovery / multi-scene fan-out
- Detecting other objects from onboard vision (only the vehicle pose/self)
- NMEA (use a separate adapter; MAVLink already carries GNSS in a richer form)
