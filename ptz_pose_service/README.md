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
      "invert_tilt": false,
      "pose_update_mode": "ptz_delta"
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
  `[-1, 1]`, etc.) without guessing a multiplier by hand. If the camera's
  ONVIF profile doesn't advertise a position range at all (`GetNodes`
  returns nothing usable), `pan_degrees`/`tilt_degrees` is still honored by
  assuming the standard ONVIF generic normalized range (`[-1, 1]`), since
  that's what the vast majority of ONVIF PTZ cameras report position in
  regardless of whether they expose that metadata.
- `pan_scale`/`tilt_scale`: explicit degrees-per-unit overrides. If set,
  they take priority over `pan_degrees`/`tilt_degrees` and the
  `--pan-scale`/`--tilt-scale` CLI defaults. Use these when a camera doesn't
  advertise a usable position range, or its space's real degrees are known
  directly (in which case a scale of `1.0` is normally correct).
- `invert_pan`/`invert_tilt`: per-camera overrides of `--invert-pan`/`--invert-tilt`.
- `pose_update_mode`: per-camera override of `--pose-update-mode` — which
  mechanism keeps this camera's pose in sync (see below).

## Pose update modes

How a camera's Scenescape pose is kept in sync with its live PTZ position is
selected with `--pose-update-mode` (or per camera via `pose_update_mode`):

### `ptz_delta` (default)

Rotates the camera's calibrated "home" pose by its pan/tilt delta, converted
to degrees via `pan_degrees`/`tilt_degrees` (or an explicit
`pan_scale`/`tilt_scale`). Needs no video feed and no AprilTags — but it does
need the camera's physical sweep range to be known, since most ONVIF cameras
report position in a normalized `[-1, 1]` space rather than real degrees. If
the position space can't be converted to degrees and no `pan_degrees`/
`tilt_degrees` is configured, the service logs a warning and falls back to
the `--pan-scale`/`--tilt-scale` defaults, which will not be accurate.

### `autocalibration` (opt-in)

Re-runs full AprilTag-based auto-calibration after each move: watches the raw
pan/tilt for movement, waits for it to settle (`--recal-settle-s`), grabs a
fresh frame via the same MQTT `getcalibrationimage` mechanism the manual
calibration UI uses, and asks the autocalibration service for a new pose.

This requires a clear view of well-distributed AprilTags at every pan/tilt
position the camera will be used at. Tags that are (near-)coplanar or lack
depth/height variation make the underlying `solvePnP` solve unreliable, and
the autocalibration service rejects such results outright rather than
returning a wrong pose. Results are additionally sanity-checked here against
`--min-camera-height` and `--max-translation-drift` (a fixed PTZ mount's
position shouldn't move between recalibrations, and should be above the
floor). A rejected result keeps the previous pose, logs why, and is retried
on the next pan/tilt change.

Auto-calibration can always be triggered manually from the camera's
calibration page in the Scenescape UI, regardless of the configured mode.

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
| `--pose-update-mode` | `ptz_delta` | default pose sync mechanism (`ptz_delta` or `autocalibration`) |
| `--recal-settle-s` | `2.0` | (autocalibration mode) how long pan/tilt must be still before recalibrating |
| `--min-raw-delta` | `0.02` | (autocalibration mode) minimum raw pan/tilt change counted as movement |
| `--min-camera-height` | `0.1` | (autocalibration mode) reject a result below this Z |
| `--max-translation-drift` | `1.0` | (autocalibration mode) reject a result that moved further than this |
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
