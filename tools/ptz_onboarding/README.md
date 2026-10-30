<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# AprilTag PTZ onboarding

Optional, standalone tools to measure **your camera in your scene**. They fit
lens intrinsics/distortion, pan/tilt curves, pan-axis alignment and backlash,
then verify the model against a new AprilTag capture.

No lab cameras, scene archives, credentials, measured models, deployment
overlays or legacy pose service are included. These tools do not install,
configure or change Positioning. Runtime service setup is a separate task.

## 1. Prepare your camera and scene

- Create your own scene and camera in Manager. Add correctly sized AprilTags
  with their measured locations on your scene's 3D geometry. Tag IDs, physical
  size, map scale and world coordinates must match the real installation.
- Enable AprilTag auto-calibration for that scene and start its live video
  pipeline. The pipeline must respond to `getcalibrationimage` MQTT requests.
  Follow the existing [AprilTag scene setup guide](../../docs/user-guide/how-to-guides/calibrate-cameras/autocalibrate-cameras-using-apriltags.md)
  for tag family, map registration and Manager UI steps.
- Use one fixed stream resolution and **fixed zoom**. Disable autofocus changes
  where practical. Do not mix calibration frames from different stream profiles.
- Enter approximate pixel intrinsics `fx`, `fy`, `cx`, `cy` in Manager. Camera
  specifications or an existing calibration are suitable initial estimates.
  For a known horizontal field of view, `fx = width / (2 * tan(hfov / 2))`
  with `hfov` in radians; square pixels usually imply `fy = fx`, and
  `cx = width / 2`, `cy = height / 2`.
- Arrange enough tags to match at least **six world/image points at every
  selected stop**. Spread tags across the frame, including edges, and at
  different depths. Repeated views of a small planar cluster cannot reliably
  determine a lens model.

**Movement warning:** capture/onboard/verify physically move the camera. Stop
all other camera drivers, patrols, auto-tracking and calibration writers during
the whole workflow. Reserve the device for this operation. Choose safe travel
limits with clearance; never run two onboarding jobs on one camera. Returning
home is attempted on failure, but power/network failures can prevent it.

## 2. Install and configure

From the SceneScape repository root (Python 3.10+):

```sh
cd tools/ptz_onboarding
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -m 700 local
cp camera.example.json local/camera.json
```

Edit `local/camera.json`. All camera/scene choices are yours; **there are no
default measurement ranges**. Relative credential/CA paths resolve relative
to this configuration file, not your working directory.

| Setting                              | What to provide                                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| `camera_uid`                         | Existing camera's UID from Manager, not its display name                             |
| `manager_url`, `autocalibration_url` | Reachable HTTPS API roots ending in `/api/v1` and `/v1` respectively                 |
| `ca_cert`                            | CA certificate trusted by both HTTPS endpoints and the TLS MQTT broker               |
| `manager_auth`                       | Local JSON with `user` and `password`, authorized to read/update this camera         |
| `mqtt`                               | TLS broker host/port and local auth JSON with `user` and `password`                  |
| `onvif`                              | Camera host/port and local auth JSON with `username` and `password`                  |
| `onvif.profile_token`                | Exact PTZ media profile token; `null` only if exactly one profile is PTZ-capable     |
| `max_rms_px`                         | Your acceptable held-out pixel RMS; must also satisfy Manager's acceptance threshold |

Use your deployment's reachable addresses and certificate DNS names. The
default MQTT TLS port in some SceneScape deployments is 1883, not 8883; use the
actual configured port. Run on a trusted host/network that can reach all four
endpoints. Set `NO_PROXY` appropriately for local service/camera addresses.
The tool verifies TLS; do not disable certificate checks or expose services
publicly just to run calibration.

Keep accounts outside tracked files, restrict them with `chmod 600`, and use
least-privilege accounts: ONVIF status/absolute movement, Manager camera
read/update, MQTT publish on `scenescape/cmd/camera/<uid>` and subscribe on
`scenescape/image/calibration/camera/<uid>`. Measurements never contain account
files or RTSP URLs. `local/` and `.venv/` are ignored.

### Choose safe measurement positions

All positions are in **this ONVIF profile's native absolute units**, not
degrees. Read the device's ONVIF status/configuration or camera documentation
first; do not assume normalized `[-1, 1]` coordinates or copy another model's
ranges.

| `motion` field            | Meaning                                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| `pan_range`, `tilt_range` | Safe `[minimum, maximum]`, inside advertised ONVIF limits                                       |
| `home`                    | `[pan, tilt]` reference view with well-spread visible tags; away from endpoints/seams           |
| `approach`                | Direction used to reach home, one of `increasing`/`decreasing` per axis                         |
| `approach_offset`         | Positive native-unit distances to move past home before approaching it; must take up backlash   |
| `lens_pan`, `lens_tilt`   | Absolute positions forming a grid; at least two distinct per axis and six grid views total      |
| `pan_path`, `tilt_path`   | Ordered **offsets from home**; at least three distinct per axis, both directions, ending at `0` |
| `settle_s`                | Image settling time **after** feedback confirms arrival; increase for slow cameras              |
| `timeout_s`, `tolerance`  | Arrival timeout and native-unit feedback tolerance                                              |

For example, design each PTZ path as
`[0, -d, -2*d, -d, 0, d, 2*d, d, 0]`, replacing the expressions with numbers
chosen for your camera. Paths include reversals to observe backlash. Lens
positions should move tags across the image, while PTZ paths should cover
the travel where you need accurate projection. No command clips or widens
your requested ranges silently. No wrap-around/full-circle seam handling is
assumed: choose a continuous region away from the seam.

The reported position-space limits are device limits, **not evidence that the
whole mechanical range was validated**. Accuracy is only measured where tags
were visible. Recalibrate after changing camera placement, lens, zoom,
resolution or scene geometry.

## 3. Check, onboard, apply

```sh
# Read-only: credentials, device capabilities, fresh image and tag visibility.
.venv/bin/python ptz.py --config local/camera.json check

# MOVES camera; fits locally and verifies using a second, fresh PTZ capture.
# Choose a new run directory each time. This does not change Manager.
.venv/bin/python ptz.py --config local/camera.json onboard \
  --output-dir local/run-01 --yes

# Review local/run-01/verification.json, then explicitly replace this camera's
# lens settings, home pose and PTZ calibration in ONE Manager request.
# Camera must still be at the approached home with the measured zoom.
.venv/bin/python ptz.py --config local/camera.json apply \
  --model local/run-01/model.json \
  --verification local/run-01/verification.json \
  --backup local/run-01/manager-before.json --yes
```

`onboard` returns to approached home after each capture. It uses a conservative
lens fit (square pixels, centered principal point, one radial coefficient) and
linear PTZ curves by default. It reuses the lab's numerical solvers without
running its legacy pose-tracking implementation.

`apply` re-evaluates held-out points without refitting and refuses a different
model/camera/scene/position space, changed zoom, non-home position, missing data,
non-finite errors or RMS above your limit. It saves the previous calibration
before the write and reads back the new values. Manager can still reject the
payload under its own validation rules. Nothing automatically exports scenes
or restarts services. The solved home is a rigid pose (unit camera scale).

The backup contains calibration fields only. To restore after an accepted
write, use Manager or its camera update API with those previous fields; keep
the original home/zoom consistent. Export a full scene separately beforehand
if you need full-scene recovery. A network failure during `apply` can leave
the update accepted but unconfirmed: inspect Manager before retrying.

## Repeat just one step

```sh
.venv/bin/python ptz.py --config local/camera.json capture-lens --output local/views.json --yes
.venv/bin/python ptz.py --config local/camera.json fit-lens --input local/views.json --output local/lens.json
.venv/bin/python ptz.py --config local/camera.json capture-ptz --output local/ptz.json --yes
.venv/bin/python ptz.py --config local/camera.json fit-ptz \
  --input local/ptz.json --lens local/lens.json --output local/model.json
.venv/bin/python ptz.py --config local/camera.json verify \
  --model local/model.json --output local/verification.json --yes
```

Use `fit-ptz --degree 2` only with sufficient measured coverage. Implausible
extrapolation is rejected rather than silently accepting a bending curve.
Fit commands are offline; they require no camera, broker or running services.
Existing output files are never overwritten.

If tag collection fails, fix scene registration, pipeline delivery, lighting
or tag coverage and start a new capture. If the lens is poorly constrained,
improve edge/depth coverage rather than accepting a low-confidence lens. If
RMS is too high, inspect the captures and scene geometry or expand the
measured region; do not just raise the limit. Increase `approach_offset` if
the fitted backlash is not fully taken up. The nominal tilt axis is
camera-local X. The conservative fitter assumes a pan axis within about
30 degrees of world vertical and scalar backlash up to 6 degrees per axis;
some camera geometries are not described by this model.

This verifies the **calibration model against held-out AprilTag points**,
not end-to-end live Positioning/Controller frame admission or tracking.

## Offline tests and provenance

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Lens and PTZ fitting algorithms originate from
`test-tools/ptz-lab/ptz_tools/tools/calibrate_intrinsics.py` and
`fit_ptz_curves.py` in the CI repository (lab provenance: PoC
`demo-room-igk3-ptz`, `f96ec293`). Original Apache-2.0 SPDX headers are retained.
The controlled home approach replaces the legacy fit's unconstrained initial
backlash state. The optimizer uses signed pixel-coordinate residuals rather
than non-smooth point-error magnitudes. No source checkout is required after
copying these tools.
