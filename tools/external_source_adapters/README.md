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

Installs `pymavlink`, `remoteid` and `paho-mqtt` (required by
`scene_common.mqtt.PubSub`).
The PX4 demo script (`tools/px4_sih_demo/run_demo.sh adapter`) uses an isolated
venv and installs these automatically.

### Configuration (environment)

| Variable                     | Required | Description                                                                               |
| ---------------------------- | :------: | ----------------------------------------------------------------------------------------- |
| `SCENESCAPE_SOURCE_ID`       |   Yes    | Persistent publisher id (topic path + payload `source_id`)                                |
| `SCENESCAPE_MQTT_AUTH`       |   Yes    | `user:password` or path to PubSub JSON auth file (e.g. `manager/secrets/controller.auth`) |
| `SCENESCAPE_ROOT_CERT`       |   Yes    | Path to Scenescape CA certificate                                                         |
| `SCENESCAPE_SCENE_ID`        |    No    | Optional scene hint for ops / manual `CONTROLLER_EXTERNAL_SOURCE_BINDINGS`                |
| `SCENESCAPE_THING_TYPE`      |    No    | MQTT `{thing_type}` segment (default `vehicle`)                                           |
| `SCENESCAPE_OBJECT_CATEGORY` |    No    | Object `category` when publishing self (default = thing type)                             |
| `SCENESCAPE_BROKER`          |    No    | Broker host (default `localhost`)                                                         |
| `SCENESCAPE_BROKER_PORT`     |    No    | Broker port (default `1883`)                                                              |
| `MAVLINK_CONNECTION`         |    No    | pymavlink connection string (default `udp:0.0.0.0:14550`)                                 |
| `MAVLINK_BAUD`               |    No    | Serial baud when using a device path (default `57600`)                                    |
| `PUBLISH_HZ`                 |    No    | Publish rate (default `5`)                                                                |
| `PUBLISH_SELF`               |    No    | `true`/`false` — include vehicle object at origin (default `true`)                        |
| `POSE_EVERY_N`               |    No    | Include pose every N publishes for cache reuse (default `1`)                              |
| `LOG_LEVEL`                  |    No    | Logging level (default `INFO`)                                                            |

### Usage

```bash
export SCENESCAPE_SOURCE_ID="drone-1"   # prefer hardware/MAC-based id in production
export SCENESCAPE_MQTT_AUTH="user:password"
export SCENESCAPE_ROOT_CERT="/path/to/scenescape-ca.pem"
export MAVLINK_CONNECTION="udp:0.0.0.0:14550"
# Optional: export SCENESCAPE_SCENE_ID="<scene-uid>" for binding docs only

python tools/external_source_adapters/mavlink_to_external_source.py
```

Examples of `--connection` / `MAVLINK_CONNECTION` values:

- UDP listen (SITL / GCS forward): `udp:0.0.0.0:14550`
- UDP client: `udpout:127.0.0.1:14550`
- Serial: `/dev/ttyUSB0` (set `MAVLINK_BAUD`)
- TCP: `tcp:127.0.0.1:5760`

### Validate

1. Confirm the target scene has valid geospatial calibration.
2. Watch `scenescape/external/{publisher_id}/{thing_type}` for published JSON.
3. Watch `scenescape/data/scene/{scene_id}/{thing_type}` (or the 3D UI) for the
   object whose `id` matches `SCENESCAPE_SOURCE_ID`.
4. Check Scene Controller logs for pose rejection reasons if nothing appears
   (see Pose Caching in `data_formats.md`).

### PX4 SIH end-to-end demo

For a full walkthrough (Mapbox geospatial scene, ROI, PX4 SIH Docker, and this
adapter), see [`tools/px4_sih_demo/README.md`](../px4_sih_demo/README.md).

### Out of scope

- Scene discovery / multi-scene fan-out
- Detecting other objects from onboard vision (only the vehicle pose/self)
- NMEA (use a separate adapter; MAVLink already carries GNSS in a richer form)

## Remote ID → external_source

[`remoteid_to_external_source.py`](./remoteid_to_external_source.py) listens
for drones broadcasting ASTM F3411 / ASD-STAN EN 4709-002 Remote ID over Wi-Fi
(Beacon and NAN) and publishes each aircraft it hears as its own external
source with a `reference_frame: wgs84` pose, the same contract the MAVLink
adapter uses for its own vehicle. Unlike MAVLink, these are third-party
aircraft: the adapter needs no link to the drone, only a Wi-Fi card in monitor
mode near the scene.

- The publisher id is `SCENESCAPE_SOURCE_PREFIX` plus the transmitter MAC
  address (for example `rid-ae996eb0ee1f`), so one radio is one scene object.
- The pose uses the broadcast geodetic altitude (WGS84 ellipsoid). Aircraft that
  have not broadcast a position with geodetic altitude yet are not published.
- Decoding and trust checks come from the
  [`remoteid`](https://github.com/Mattbusel/remoteid) package (MIT, Rust with
  abi3 wheels). The object `metadata` carries `remote_id_trust` (`label` is
  `authenticated`, `plausible`, `suspicious` or `spoofed`, `confidence` is the
  0 to 1 score), `remote_id_reasons` (for example `teleport`, `known_spoofer`)
  and `remote_id_uas_id` (the broadcast serial number or registration ID).
  Remote ID is unauthenticated on most aircraft and can be spoofed from a
  laptop, so treat `spoofed` and `suspicious` objects accordingly.

Bluetooth Remote ID is not read by this script; the `remoteid` package decodes
it (`remoteid.decode(adv_data, "ble_adv")`) if you feed it from a BLE scanner.

### Configuration (environment)

Uses the same `SCENESCAPE_MQTT_AUTH`, `SCENESCAPE_ROOT_CERT`,
`SCENESCAPE_BROKER`, `SCENESCAPE_BROKER_PORT`, `SCENESCAPE_THING_TYPE`,
`SCENESCAPE_OBJECT_CATEGORY`, `SCENESCAPE_OBJECT_SIZE` and `LOG_LEVEL`
variables as the MAVLink adapter, plus:

| Variable                   | Required | Description                                                              |
| -------------------------- | :------: | ------------------------------------------------------------------------ |
| `SCENESCAPE_SOURCE_PREFIX` |    No    | Prefix for each aircraft's publisher id (default `rid-`)                 |
| `REMOTEID_INTERFACE`       | One of ① | Linux Wi-Fi interface in monitor mode (`--interface`)                    |
| `REMOTEID_PCAP`            | One of ① | Classic pcap (802.11 or radiotap) to replay at recorded speed (`--pcap`) |
| `PUBLISH_HZ`               |    No    | Maximum publish rate per aircraft (default `1`)                          |
| `REMOTEID_SYSTEM_CLOCK`    |    No    | `true` to use the UTC clock for timestamp and DRIP signature checks      |

① Give exactly one. Only enable `REMOTEID_SYSTEM_CLOCK` on an NTP- or
GNSS-synced host; without it no aircraft can be `authenticated`, and an
unsynced clock would mark every aircraft with clock-drift reasons.

### Usage

```bash
export SCENESCAPE_MQTT_AUTH="user:password"
export SCENESCAPE_ROOT_CERT="/path/to/scenescape-ca.pem"

# Live (Linux, needs root or CAP_NET_RAW). Wi-Fi NAN Remote ID uses 2.4 GHz
# channel 6; Beacon may use any channel, channel 6 is the common one.
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up
sudo iw dev wlan0 set channel 6
sudo -E python tools/external_source_adapters/remoteid_to_external_source.py --interface wlan0

# Replay a capture (tcpdump -i wlan0 -w drones.pcap)
python tools/external_source_adapters/remoteid_to_external_source.py --pcap drones.pcap
```

Validate as for the MAVLink adapter: each aircraft appears on
`scenescape/external/rid-<mac>/{thing_type}` and, once a geo-calibrated scene
covers its position, as an object with that `id` in the scene output.
