<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Add and Use Radar Sensors

- **Time to Complete:** About 20 minutes (plus optional VIDETEC convert/replay)

This guide shows how to provision a first-class **radar** sensor in SceneScape,
publish 3-D detections on `scenescape/data/radar/{radar_id}`, and optionally
replay [VIDETEC-2](https://zenodo.org/records/17799385) frames (CC BY 4.0).

Radar is a scene sensor with a fixed pose (like a camera), not an
`external_source` adapter. The Controller transforms radar-local detections
into scene space using the sensor extrinsics stored in Manager.

## Prerequisites

- A running SceneScape stack (Manager, Controller, MQTT broker).
- An existing scene and an auth token with permission to create sensors.
- Optional: Python 3 with `numpy` / `h5py` for VIDETEC conversion
  (`radar/requirements.txt`).

## 1. Provision a radar

### UI

1. Open **Radars** in the Manager nav, or open a scene and use the **Radars** tab.
2. Create a radar with a unique **Radar ID** and attach it to the scene.
3. Set pose via REST (step below). UI create only stores id/name/scene.

### REST

```bash
curl -k -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "gantry-radar",
    "sensor_id": "radar1",
    "scene": "<scene-uid>",
    "transform_type": "euler",
    "translation": [0.0, 0.0, 8.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0]
  }' \
  https://localhost/api/v1/radar
```

`translation` / `rotation` (Euler degrees) / `scale` define the radar pose in
the scene. Point-correspondence calibration is not used for radar.

Scene import JSON may include a `radars` array with the same fields (see camera
import for structure).

## 2. Live detection contract

Publish detector metadata on:

`scenescape/data/radar/{radar_id}`

Use the same `detector` schema as cameras (`id`, `timestamp`, `objects`). Prefer
**3-D** detections with `translation` + `size` in **radar-local metres**. Always
publish frames, including empty `objects`, so tracks clear.

```json
{
  "id": "radar1",
  "timestamp": "2026-08-28T18:00:00.000Z",
  "rate": 10.0,
  "objects": {
    "vehicle": [
      {
        "id": 1,
        "category": "vehicle",
        "translation": [12.0, -1.5, 0.0],
        "size": [2.0, 1.5, 1.5],
        "confidence": 0.85
      }
    ]
  }
}
```

Native perception input (before clustering) is a per-frame `float32 (N, 5)` list:

`[range_m, doppler_mps, azimuth_deg, elevation_deg, magnitude]`

The `radar/` service converts those frames to the MQTT detector payload above.

## 3. Run the radar publisher

From the repo `radar/` directory:

```bash
python3 radar_publisher.py --radar-id radar1 --frames-dir ./frames \
  --broker broker.scenescape.intel.com \
  --user <mqtt-user> --password <mqtt-pass>
```

Or pipe JSON arrays of `(N, 5)` detections on stdin (one frame per line).

## 4. VIDETEC-2 replay example

[VIDETEC-2](https://zenodo.org/records/17799385) provides gantry FMCW radar at
an intersection under **CC BY 4.0**. HDF5 is archive-only; convert to live
frames before replay:

```bash
python3 videtec_hdf5_to_frames.py /path/to/videtec.h5 -o ./frames
python3 radar_publisher.py --radar-id radar1 --frames-dir ./frames \
  --broker broker.scenescape.intel.com --user <user> --password <pass>
```

Set the Manager radar pose from the dataset `/sensor` metadata (gantry
position/orientation) so Controller extrinsics match the recording.

### Attribution

When using or redistributing VIDETEC-derived frames, attribute:

> VIDETEC-2 dataset, Zenodo record [17799385](https://zenodo.org/records/17799385),
> Creative Commons Attribution 4.0 International (CC BY 4.0).

## 5. Validate

1. Confirm the radar appears on the scene (Manager scene detail → **Radars**).
2. Publish detections (or run the publisher).
3. Confirm tracked objects appear in the scene UI / regulated scene MQTT topic.
4. If nothing appears: check radar pose is set, `id` matches the provisioned
   `sensor_id`, and the Controller subscribed after the create (DB update).

## Related documentation

- [Run the Radar-Intersection Fusion Demo](./run-radar-intersection-demo.md)
- [Integrate Cameras and Sensors](./integrate-cameras-and-sensors.md)
- [Scene Controller Data Formats](../microservices/controller/data_formats.md)
- [Radar service README](../../../radar/README.md)
