<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Radar ingest service

First-class SceneScape radar publisher for VIDETEC-style detection lists.

## Live frame contract

Each frame is `float32 (N, 5)`:

| Column | Unit | Meaning |
| --- | --- | --- |
| `range_m` | metres | Slant range |
| `doppler_mps` | m/s | Radial velocity |
| `azimuth_deg` | degrees | From +X toward +Y |
| `elevation_deg` | degrees | From XY plane toward +Z |
| `magnitude` | unitless | Detection strength |

Empty frames (`N=0`) are valid and must be published so tracks clear.

## Pipeline

1. Read live frames (JSON lines on stdin) or replay `.npy`/`.npz` files.
2. Run v1 perception (`radar_perception.py`): spherical→XYZ, distance cluster, NN track.
3. Publish detector JSON on `scenescape/data/radar/{radar_id}` (same object fields as cameras: `translation`, `size`, `category`, `id`, `confidence`).

Coordinates in the MQTT payload are **radar-local metres**. The Scene Controller applies the radar sensor pose provisioned in Manager.

## Provision a radar

```bash
# REST example (euler pose: translation + rotation degrees + scale)
curl -k -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"gantry-radar","sensor_id":"radar1","scene":"<scene-uid>",
       "transform_type":"euler","translation":[0,0,8],
       "rotation":[0,0,0],"scale":[1,1,1]}' \
  https://localhost/api/v1/radar
```

## Replay converted frames

```bash
python3 videtec_hdf5_to_frames.py /path/to/videtec.h5 -o ./frames
python3 radar_publisher.py --radar-id radar1 --frames-dir ./frames \
  --broker broker.scenescape.intel.com --user <user> --password <pass>
```

## VIDETEC-2 example dataset

[VIDETEC-2](https://zenodo.org/records/17799385) (CC BY 4.0) provides gantry FMCW detections at an intersection. HDF5 `/detections` is archive-only; convert with `videtec_hdf5_to_frames.py` before replay.

When using or redistributing converted frames, attribute: *VIDETEC-2, Zenodo, CC BY 4.0*.
