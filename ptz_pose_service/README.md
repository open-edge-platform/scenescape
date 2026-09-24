# PTZ Pose Service

Keeps a Scenescape camera's stored `rotation` in sync with a physical ONVIF
PTZ camera's live pan/tilt position.

**Status**: experimental / first iteration — pan & tilt only, no zoom, docker
logs are the only feedback mechanism for now.

## What it does

1. On startup, for each camera in the config file:
   - resolves an ONVIF PTZ media profile (auto-detected if not pinned),
   - if `pan_degrees`/`tilt_degrees` is configured, queries the camera's own
     advertised absolute pan/tilt position range (ONVIF `GetNodes`) and
     derives a degrees-per-unit scale factor from it, so cameras with
     different physical fields of view (e.g. 360° vs. 90° pan) or different
     position-reporting units are normalized correctly (see `pan_degrees`/
     `tilt_degrees` in the config schema below),
   - fetches the camera's calibrated `rotation` from Scenescape via the REST
     API (this is the pose set during scene calibration, at whatever pan/tilt
     the camera physically had at that time — the "home" position),
   - records the ONVIF pan/tilt reading at that home position, either from
     the config file (`home_pan`/`home_tilt`) or, if not given, from the
     camera's current status at startup (i.e. it assumes the camera is still
     at its calibrated position when the service starts).
2. Polls each camera's PTZ status (`GetStatus`) at `--poll-hz` (default 5×/s).
3. Normalizes the raw pan/tilt delta from home into degrees (using the
   resolved scale factors) and converts it into a new `[roll, pitch, yaw]`
   rotation (yaw ← pan, pitch ← tilt, roll unchanged); when the change
   exceeds `--min-delta-deg`, `PATCH`es the camera's `rotation` via
   `updateCamera()` and logs the change.

See [pose_math.py](src/pose_math.py) for the exact math and its documented
assumptions/limitations (linear pan/tilt→degrees mapping, no zoom, no full
quaternion composition).

## Discovering cameras

To find ONVIF/PTZ-capable cameras on the network (no Scenescape REST
connection required) and get the values needed for the config file:

```bash
python3 src/ptz_pose_service.py --discover-only \
    --onvif-username admin --onvif-password admin123
```

or, once the image is built:

```bash
docker run --rm --network host intel/scenescape-ptz-pose-service:latest \
    --discover-only
```

## Config file (`--config`, default `/app/config/cameras.json`)

```json
{
  "cameras": [
    {
      "onvif_host": "192.168.0.92",
      "onvif_port": 80,
      "scene_camera_uid": "<uid of the camera as calibrated in Scenescape>",
      "profile_token": null,
      "home_pan": null,
      "home_tilt": null,
      "pan_degrees": 360.0,
      "tilt_degrees": 90.0,
      "pan_scale": null,
      "tilt_scale": null,
      "invert_pan": false,
      "invert_tilt": false
    }
  ]
}
```

- `profile_token`: optional; auto-detected (first PTZ-capable profile) if omitted.
- `home_pan`/`home_tilt`: optional; if omitted, the camera's pan/tilt at
  service startup is used as home. Set these explicitly if the service may
  restart while the camera isn't at its calibrated position.
- `pan_degrees`/`tilt_degrees`: the camera's real physical field of view in
  degrees (from its datasheet, e.g. `360` for a full-turn pan turret or `90`
  for a limited-sweep camera). If set, the service queries the camera's own
  advertised `AbsolutePanTiltPositionSpace` range via ONVIF `GetNodes` at
  startup and derives `pan_scale`/`tilt_scale` from it automatically — this
  is the recommended way to configure scale, since it normalizes for
  whatever units that particular camera reports (raw degrees, normalized
  `[-1, 1]`, etc.) without guessing a multiplier by hand.
- `pan_scale`/`tilt_scale`: explicit degrees-per-unit overrides. If set,
  they take priority over `pan_degrees`/`tilt_degrees` and the
  `--pan-scale`/`--tilt-scale` CLI defaults. Use these when a camera doesn't
  advertise a usable position range, or its space's real degrees are known
  directly (in which case a scale of `1.0` is normally correct).
- `invert_pan`/`invert_tilt`: per-camera overrides of `--invert-pan`/`--invert-tilt`.

## Environment variables / credentials

- `ONVIF_USERNAME` / `ONVIF_PASSWORD`: credentials used to authenticate to
  every configured ONVIF camera (default for `--onvif-username`/`--onvif-password`).

## CLI options

| Option | Default | Description |
|---|---|---|
| `--resturl` | `https://web.scenescape.intel.com:443/api/v1` | Scenescape REST API base URL |
| `--restauth` | `/run/secrets/calibration.auth` | REST auth file or `user:pass` |
| `--rootcert` | `/run/secrets/certs/scenescape-ca.pem` | CA cert for REST TLS |
| `--config` | `/app/config/cameras.json` | camera map config file |
| `--onvif-username` / `--onvif-password` | env vars | ONVIF credentials |
| `--poll-hz` | `5.0` | PTZ status poll rate |
| `--min-delta-deg` | `0.2` | minimum rotation change before a REST update is sent |
| `--pan-scale` / `--tilt-scale` | `1.0` | default degrees per unit of ONVIF pan/tilt |
| `--invert-pan` / `--invert-tilt` | `false` | flip sign of pan/tilt contribution |
| `--discover-only` | `false` | discover cameras, log them, exit (no REST connection) |

## Build

```bash
make -C ptz_pose_service vendor-deps   # clones dlstreamer.onvif on the host
make ptz_pose_service                   # from the repo root, or:
make -C ptz_pose_service build-image
```

## Deploying with the PTZ demo compose file

See `sample_data/compose/docker-compose-ptz-demo.yml`, service `ptz-pose`
(profile `ptz-pose`). Populate `ptz_pose_service/config/cameras.json` with
the camera UIDs from your scene before starting it, and set
`ONVIF_USERNAME`/`ONVIF_PASSWORD` in your environment/`.env`.
