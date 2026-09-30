# PTZ Pose Service

Keeps a Scenescape camera's stored pose in sync with a physical ONVIF PTZ
camera's live pan/tilt position, so a camera that is panned or tilted after
calibration stays correctly placed in the scene.

**Status**: experimental — pan and tilt only, no zoom; docker logs are the
only feedback mechanism for now.

New to this service? Start with [Setting up a new camera](#setting-up-a-new-camera):
[`tools/tune_ptz_camera.sh`](tools/tune_ptz_camera.sh) measures and configures a
new PTZ camera in one run.

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
   vertical axis** (or the measured `pan_axis`, for a mount that isn't level)
   and tilt pivots the camera about its **own horizontal axis**, composed as
   `R_new = R_pan(Δpan) · R_home · Rx(Δtilt)`. Once the head has been still
   for `--pose-settle-s` (default 0.5s) and the change exceeds
   `--min-delta-deg`, the new pose is persisted via
   `updateCamera()` and published for the UI to redraw.
5. For cameras calibrated from 3D-2D point correspondences (the AprilTag/auto
   flow), the stored world points are reprojected to their new pixel
   positions instead of overwriting the pose as raw Euler angles. That keeps
   the camera on its native transform type so the 2D calibration view still
   has points to draw, and Scenescape re-derives the same pose from them.
   Only points that are still in frame are written. With barrel distortion
   the lens model folds back past a certain radius, so a point well outside
   the frame would otherwise be projected *into* it at a wrong pixel and
   corrupt the pose. If fewer than 6 points stay visible (too few for
   Scenescape's `solvePnP`), the rotation is written directly as a Euler pose
   instead, which clears the 2D points from the calibration view. The service
   keeps the world points in memory and switches back to point
   correspondences as soon as enough are in view again.

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
      "pan_curve": [0.0, -159.23, 20.5],
      "tilt_curve": [0.0, 62.65, -4.4],
      "pan_axis": [0.0637, 0.1063, 0.9923],
      "pan_backlash_deg": 0.75,
      "tilt_backlash_deg": 2.63,
      "pose_settle_s": 0.5,
      "pan_home_approach": "decreasing",
      "tilt_home_approach": "increasing",
      "invert_pan": false,
      "invert_tilt": false,
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
- `pan_axis`: optional direction of the head's pan axis in **world**
  coordinates (`[x, y, z]`, normalised by the service). Defaults to world
  vertical `[0, 0, 1]`. Set it when the mount isn't level: pan then turns
  about a leaning axis and the error grows with the pan angle, which no scale
  or curve can fix. Measure it with `fit_ptz_curves.py` (see
  [Pan axis not vertical](#pan-axis-not-vertical)). It is fixed to the mount,
  so it stays valid across re-calibrations.
- `pan_backlash_deg`/`tilt_backlash_deg`: mechanical slack in degrees, which
  makes the same reported position mean different physical angles depending on
  the direction of approach. See [Measuring backlash](#measuring-backlash).
- `pose_settle_s`: optional per-camera override of `--pose-settle-s`.
  Holds REST/MQTT pose updates until the pan and tilt have stopped changing
  for this many seconds. Backlash tracking still runs on every poll. Set to
  `0` to update during movement instead.
- `pan_home_approach`/`tilt_home_approach`: `"increasing"` or `"decreasing"`
  — which way the ONVIF position was moving when the home pose was
  calibrated. Needed only at startup: with backlash it decides which side of
  the slack the camera sits on. If omitted, the service assumes the middle of
  that slack, which leaves up to half the backlash as error in *both* directions.
- `pan_degrees`/`tilt_degrees`: fallback if no explicit scale is given — the
  camera's physical sweep in degrees, divided by the ONVIF position range the
  camera advertises (`AbsolutePanTiltPositionSpace` via `GetNodes`, assumed
  `[-1, 1]` if it advertises nothing usable). Convenient, but only as accurate
  as the datasheet.
- `invert_pan`/`invert_tilt`: per-camera overrides of `--invert-pan`/`--invert-tilt`.
  Equivalent to negating the corresponding scale.
- `resolution`/`intrinsics`/`distortion`: optional lens parameters, applied to
  Scenescape at startup if they differ from what is stored. Declaring them
  here means a measured calibration is reapplied automatically instead of
  having to be re-entered in the UI after a database reset. See
  [Calibrating intrinsics and lens distortion](#calibrating-intrinsics-and-lens-distortion).

**Static (non-PTZ) cameras** can be listed with only `scene_camera_uid` and
the lens fields, without `onvif_host`. The service applies their lens settings
at startup and does not track them. `"track": false` does the same for a PTZ
camera, pausing its tracking (the tuning script uses it while tools drive the
camera):

```json
{
  "scene_camera_uid": "atag-ptzcam1",
  "resolution": [1920, 1080],
  "intrinsics": { "fx": 1100.6252, "fy": 1100.6252, "cx": 960.0, "cy": 540.0 },
  "distortion": { "k1": -0.207929, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0 }
}
```

## How poses are kept in sync

The service rotates the camera's calibrated "home" pose by its pan/tilt delta.
It needs no video feed, no AprilTags and no re-calibration after a move, but it
does need accurate `pan_scale`/`tilt_scale`, since most ONVIF cameras report
position in a normalized `[-1, 1]` space rather than real degrees. See
[Measuring pan/tilt scale factors](#measuring-pantilt-scale-factors); if no
usable scale can be resolved the service logs a warning and falls back to the
`--pan-scale`/`--tilt-scale` defaults, which will not be accurate.

Assumes the camera rotates about its own centre, so `translation` is left
untouched. Real pan/tilt heads have a small lever arm between the rotation
axes and the lens, which this ignores.

The service never re-runs auto-calibration itself. Calibrate from the camera's
calibration page in the Scenescape UI whenever needed; the service adopts the
result as its new home (see
[Re-calibrating while the service runs](#re-calibrating-while-the-service-runs)).

## Setting up a new camera

### Quick start: tune with one script

[`tools/tune_ptz_camera.sh`](tools/tune_ptz_camera.sh) runs the whole
procedure below unattended and writes the results into `config/cameras.json`.
Run it on the host from the repo root:

```bash
ptz_pose_service/tools/tune_ptz_camera.sh \
    --camera-uid atag-ptzcam4 --onvif-host 192.168.0.94 --onvif-port 2020
```

Before running it:

- the camera is added in Scenescape and streams through the pipeline server,
- it points at a view with **at least 6 AprilTags** that stay visible within
  about ±0.2 pan / +0.1 −0.3 tilt of it (this is the start position),
- the `ptz-pose` and `autocalibration` containers are running,
- with a proxy configured, the camera's IP is in the `ptz-pose` container's
  `no_proxy`/`NO_PROXY` (add it in `docker-compose.yml` and recreate the
  container with `ONVIF_USERNAME`/`ONVIF_PASSWORD` exported). The script checks
  this and stops with instructions if it's missing.

It then runs, in about 20 minutes:

| phase | what | tools |
|---|---|---|
| preflight | ONVIF reachable, camera in Scenescape, ≥6 tags matched; backs up the config | `ptz_goto.py`, `save_fresh_calibration.py --dry-run` |
| 1. lens | AprilTag sweep around the start; fits and applies intrinsics + distortion | `collect_calibration_views.py`, `calibrate_intrinsics.py` |
| 2. scale | texture sweep over the travel; starting pan/tilt scale | `capture_ptz_sweep.py`, `measure_ptz_scale.py` |
| 3. model ×2 | fresh home, accuracy measurement, fit of curves, pan axis, backlash and signs | `measure_reprojection_accuracy.py`, `fit_ptz_curves.py` |
| 4. verify | fresh home and a final measurement with the applied values | same |

While phases 1-2 drive the camera, its tracking is paused with `track: false`.
Before every measurement the camera is parked at its start position from a
known direction (pan decreasing, tilt increasing, matching the configured
`*_home_approach`), a fresh auto-calibration is saved as its trusted home, and
the service is restarted. The fit drops stops whose tags were mis-matched,
and the script falls back to a constant scale for any axis whose curve
wouldn't extrapolate safely.

It ends with a summary of the error per stage, the best achievable error, and
the final config entry. All measurements and the config backup are kept in
`/tmp/ptz_tune_<camera>_<time>/`. If it fails or is interrupted, the config is
restored and the service restarted.

Useful options (`--help` lists all): `--skip-lens`/`--skip-scale` to keep
existing values, `--rounds N`, `--pan-path`/`--tilt-path` if tags leave the
view on the default measurement path, `--scale-pan-range`/`--scale-tilt-range`
to limit the texture sweep, and `--yes` to skip the confirmation.

The sections below explain each step, for running them by hand or
investigating a result.

### The steps in detail

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
7. [Measure tracking accuracy and fit the head model](#measuring-tracking-accuracy-and-fitting-the-head-model)
   (`pan_curve`, `tilt_curve`, `pan_axis`).
   This step runs *with* the service, re-calibrates, and is repeated until
   the numbers are satisfactory.

Steps 1-3 are one-off per camera model; their output lives in the config file
and is reapplied on every start.

> **Stop the service while measuring** (steps 1-3). Run `docker compose stop ptz-pose` first.
> The tools drive the camera, and a running service would track those moves
> from a baseline that no longer matches, writing poses into the database as
> it goes. Step 7 is the exception: it measures the running service.

All tools take `--help`. They run inside containers because the dependencies
are split: `ptz-pose` has the ONVIF/MQTT plumbing, `autocalibration` has
OpenCV. Copy them in first:

```bash
cd <repo root>
docker compose exec -u root ptz-pose rm -rf /tmp/tools
docker compose exec -u root autocalibration rm -rf /tmp/tools
docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
docker cp ptz_pose_service/tools scenescape-autocalibration-1:/tmp/tools
```

> Remove the old directory first. `docker cp` nests the source inside an
> existing directory of the same name rather than replacing it, so a stale
> copy will silently keep running. The `-u root` is needed because the copied
> files keep the host user's uid, which the container user can't delete.
> Check with `docker compose exec ptz-pose ls /tmp/tools`: there must be no
> nested `tools/`.

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

#### Static (non-PTZ) cameras

The same two tools work for a fixed camera. Omit `--onvif-host` and the
collector grabs several frames of the one view instead of sweeping:

```bash
docker compose exec ptz-pose python3 /tmp/tools/collect_calibration_views.py \
    --camera-uid atag-ptzcam1 --output /tmp/views_atag-ptzcam1.json

docker cp scenescape-ptz-pose-1:/tmp/views_atag-ptzcam1.json /tmp/
docker cp /tmp/views_atag-ptzcam1.json scenescape-autocalibration-1:/tmp/
docker compose exec autocalibration python3 /tmp/tools/calibrate_intrinsics.py \
    --camera-uid atag-ptzcam1 --input /tmp/views_atag-ptzcam1.json
```

Repeated frames only average out detection jitter. The fit relies on the tags
in that one view spreading across the frame and in depth, so check the
`uncertainty` line: the tool warns when focal length or `k1` is poorly
constrained. Its sigmas assume independent views, so with repeated frames
treat them as roughly 2× optimistic.

Put the result in a [static entry](#config-file---config-default-appconfigcamerasjson)
in `config/cameras.json` and restart `ptz-pose`. Scenescape re-derives the
camera's pose from its stored calibration points with the new lens model, so
no re-calibration is required, although re-running auto-calibration afterwards
does no harm.

The collector records the real frame size from the camera's images, and the
fit uses that instead of the stored `resolution`. A stored resolution that
doesn't match the stream is common and silently wrong: the principal point
then lands outside the image and every pose is solved against a broken model.

<details>
<summary>What this looked like on the two static cameras</summary>

Both were stored as `resolution: [640, 480]` with the default `fx=570,
cx=960, cy=540`, while actually streaming 1920×1080. Five frames each:

| camera | tags | fitted fx | k1 | stored pose error before | after |
|---|---|---|---|---|---|
| `atag-ptzcam1` | 12 | 1100.6 ± 11.5 | −0.208 ± 0.006 | 54.8 / 90.6 px | **7.1 / 11.0 px** |
| `atag-ptzcam2` | 11 | 1126.1 ± 10.0 | −0.208 ± 0.003 | 84.4 / 151.4 px | **5.5 / 11.4 px** |

The two independently fitted lenses agree to within about 2%, as expected
for the same camera model. The re-derived poses moved by 1.2–1.6 m, so the
wrong intrinsics had also been misplacing the cameras in the scene.
</details>

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
than ~15% a curve is worth fitting. The recommended way to get one is
`fit_ptz_curves.py`. It fits both `pan_curve` and `tilt_curve` in one step,
directly against detected AprilTags (see
[Measuring tracking accuracy](#measuring-tracking-accuracy-and-fitting-the-head-model)).
Curves are polynomials in the ONVIF position, e.g.
`"tilt_curve": [0.0, 42.05, 9.41]` means `42.05*t + 9.41*t²`.

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

The model also needs to know which side of the slack the camera was on when
it was calibrated. If the camera is re-calibrated while the service is
running, the service already knows this from tracking it. At startup it does
not, so set `tilt_home_approach`/`pan_home_approach`, or re-calibrate once
after moving the camera while the service runs.

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

### Measuring tracking accuracy and fitting the head model

This checks the final result: how far the pose the service *stores* is from
where the AprilTags actually are in the frame. The same measurement is then
used to fit `pan_curve`, `tilt_curve` and `pan_axis` together in one step.

The measurement tool drives the camera through a pan path and then a tilt path
of offsets from its current position. The defaults are pan ±0.2 (≈ ±32°) and
tilt +0.1 / −0.3 (≈ +6° / −16°), and every stop is visited from both
directions, so backlash shows up. At each stop it waits for the service to
write the pose, has autocalibration detect the tags, and projects their world
points through the stored pose. The camera's config entry is saved with the
results, so the fit knows which curves, pan axis, backlash and home approach
were in use.

Unlike steps 1-3 it needs `ptz-pose` **running**:

```bash
# 0. Re-calibrate the camera from the Scenescape UI (service running).
#    Click "Save camera" afterwards; the service then logs
#    "new calibration saved in Scenescape; adopted as the trusted home".
#    Close the calibration page afterwards so it doesn't save over the test.

# 1. Measure (about 4 minutes; the camera returns to its start position)
docker compose exec ptz-pose python3 /tmp/tools/measure_reprojection_accuracy.py \
    --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

# 2. Fit pan_curve, tilt_curve and pan_axis against the measured tags
docker cp scenescape-ptz-pose-1:/tmp/reprojection_accuracy.json /tmp/
docker cp /tmp/reprojection_accuracy.json scenescape-autocalibration-1:/tmp/
docker compose exec autocalibration python3 /tmp/tools/fit_ptz_curves.py --fit-backlash
```

Widen or narrow the paths with `--pan-path`/`--tilt-path` (offsets, visited
in order) to cover the range the camera is used over while keeping tags in
view. Stops where no tags are detected are still recorded, because the move
matters for backlash. End the tilt path with an upward move into the start
position (as the default does) so `tilt_home_approach: "increasing"` stays
true after a restart.

Step 1 prints mean/max pixel error per stop and per axis. The error at the
start position is the floor, set by tag detection and the scene mesh (~3 px
on the development camera).

Step 2 replays the service's exact model, `R_pan(Δpan) · R_start · Rx(Δtilt)`,
with each axis tracked through its backlash deadband along the measured path.
By default the pan axis is fitted too (`--no-fit-pan-axis` keeps the
configured one); the first line reports how far it leans from vertical.
With `--fit-backlash` it also fits `pan_backlash_deg`/`tilt_backlash_deg` from
the stops reached from both directions, instead of using the configured
values, so no separate backlash capture is needed.
It also fits two nuisance parameters, so the measurement doesn't need to start
from a perfectly known state:
- a small **start pose correction**: above ~1°, re-calibrate and measure again,
- where each axis **started within its backlash band**, which depends on how
  the camera last arrived.

It then prints, per axis:

| line | meaning |
|---|---|
| per-stop table | `actual`: the rotation the tags say the camera made; `current`/`fitted`: what the service computes with the current/fitted curve |
| `service, as measured` | what step 1 measured |
| `current` | current curves and pan axis, from the fitted start state |
| `linear` | best constant scale (with the fitted pan axis) |
| `curve` | best polynomial (`--pan-degree`/`--tilt-degree`, default 2), with the fitted pan axis |
| `floor` | best angle fitted independently at each stop: the lowest error any curve can reach |
| `WARNING` | the fitted curve bends implausibly outside the measured range (checked over `--pan-travel`/`--tilt-travel`); widen the path or use degree 1 |

It ends with the `pan_curve`/`tilt_curve`/`pan_axis` lines (plus the backlash
lines with `--fit-backlash`) to paste into
`config/cameras.json` (the curves replace `pan_scale`/`tilt_scale`). If `curve`
is close to `floor`, the model is as good as it can be. If the floor itself is
well above the start-position error, the rest is not in the model: look for
direction-dependent errors (backlash) or tag detection problems at those stops.

A large, constant tilt (or pan) error on every stop after the first move,
including back at the start position, means the service assumed the wrong
side of the backlash band. The fitted `started ... within [...]` offset then
sits at the opposite edge from what `*_home_approach` says; the fit itself
is still valid.

To apply the result:

1. Put the printed lines in `config/cameras.json`. Set `pan_home_approach` to
   `"decreasing"` and `tilt_home_approach` to `"increasing"`: that is how the
   default path last arrives at the start position.
2. `docker compose restart ptz-pose`. The config file is mounted, so no rebuild
   is needed.
3. Auto-calibrate from the UI and click **Save camera**, without moving the
   camera. On restart the service takes the stored pose as home, which carries
   whatever error the old settings had; saving a fresh calibration makes it
   the trusted home.
4. Repeat steps 1-2 of the measurement to confirm. When the values have
   converged, `current`, `curve` and `floor` agree, and re-fitting returns the
   same pan axis and backlash.

<details>
<summary>What this looked like on the development camera</summary>

Mean / max error per axis:

| state | pan | tilt |
|---|---|---|
| after first restart: tilt home approach unknown, `pan_scale: -154.15` | 20.8 / 76.2 px | 22.3 / 31.8 px |
| re-calibrated from the UI while running | 21.4 / 77.5 px | 4.8 / 10.4 px¹ |
| + pan-only curve `[0, -166.06, 34.61]`, `tilt_home_approach: increasing` | 14.4 / 48.8 px | 4.8 / 10.4 px¹ |
| same settings, wider tilt path (+0.1 / −0.3) | 13.9 / 46.7 px | 9.2 / 30.0 px |
| + `fit_ptz_curves.py`: pan `[0, -164.2, 39.11]`, tilt `[0, 63.03, -5.01]` | 12.3 / 38.2 px | 4.5 / 14.2 px |
| + `pan_axis` `[0.0684, 0.1106, 0.9915]` (7.5° lean), refitted pan `[0, -158.55, 35.15]`, tilt `[0, 51.69, 3.5]` | 6.9 / 23.9 px | 4.0 / 7.9 px |
| next day, after a camera reboot: same settings, tilt home approach now wrong | 7.7 / 20.1 px | 44.4 / 65.9 px |
| + `--fit-backlash`: pan backlash 0.75°, tilt 2.63°, refitted curves and axis, fresh home | **5.0 / 16.3 px** | **3.9 / 9.2 px** |

¹ tilt path ±0.1 only.

- The wider tilt path exposed the old `tilt_curve` `[0, 42.05, 9.41]`, which
  came from the texture sweep. It was accurate near home but under-rotated by
  1.3° at −16° (up to 30 px). Fitted against tags over the wider range, tilt
  error halved and reached its floor (4.3 px).
- A tilt curve fitted on the narrow ±0.1 path alone, `[0, -7.37, 40.33]`,
  matched the data but reversed slope near tilt 0.1. That is why the tool
  warns about extrapolation and why the default tilt path is wide.
- The fit found tilt had started +1.40° into its ±1.42° backlash band
  (arrived going down). Without fitting that, the tilt numbers would have been
  skewed by a full backlash.
- **Pan** is non-uniform (~170 °/unit on the negative side of home, ~150 on
  the positive). With the curve alone it stopped at ~12 px, because the pan
  axis leans 7.5° from world vertical. Setting `pan_axis` halved the pan error
  (12.3 → 6.9 px), and a re-fit on the new data returned the same axis to
  within 0.25°.
- The remaining pan error was uneven. At pan +0.108 it was 5 px arriving from
  one side and 16 px from the other. `--fit-backlash` measured 0.75° of pan
  backlash (configured as 0 until then); modelling it brought pan to 5.0 px.
  A re-fit on the new data returned the same backlash (0.76° pan, 2.58° tilt)
  and axis (within 0.3°).
- After the camera was rebooted, it arrived at home tilting down while the
  config said `increasing`, so the service was a full backlash (~2.7°, ~45 px)
  off in tilt. The fit recovered the curve unaffected.
</details>

#### Pan axis not vertical

By default the model pans about world vertical (`Rz`). If the mount isn't
level, or the stored home rotation has a small error about a horizontal axis,
pan actually turns about a leaning axis. The error then grows with the pan
angle, pure pan moves also appear to change tilt, and no `pan_curve` can
remove it.

`fit_ptz_curves.py` fits the axis by default and prints it as `pan_axis`, with
its lean from vertical. Put it in `config/cameras.json`; the service then pans
about that axis. It is a property of the mount, so it stays valid across
re-calibrations, but re-measure it if the camera is remounted. A lean of more
than a few degrees may also be worth fixing physically.

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
| [`collect_calibration_views.py`](tools/collect_calibration_views.py) | `ptz-pose` | Collect AprilTag 2D/3D correspondences: pan/tilt sweep, or repeated frames of a static camera |
| [`calibrate_intrinsics.py`](tools/calibrate_intrinsics.py) | `autocalibration` | Fit intrinsics + distortion from those views |
| [`capture_ptz_sweep.py`](tools/capture_ptz_sweep.py) | `ptz-pose` | Sweep pan/tilt, saving a frame at each position (no markers needed) |
| [`measure_ptz_scale.py`](tools/measure_ptz_scale.py) | `autocalibration` | Recover degrees-per-ONVIF-unit from those frames |
| [`capture_ptz_backlash.py`](tools/capture_ptz_backlash.py) | `ptz-pose` | Arrive at positions from both directions, saving frame pairs |
| [`measure_ptz_backlash.py`](tools/measure_ptz_backlash.py) | `autocalibration` | Measure mechanical slack from those pairs |
| [`measure_reprojection_accuracy.py`](tools/measure_reprojection_accuracy.py) | `ptz-pose` (service running) | Drive a pan/tilt path, measure stored-pose error against detected AprilTags |
| [`fit_ptz_curves.py`](tools/fit_ptz_curves.py) | `autocalibration` | Fit `pan_curve`, `tilt_curve`, `pan_axis` and (with `--fit-backlash`) backlash from that measurement, and report the floor any curve can reach |
| [`onvif_reboot.py`](tools/onvif_reboot.py) | `ptz-pose` | Reboot a camera over ONVIF |
| [`tune_ptz_camera.sh`](tools/tune_ptz_camera.sh) | host | Run the whole tuning procedure for one camera and write the results to the config |
| [`ptz_goto.py`](tools/ptz_goto.py) | `ptz-pose` | Move to a position arriving from a given direction per axis (or print the position) |
| [`save_fresh_calibration.py`](tools/save_fresh_calibration.py) | `ptz-pose` | Auto-calibrate at the current view and save it, like Auto calibrate + Save camera |
| [`update_camera_config.py`](tools/update_camera_config.py) | host | Set, merge or remove fields of one camera's entry in `cameras.json` |

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

The service waits for `--pose-settle-s` after the last detected motion before
publishing a pose. This avoids several intermediate point jumps during one PTZ
move, but the displayed pose remains at the previous position while the head
is moving. The image refreshes independently, so points may temporarily be
off the tags during motion; they should align once the head settles and a new
image arrives. Set `--pose-settle-s 0` (or `pose_settle_s: 0` per camera) to
restore in-motion updates.

## Re-calibrating while the service runs

The **home** is the trusted ground-truth calibration: a pose calibrated by the
user, manually or with the autocalibration service, together with the pan/tilt
the camera was at. Every pose the service writes after a move is *derived* from
that home by calculation.

When the camera is calibrated again from the UI (manually or by triggering
auto-calibration) while the service runs, the service notices within
`--rebaseline-check-s` (default 2s) and adopts that calibration as the new
home: its pose, calibration points and lens parameters, paired with the
pan/tilt the camera is at that moment. All later moves are calculated from it.
The backlash state is carried over, since the service already knows which side
of the slack each axis is on.

In the UI, **Auto calibrate** only proposes a calibration on the page; nothing
is stored until **Save camera** is clicked, so that is when the service adopts
it and logs `new calibration saved in Scenescape; adopted as the trusted home`.
Don't move the camera between the two clicks: the service's live updates for
the move replace the proposed points on the page, and those would be saved
instead.

Detection compares the *stored correspondences* against the ones the service
expects (the home at startup, then its own writes), with no angle threshold:
they are stored exactly as written, so any difference is a new calibration,
even one a fraction of a degree from the current pose, as a re-calibration
of a still camera usually is. Comparing rotations instead would not work:
Scenescape re-derives rotation from written points via `solvePnP`, and that
value drifts slightly from the one used to generate them. Only a camera stored
as a plain Euler pose is compared by rotation, using
`--rebaseline-tolerance-deg`.

The home is held in memory only. On restart the service takes whatever pose is
stored at that moment as home, which is a derived pose if the camera was moved
since its last calibration. For the most accurate home after a restart,
calibrate once from the UI at the camera's current position.

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
[`measure_reprojection_accuracy.py`](#measuring-tracking-accuracy-and-fitting-the-head-model).
It gives pixel error per position against detected tags. Comparing with a
manual auto-calibration from the UI is coarser: a single run is not exact
ground truth. On the development camera, repeated runs from the same position
varied by up to `[0.34, 0.19, 0.21] m` in translation and a few degrees in
rotation.

### Diagnosing a pose that tracks badly

| Symptom | Likely cause |
|---|---|
| Error grows steadily with distance from the calibrated position | `pan_scale`/`tilt_scale` wrong — [re-measure](#measuring-pantilt-scale-factors) |
| Tracks one direction well, offset the other way | Backlash — [measure it](#measuring-backlash) |
| Offset by roughly half the backlash in *both* directions | Home approach direction unknown — set `*_home_approach` |
| Good near the middle of travel, drifts at both ends in opposite directions | Non-uniform travel — [fit a curve](#if-the-scale-isnt-constant) |
| Pan error grows with angle even with a fitted `pan_curve`; tilt also drifts during pure pan moves | Pan axis not vertical — [set `pan_axis`](#pan-axis-not-vertical) |
| Pose rotates the wrong way entirely | Sign — negate the scale or set `invert_pan`/`invert_tilt` |
| Points fit near the image centre but drift at the edges | Lens distortion — [calibrate intrinsics](#calibrating-intrinsics-and-lens-distortion) |
| Points vanish from the 2D view | Expected for tags that have left the frame. If all vanish, fewer than 6 points were in view and the pose was written as a Euler rotation; they return once enough tags are back in view. If the service restarted meanwhile, it only sees the Euler pose, so re-calibrate once from the UI |
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
| `--pose-settle-s` | `0.5` | seconds of stillness before a pose is written (0 updates during movement) |
| `--pan-scale` / `--tilt-scale` | `1.0` | default degrees per unit of ONVIF pan/tilt |
| `--invert-pan` / `--invert-tilt` | `false` | flip sign of pan/tilt contribution |
| `--rebaseline-check-s` | `2.0` | how often to look for an externally applied re-calibration (0 disables) |
| `--rebaseline-tolerance-deg` | `0.5` | for a camera stored as a Euler pose only: how far its rotation must differ before it counts as a new calibration |
| `--no-notify-ui` | off | don't publish pose updates for open calibration pages |
| `--broker` / `--brokerauth` / `--brokerrootcert` | Scenescape defaults | MQTT broker used for those live page updates |
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
