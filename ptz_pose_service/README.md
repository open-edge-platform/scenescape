# PTZ Pose Service

Keeps a Scenescape camera's stored pose in sync with a physical ONVIF PTZ
camera's live pan/tilt position, so a camera that is panned or tilted after
calibration stays correctly placed in the scene.

**Status**: experimental — pan and tilt only, no zoom; docker logs are the
only feedback mechanism for now.

New to this service? Start with [Setting up a new camera](#setting-up-a-new-camera),
which walks through measuring the two things accuracy depends on.

## What it does

1. On startup, for each camera in the config file:
   - resolves an ONVIF PTZ media profile (auto-detected if not pinned),
   - applies any `intrinsics`/`distortion`/`resolution` declared for the
     camera, so a measured lens calibration survives a database reset,
   - resolves the degrees-per-ONVIF-unit scale factors for pan and tilt
     (see `pan_scale`/`tilt_scale` and `pan_degrees`/`tilt_degrees` below),
   - fetches the camera's calibrated pose from Scenescape via the REST
     API (this is the pose set during scene calibration, at whatever pan/tilt
     the camera physically had at that time — the "home" position),
   - records the ONVIF pan/tilt reading at that home position, either from
     the config file (`home_pan`/`home_tilt`) or, if not given, from the
     camera's current status at startup (i.e. it assumes the camera is still
     at its calibrated position when the service starts).
2. Polls each camera's PTZ status (`GetStatus`) at `--poll-hz` (default 5×/s).
3. Converts the reported pan/tilt into real degrees (via `pan_scale`/
   `tilt_scale`, or a `pan_curve`/`tilt_curve` for a non-uniform head), and
   tracks each axis through its `*_backlash_deg` deadband so the angle used
   is where the camera physically is rather than where it reports being.
4. Rotates the home pose by that delta: pan turns the head about the **world
   vertical axis** and tilt pivots the camera about its **own horizontal
   axis**, composed as `R_new = Rz(Δpan) · R_home · Rx(Δtilt)`. When the
   change exceeds `--min-delta-deg` the new pose is persisted via
   `updateCamera()` and published for the UI to redraw.
5. For cameras calibrated from 3D-2D point correspondences (the AprilTag/auto
   flow), the stored world points are reprojected to their new pixel
   positions instead of overwriting the pose as raw Euler angles. That keeps
   the camera on its native transform type so the 2D calibration view still
   has points to draw, and Scenescape re-derives the same pose from them. If
   a pose would put those points behind the camera the update is skipped
   rather than written as Euler angles, which would discard them.

> **Why matrix composition rather than adding to the Euler angles?**
> Scenescape stores `rotation` as *intrinsic* Euler XYZ, whose third
> component rotates about an already-rotated local axis — not the world
> vertical. Measured against ground-truth poses, a pure pan move changes all
> three components (e.g. roll −14°, pitch +34°, yaw +20°), so adding the pan
> delta to yaw alone gave ~18° of error versus ~1.8° for the composed form.

See [pose_math.py](src/pose_math.py) for the exact math and its documented
assumptions and limitations. Notably, the camera is assumed to rotate about
its own centre, so `translation` is never changed; real heads have a small
lever arm between the rotation axes and the lens, which this ignores (fitting
one on the development camera improved reprojection by only 0.13 px and
produced a physically implausible value, so it was left out).

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
      "pan_degrees": null,
      "tilt_degrees": null,
      "pan_scale": -154.15,
      "tilt_scale": 56.49,
      "tilt_curve": [0.0, 42.05, 9.41],
      "pan_backlash_deg": 0.0,
      "tilt_backlash_deg": 2.83,
      "invert_pan": false,
      "invert_tilt": false,
      "pose_update_mode": "ptz_delta",
      "resolution": [1280, 720],
      "intrinsics": { "fx": 1066.3453, "fy": 1066.3453, "cx": 640.0, "cy": 360.0 },
      "distortion": { "k1": -0.371571, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0 }
    }
  ]
}
```

The values above are the ones measured for the camera used during development.
They are **specific to that camera** — see
[Setting up a new camera](#setting-up-a-new-camera) for how to measure your own.

- `profile_token`: optional; auto-detected (first PTZ-capable profile) if omitted.
- `home_pan`/`home_tilt`: optional; if omitted, the camera's pan/tilt at
  service startup is used as home. Set these explicitly if the service may
  restart while the camera isn't at its calibrated position.
- `pan_scale`/`tilt_scale`: degrees of real rotation per ONVIF position unit.
  **These are the values to set**, and the reliable way to obtain them is to
  measure them — see [Measuring pan/tilt scale factors](#measuring-pantilt-scale-factors).
  Datasheet sweep figures are often wrong: on the development camera the
  documented 332° pan measured 308°, and a negative sign was needed because
  the head pans opposite to the assumed convention.
- `pan_curve`/`tilt_curve`: optional polynomial replacing the constant scale
  for a head whose travel isn't uniform. Coefficients run in increasing power,
  so `[0.0, 42.05, 9.41]` means `42.05*t + 9.41*t²` degrees at position `t`;
  only differences matter, so any constant term cancels. Needed when the
  measured scale varies materially across the travel (the development camera
  ranged from 52 to 59 °/unit on tilt).
- `pan_backlash_deg`/`tilt_backlash_deg`: mechanical slack in degrees, which
  makes the same reported position mean different physical angles depending on
  the direction of approach. See [Measuring backlash](#measuring-backlash).
- `pan_degrees`/`tilt_degrees`: fallback if no explicit scale is given — the
  camera's physical sweep in degrees, divided by the ONVIF position range the
  camera advertises (`AbsolutePanTiltPositionSpace` via `GetNodes`, assumed
  `[-1, 1]` if it advertises nothing usable). Convenient, but only as accurate
  as the datasheet.
- `invert_pan`/`invert_tilt`: per-camera overrides of `--invert-pan`/`--invert-tilt`.
  Equivalent to negating the corresponding scale.
- `pose_update_mode`: per-camera override of `--pose-update-mode` — which
  mechanism keeps this camera's pose in sync (see below).
- `resolution`/`intrinsics`/`distortion`: optional lens parameters, applied to
  Scenescape at startup if they differ from what is stored. Declaring them
  here means a measured calibration is reapplied automatically instead of
  having to be re-entered in the UI after a database reset. See
  [Calibrating intrinsics and lens distortion](#calibrating-intrinsics-and-lens-distortion).

## Pose update modes

How a camera's Scenescape pose is kept in sync with its live PTZ position is
selected with `--pose-update-mode` (or per camera via `pose_update_mode`):

### `ptz_delta` (default)

Rotates the camera's calibrated "home" pose by its pan/tilt delta. Needs no
video feed, no AprilTags and no re-calibration — but it does need accurate
`pan_scale`/`tilt_scale`, since most ONVIF cameras report position in a
normalized `[-1, 1]` space rather than real degrees. See
[Measuring pan/tilt scale factors](#measuring-pantilt-scale-factors); if no
usable scale can be resolved the service logs a warning and falls back to the
`--pan-scale`/`--tilt-scale` defaults, which will not be accurate.

Assumes the camera rotates about its own centre, so `translation` is left
untouched. Real pan/tilt heads have a small lever arm between the rotation
axes and the lens, which this ignores.

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

## Setting up a new camera

Accuracy rests on three properties of the hardware: the camera's **lens
parameters**, its **pan/tilt scale factors**, and any **mechanical backlash**
in the head. All three are commonly wrong or absent in datasheets, all three
can be measured directly with the tools in [tools/](tools/), and the scale and
backlash measurements need no AprilTags or scene calibration at all — so they
apply equally to manual, marker-based and markerless deployments.

Recommended order (each step feeds the next):

1. [Calibrate intrinsics and lens distortion](#calibrating-intrinsics-and-lens-distortion)
2. [Measure pan/tilt scale factors](#measuring-pantilt-scale-factors)
3. [Measure backlash](#measuring-backlash)
4. Write the results into `config/cameras.json`, rebuild, restart
5. Calibrate the camera's pose once in the Scenescape UI
6. Restart `ptz-pose` so it picks that pose up as its home reference

Steps 1-3 are one-off per camera model; their output lives in the config file
and is reapplied on every start.

> **Stop the service while measuring.** `docker compose stop ptz-pose` first.
> The tools drive the camera, and a running service would track those moves
> from a baseline that no longer matches, writing poses into the database as
> it goes.

All tools take `--help`. They run inside containers because the dependencies
are split: `ptz-pose` has the ONVIF/MQTT plumbing, `autocalibration` has
OpenCV. Copy them in first:

```bash
cd <repo root>
docker compose exec ptz-pose rm -rf /tmp/tools
docker compose exec autocalibration rm -rf /tmp/tools
docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
docker cp ptz_pose_service/tools scenescape-autocalibration-1:/tmp/tools
```

> Remove the old directory first — `docker cp` nests the source inside an
> existing directory of the same name rather than replacing it, so a stale
> copy will silently keep running.

### Calibrating intrinsics and lens distortion

Scenescape defaults a new camera to a rough guess (a single FOV value). If
that is far from reality, or the lens has noticeable barrel distortion,
calibration points will fit well near the image centre and drift badly toward
the edges.

```bash
# 1. Sweep a grid of pan/tilt positions, matching the scene's AprilTags in each
docker compose exec ptz-pose python3 /tmp/tools/collect_calibration_views.py \
    --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

# 2. Fit intrinsics + distortion over all views at once
docker cp scenescape-ptz-pose-1:/tmp/calibration_views.json /tmp/
docker cp /tmp/calibration_views.json scenescape-autocalibration-1:/tmp/
docker compose exec autocalibration python3 /tmp/tools/calibrate_intrinsics.py \
    --camera-uid atag-ptzcam3
```

The tool prints before/after reprojection error and a JSON block to paste into
`config/cameras.json` (or use `--apply` to write it straight to Scenescape).

It deliberately fits a **constrained** model by default — square pixels,
principal point pinned to the image centre, one radial term — and drops views
whose reprojection error marks them as mis-detections. A tag sweep yields few
distinct world points, and those points carry the scene mesh's own error, so
an unconstrained fit will happily trade physical plausibility for a lower
residual: on the development camera it produced `fx`/`fy` differing by 3% with
a *worse* maximum error. Use `--fit-principal-point`, `--fit-aspect-ratio`,
`--fit-k2`, `--fit-k3` or `--fit-tangential` only with dense, well-spread
coverage.

This step does need AprilTags, since it needs known 3D points. For a camera in
a scene without them, calibrate the lens conventionally (e.g. a checkerboard
with OpenCV) and put the result in `config/cameras.json` directly.

<details>
<summary>What this looked like on the development camera</summary>

The datasheet gave `fx=710.79, fy=848.11` — internally inconsistent, since
`fx ≠ fy` by 20% implies non-square pixels. Measured over 15 views / 122
points:

| | fx / fy | k1 | mean error | max error |
|---|---|---|---|---|
| datasheet, no distortion | 710.8 / 848.1 | – | 25.67 px | 155.3 px |
| measured | 1066.3 / 1066.3 | −0.3716 | **3.18 px** | **8.0 px** |

An 87% reduction in mean error, and the strong barrel distortion (`k1 = −0.37`)
explained why edge points had been drifting.
</details>

### Measuring pan/tilt scale factors

Most ONVIF cameras report pan/tilt in a normalized `[-1, 1]` space, so the
service needs to know how many degrees one unit represents. This is measured
from image content alone — no markers, no scene calibration:

```bash
# 1. Sweep the full travel, saving a frame at each position
docker compose exec ptz-pose python3 /tmp/tools/capture_ptz_sweep.py \
    --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020 \
    --pan-range -0.9 0.9 --pan-step 0.05 --tilt-range 0.1 0.9 --tilt-step 0.05

# 2. Recover how far the camera actually rotated between consecutive frames
docker cp scenescape-ptz-pose-1:/tmp/ptz_sweep /tmp/ptz_sweep
docker cp /tmp/ptz_sweep scenescape-autocalibration-1:/tmp/ptz_sweep
docker compose exec autocalibration python3 /tmp/tools/measure_ptz_scale.py \
    --camera-uid atag-ptzcam3
```

**How it works.** For each consecutive pair of frames, SIFT finds distinctive
keypoints — corner- and blob-like spots, described in a way that survives
rotation, scale and lighting changes — and matches them between the two
images. A camera that only rotates transforms the whole scene by
`H = K·R·K⁻¹` regardless of depth, so fitting that homography and computing
`R = K⁻¹·H·K` recovers the rotation. Its angle divided by the ONVIF position
change gives degrees per unit. Accurate intrinsics matter here, which is why
lens calibration comes first.

Each step is measured independently and screened on match count, rotation-axis
consistency and magnitude, so one bad frame (a blank wall, too little overlap)
costs only the steps touching it. Use `--verbose` to see every rejection.

The report also states how much the scale varies across the travel — if that
is small, a single linear scale is justified; if not, the measured value is
only an approximation. Sweep the widest range the scene allows: a narrow
sweep can give a confidently wrong answer.

The sign is *not* taken from the measurement — it depends on the stored pose
convention. If the pose rotates the wrong way after a move, negate the scale
(or set `invert_pan`/`invert_tilt`).

<details>
<summary>What this looked like on the development camera</summary>

| axis | measured | implied full travel | datasheet |
|---|---|---|---|
| pan | 154.15 °/unit | 308° | 332° |
| tilt | 59.17 °/unit | 118° | 120° ✅ |

Both axes varied only ~9% across the travel, so a single linear scale was
justified. Two independent checks: pan agreed to 0.2% with a separate
AprilTag-based fit, and the recovered pan axis in camera coordinates
(`[0.00, −0.908, −0.419]`, i.e. 24.8° below horizontal) matched the camera's
physical downward tilt.

A first attempt over a much narrower sweep gave 44.9 °/unit for tilt — one bad
step in a short sequence was enough to skew it by 25%. Hence sweeping wide.
</details>

#### If the scale isn't constant

A head whose travel isn't uniform needs `pan_curve`/`tilt_curve` instead of a
single scale. The symptom is a pose that tracks well near the calibrated
position but drifts progressively toward one end of the travel — and, because
a mid-range fit splits the difference, drifts the *opposite* way at the other
end.

`measure_ptz_scale.py` reports the variation across the travel; if it is more
than ~15% a curve is worth fitting. Obtain one by fitting a polynomial to the
per-step scales the tool prints, then set e.g.
`"tilt_curve": [0.0, 42.05, 9.41]` for `42.05*t + 9.41*t²`.

On the development camera the tilt axis ran from 53.8 °/unit near the middle
of its range to 60.6 °/unit near the top. Fitting the curve reduced mean
reprojection error from 4.43 px to 3.93 px, with the gain concentrated at the
extremes (−33% at one end, −15% at the other) — exactly where a constant
scale is worst.

### Measuring backlash

Gear slack means the same reported position can correspond to different
physical angles depending on which way the head arrived. The position encoder
sits on the motor side of the gearbox, so on a direction reversal the encoder
moves while the camera does not, until the slack is taken up.

The symptom is direction-dependent error: the pose tracks correctly while
moving one way and is consistently offset when moving back.

```bash
# 1. Arrive at several positions from each direction, saving a frame at each
docker compose exec ptz-pose python3 /tmp/tools/capture_ptz_backlash.py \
    --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

# 2. Measure the rotation between the two arrivals at each position
docker cp scenescape-ptz-pose-1:/tmp/ptz_backlash /tmp/ptz_backlash
docker cp /tmp/ptz_backlash scenescape-autocalibration-1:/tmp/ptz_backlash
docker compose exec autocalibration python3 /tmp/tools/measure_ptz_backlash.py \
    --camera-uid atag-ptzcam3
```

Both arrivals report the *same* ONVIF position, so any rotation measured
between their frames is slack. The same homography method as the scale
measurement is used, which is what makes this feasible: the difference is a
couple of degrees, well below what auto-calibration can resolve reliably.

Put the result in `tilt_backlash_deg`/`pan_backlash_deg`. The service then
models each axis as a deadband, tracking where the camera physically is rather
than where it reports being, and only rotating the pose once the slack has
been taken up.

<details>
<summary>What this looked like on the development camera</summary>

| axis | backlash | spread across positions |
|---|---|---|
| tilt | **2.83°** | 0.68° over 4 positions |
| pan | 0.37° (noise) | — |

Confirmed independently: arriving at reported tilt `0.800733` from below gave
rotation `[-115.232, 37.048, 14.352]`, and from above `[-111.087, 36.216,
12.266]` — the same reported position, 4.1° apart physically. Pan had no
measurable backlash, which is why pan tracking always looked correct while
tilt did not.

Modelling it halved the vertical reprojection error (47.5 px → 24.4 px).
</details>

### Rebooting a camera

Some cameras need an occasional reboot (for example after RTSP sessions are
left stale by abrupt restarts):

```bash
docker compose exec ptz-pose python3 /tmp/tools/onvif_reboot.py 192.168.0.91:2020
```

Credentials are prompted for, never passed as arguments, and read from
`ONVIF_ADMIN_USERNAME`/`ONVIF_ADMIN_PASSWORD` rather than the service's own
`ONVIF_USERNAME`/`ONVIF_PASSWORD` — rebooting needs an administrator account,
while the service only needs a PTZ-capable one. Run it inside the container:
the pinned `onvif-zeep` there is known to work with these cameras, whereas
newer `zeep` releases can fail the initial `GetCapabilities` call outright.

### Tool reference

| Tool | Runs in | Purpose |
|---|---|---|
| [`collect_calibration_views.py`](tools/collect_calibration_views.py) | `ptz-pose` | Sweep pan/tilt, collecting AprilTag 2D/3D correspondences per view |
| [`calibrate_intrinsics.py`](tools/calibrate_intrinsics.py) | `autocalibration` | Fit intrinsics + distortion from those views |
| [`capture_ptz_sweep.py`](tools/capture_ptz_sweep.py) | `ptz-pose` | Sweep pan/tilt, saving a frame at each position (no markers needed) |
| [`measure_ptz_scale.py`](tools/measure_ptz_scale.py) | `autocalibration` | Recover degrees-per-ONVIF-unit from those frames |
| [`capture_ptz_backlash.py`](tools/capture_ptz_backlash.py) | `ptz-pose` | Arrive at positions from both directions, saving frame pairs |
| [`measure_ptz_backlash.py`](tools/measure_ptz_backlash.py) | `autocalibration` | Measure mechanical slack from those pairs |
| [`onvif_reboot.py`](tools/onvif_reboot.py) | `ptz-pose` | Reboot a camera over ONVIF |

## Live updates in the calibration UI

A calibration page that is already open would otherwise keep showing the pose
it loaded with. The service publishes each update on the camera's pose topic
(`scenescape/autocalibration/camera/pose/<camera_uid>`), which the calibration
page subscribes to and redraws from, so points track the camera without a
reload.

This goes over MQTT — the browser is already connected to the broker — rather
than through the autocalibration service, so pose tracking stays independent
of it. Publishing is best-effort: if the broker is unreachable the live
redraw is lost but tracking continues unaffected. Disable with
`--no-notify-ui`.

Because the browser's MQTT connection is user-toggleable, live updates stop if
it is disconnected; the stored pose is still correct and appears on reload.

## Re-calibrating while the service runs

The service caches the calibrated pose as its home reference at startup. If a
camera is re-calibrated afterwards — from the UI, or by any other client — it
notices within `--rebaseline-check-s` (default 2s) and adopts the new pose,
together with the pan/tilt the camera is at that moment, as its new home.

Detection compares the *stored correspondences* against the ones this service
last wrote, not the camera's rotation: Scenescape re-derives rotation from
written points via `solvePnP`, and that derived value drifts slightly from the
one used to generate them. Comparing rotations would therefore mistake the
service's own updates for external ones, re-baseline onto a mid-move pose, and
compound from there.

## Verifying it works

After a move, check that:

- the service logged a pose update (`docker logs scenescape-ptz-pose-1`),
- the camera's calibration page shows its points **on** the AprilTags — reload
  with a hard refresh, as the page is otherwise served from browser cache,
- translation is unchanged and above the floor (a fixed mount doesn't move),
- the 3D view's camera frustum points the new way. The 3D calibration points
  themselves are world points on fixed tags, so they are *expected* not to
  move — only the 2D view shows the reprojection.

To compare the delta-tracked pose against an independent measurement, run
auto-calibration manually from the UI and compare the resulting rotation.
Bear in mind a single auto-calibration run is not exact ground truth: on the
development camera repeated runs from the same position varied by up to
`[0.34, 0.19, 0.21] m` in translation and a few degrees in rotation. For
anything finer than that, use the homography-based tools instead.

### Diagnosing a pose that tracks badly

| Symptom | Likely cause |
|---|---|
| Error grows steadily with distance from the calibrated position | `pan_scale`/`tilt_scale` wrong — [re-measure](#measuring-pantilt-scale-factors) |
| Tracks one direction well, offset the other way | Backlash — [measure it](#measuring-backlash) |
| Good near the middle of travel, drifts at both ends in opposite directions | Non-uniform travel — [fit a curve](#if-the-scale-isnt-constant) |
| Pose rotates the wrong way entirely | Sign — negate the scale or set `invert_pan`/`invert_tilt` |
| Points fit near the image centre but drift at the edges | Lens distortion — [calibrate intrinsics](#calibrating-intrinsics-and-lens-distortion) |
| Points vanish from the 2D view | A pose put them behind the camera, or the camera was left on the `euler` transform type; re-calibrate once from the UI |
| Points stop updating live but the pose is right on reload | Browser MQTT disconnected (see [Live updates](#live-updates-in-the-calibration-ui)) |

## Environment variables / credentials

- `ONVIF_USERNAME` / `ONVIF_PASSWORD`: credentials used to authenticate to
  every configured ONVIF camera (default for `--onvif-username`/`--onvif-password`).
- `ONVIF_ADMIN_USERNAME` / `ONVIF_ADMIN_PASSWORD`: used only by
  `onvif_reboot.py`, kept separate because rebooting needs an administrator
  account while the service itself only needs a PTZ-capable one.

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
| `--rebaseline-check-s` | `2.0` | how often to look for an externally applied re-calibration (0 disables) |
| `--rebaseline-tolerance-deg` | `0.5` | how far the stored pose must differ before it counts as external |
| `--no-notify-ui` | off | don't publish pose updates for open calibration pages |
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
