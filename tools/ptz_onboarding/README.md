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

### Create the camera credential file

Create a new file, for example `local/camera-onvif.json`, in your editor:

```json
{
  "username": "<your camera ONVIF username>",
  "password": "<your camera ONVIF password>"
}
```

Replace the placeholders **locally**, then restrict access:

```sh
chmod 700 local
chmod 600 local/camera-onvif.json
```

Set `"auth": "camera-onvif.json"` inside the `onvif` section of
`local/camera.json`. Both files are in the same directory. This is the
camera's ONVIF account, not a SceneScape login; enable ONVIF in the camera UI
and grant status/absolute-movement access. Use its actual ONVIF port.
Do not paste accounts into chat, command-line flags, screenshots or Git.

SceneScape accounts are separate: `manager_auth` points to the deployed
checkout's `manager/secrets/controller.auth`, and `mqtt.auth` typically
points to `manager/secrets/browser.auth`. Both use `user`/`password` keys
(not ONVIF's `username`/`password`). RTSP accounts are configured separately
in the video pipeline.

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

### Configure the camera stream first

Adding a camera in Manager does **not** create a DLStreamer pipeline.
Configure your deployment's pipeline server with:

- The camera's actual RTSP URI and RTSP account. Obtain the URI for the
  selected ONVIF profile using `GetStreamUri`, or from the camera documentation.
  ONVIF and RTSP accounts can differ.
- The **exact same camera UID** as `camera_uid` in Manager and the tool config.
- Your deployment's SceneScape image/metadata publisher, TLS CA and broker
  connection. The publisher must subscribe to
  `scenescape/cmd/camera/<uid>` and respond to `getcalibrationimage` by
  publishing a JSON message with a base64 `image` and timezone-aware ISO 8601
  `timestamp` (post-decode buffer time, not publication time) on
  `scenescape/image/calibration/camera/<uid>`.
- A stable stream resolution, fixed zoom and a reachable NTP service for
  timestamped image delivery.

Synchronize the runner and timestamp-producing host (or camera when using frame
NTP timestamps). `mqtt.max_clock_skew_s` is the maximum absolute difference
between their clocks in seconds (default `0.1`, finite and non-negative).
Choose a bound that your time synchronization actually guarantees; avoid clock
steps during measurement. After ONVIF arrival and `settle_s`, the tool records
the image-request time. It accepts a frame only if its timestamp **minus this
skew bound** is at or after that request, and the timestamp is no more than
the skew bound ahead of receipt. This is a conservative safety margin, not
permission to accept older frames. Retained/pre-request messages are ignored.
Stale frames are discarded with a diagnostic and another image is requested
while the camera stays stationary, keeping the original freshness boundary.
Retries share the existing 20-second subscription/image timeout. Missing,
invalid or implausibly future timestamps, or failure to obtain a fresh frame,
abort capture/discovery rather than becoming visibility gaps. Fix backlog or
synchronization before retrying; increase settling time if needed.
Captures save `frame_timestamp`.
Post-decode timestamps cannot reveal buffering upstream of the decoder; keep
that buffering bounded and include it in your settling delay.

Verify that its pipeline reports `RUNNING` and Manager shows live video,
then run the tool's `check` command. A plain RTSP preview or successful person
detection is not sufficient: the calibration-image request must work too.
Avoid a second publisher for the same UID. Generated stream configurations
contain RTSP credentials: keep them in a private ignored directory, and grant
read access only to the pipeline container UID. Do not copy them into tool
examples or print unredacted pipeline logs.

The onboarding tools do not create or alter video pipelines automatically.
Keep stream deployment separate from camera measurement and Positioning.

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

### Discover AprilTag-covered positions automatically

You must still choose **safe hardware limits**. Tag visibility cannot tell the
tool which mechanical moves are safe. Advertised ONVIF limits alone are not
permission to sweep the whole head.

1. Run `inspect` to read profile/position/advertised limits without moving.
   Set an explicit `onvif.profile_token` if the device has several PTZ profiles.
2. Choose a well-observed `motion.home`, operator-approved `pan_range` and
   `tilt_range`, home approach directions and positive `approach_offset`.
   Also set settling time, arrival timeout and native-unit tolerance.
   Keep the approach position inside the safe limits.
3. Leave `lens_pan`, `lens_tilt`, `pan_path` and `tilt_path` empty for now.
   Run `check`: it requests a fresh frame and verifies tags at the current
   position, but performs no movement.
4. Reserve the camera, then run bounded discovery:

```sh
.venv/bin/python ptz.py --config local/camera.json inspect
.venv/bin/python ptz.py --config local/camera.json check
# MOVES CAMERA, only after approving the safe limits in camera.json:
.venv/bin/python ptz.py --config local/camera.json discover \
  --output-dir local/coverage-01 --steps 5 --yes
```

Discovery samples a Cartesian grid inside your limits, including exact home
and approach coordinates. `--steps` accepts 3–9 grid points per axis, plus
those extra coordinates; runtime grows with their product. It requires usable
tags at home before probing, records explicit tag-coverage rejections and
returns to approached home. Transport/API failures abort rather than being
silently treated as missing tags.
The current service does not distinguish internal failures from calibration
rejections with structured error codes. Therefore every `status: "error"`
response aborts discovery, even if its message mentions tags. Only the known
`pending` coverage status or a successful response with fewer than six matched
points is treated as a visibility gap. Unknown statuses time out and abort;
error-message text is never used to decide whether movement should continue.

It selects the largest fully observed rectangle with at least three positions
per axis that includes home and the approach coordinates. It writes:

- `coverage.json`: sampled positions, point counts and rejection reasons.
- `camera.discovered.json`: a **new proposed configuration**, containing lens
  grid positions and reversing PTZ paths. Credentials remain file references.

Review these files, then use `camera.discovered.json` as `--config` for
`onboard` and `apply`. The original config and safe travel limits are unchanged.
If floating-point reconstruction would put a generated path endpoint outside
those limits, its offset is moved one representable step toward zero.
Only sampled grid points are checked; visibility between points, image-edge
coverage and lens-fit conditioning are not guaranteed. If no suitable rectangle
exists, discovery fails explicitly. Improve the scene, change the home or refine
the grid **inside** your approved safe limits instead of widening them blindly.

### Optional Docker runner for Compose deployments

When broker/autocalibration are reachable only inside the Compose network, run
the tools on that existing network. This also supplies a consistent Python 3.12
runtime. `.dockerignore` excludes local accounts, generated RTSP configs and
measurements from the image build.

```sh
docker build -t scenescape-ptz-onboarding:local .
docker run --rm --user "$(id -u):$(id -g)" \
  --network <your-existing-compose-network> \
  --mount type=bind,src="$PWD/local",dst=/work \
  --mount type=bind,src=/absolute/path/to/manager/secrets,dst=/run/secrets,readonly \
  scenescape-ptz-onboarding:local --config /work/camera.json check
```

For this layout, set config paths to `/run/secrets/controller.auth`,
`/run/secrets/browser.auth` and `/run/secrets/certs/scenescape-ca.pem`, and keep
ONVIF auth relative to the config. Use the services' certificate DNS names for
URLs/broker host, not container IP addresses. Results belong under `/work`.
Replace `check` with `inspect`, `discover --output-dir /work/coverage-01 --yes`,
or the other documented commands. The local-directory mount is writable for
results; service secrets are read-only.

Newer host Python/OpenSSL versions may reject older demo CAs missing required
extensions. Prefer correctly issued deployment certificates. The provided
runner uses its standard verified TLS behavior; no command disables
certificate or hostname verification. Do not work around certificate errors
with `verify=False` or `--insecure`.

## 3. Check, onboard, apply

```sh
# Read-only: credentials, device capabilities, fresh image and tag visibility.
.venv/bin/python ptz.py --config local/camera.json check

# MOVES camera; fits locally and verifies using a second, fresh PTZ capture.
# Choose a new run directory each time. This does not change Manager.
.venv/bin/python ptz.py --config local/camera.json onboard \
  --output-dir local/run-01 --yes

# STOP: review the saved captures, lens.json, model.json and verification.json.
# Nothing has been imported into Manager by check/onboard.

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

### Review before importing

`onboard` saves each completed capture **before fitting** it. If a later fit
fails, earlier files remain available for inspection and offline retries.
Neither capture, fitting nor verification writes camera calibration to Manager.
Only the separate, explicitly confirmed `apply` command imports the result.

| Saved file                                 | Review                                                                         |
| ------------------------------------------ | ------------------------------------------------------------------------------ |
| `lens-capture.json`, `ptz-capture.json`    | Measured positions, frame timestamps and image/world correspondences           |
| `lens.json`                                | Resolution, fitted intrinsics/distortion, fit error and uncertainty acceptance |
| `model.json`                               | Home pose, axis curves, backlash, provenance and pre-run camera settings       |
| `verify-capture.json`, `verification.json` | Independent observations, model hash, point count, RMS and maximum point error |

The configured `max_rms_px` gates **held-out RMS**, not the maximum individual
point error; inspect both before import. A passing run validates its sampled
region at the measured zoom, not the full advertised mechanical range.
Backend pose acceptance during raw collection and final held-out model
acceptance are separate gates. Raising a collection gate for an isolated
bootstrap experiment does not justify raising the final verification limit,
ignoring backend errors or importing an unverified result.

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
