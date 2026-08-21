<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Alternative Scene Sources: Blueprint, GLB Mesh, and Geospatial Maps

By default (steps 9, 11–13) the orchestrator captures calibration frames from each camera and
auto-generates the scene map via the mapping service (`reconstruct_and_finalize.py`), which also
estimates each camera's pose automatically. Use this reference when the user already has a 2D
floor blueprint image, a 3D `.glb`/`.ply` mesh, or wants to build the scene from a geospatial
(GPS-based) map instead of auto-reconstruction.

## Caveat: manual calibration vs automated camera.json

Auto-reconstruction estimates camera pose (position + orientation) as a side effect of building
the mesh from captured frames. A pre-made blueprint/GLB/geospatial map has no such frames to
estimate pose from.

* **Without pre-calibrated cameras**: Cameras must be calibrated **manually** through the SceneScape
  web UI (2D or 3D calibration UI) after the scene is created.
* **With pre-calibrated `camera.json`**: If the user provides a `camera.json` containing camera
  translation, rotation (quaternion), and intrinsics (`fx`, `fy`, `cx`, `cy`), camera registration can be
  **fully automated** via REST API, bypassing manual UI calibration.

Exception: uploading a `.zip` Polycam scan (a mobile 3D scan) instead of a blueprint/GLB enables
`Markerless` auto-calibration — mention this option if the user has a mobile 3D scan rather than a
static blueprint image or GLB file.

## Running only bootstrap + calibrate (skip auto-reconstruction)

Run the orchestrator through calibration only, then create the scene manually with the steps
below instead of letting steps 11–13 run automatic reconstruction:

```bash
bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase bootstrap

bash "$SKILL_DIR/scripts/deploy_scenescape.sh" \
  --deploy-dir <deploy_dir> \
  --skill-dir "$SKILL_DIR" \
  --phase calibrate
```

(`--phase calibrate` still captures calibration frames per camera even though they won't be used
for reconstruction — harmless, and keeps `.deploy-state.json` consistent for later resume.)

## Authenticate to the manager

REST calls below need a token from the manager's `admin` account (password in
`<deploy_dir>/secrets/supass`):

```bash
SUPASS=$(cat <deploy_dir>/secrets/supass)
TOKEN=$(curl -sk -X POST https://localhost/api/v1/auth \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"admin\", \"password\": \"$SUPASS\"}" | \
  python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
```

## Computing pixels per meter (floor blueprint only)

A 2D floor blueprint has no inherent scale, so SceneScape needs a `scale` value in
**pixels per meter** to convert calibrated pixel positions to real-world meters. (`.glb`/`.ply`
meshes and geospatial maps are scaled automatically — skip this section for those.)

Ask the user for one of:

1. **Known image width**: the blueprint's pixel width, and the real-world width (in meters) that
   the same edge of the image spans.

   ```
   scale = image_width_pixels / real_world_width_meters
   ```

2. **Two known reference points** (more accurate when the image isn't a straight-on/orthographic
   view of the whole area): the pixel distance and real-world distance between two identifiable
   landmarks (e.g. parking-line centers, wall corners).

   ```
   scale = pixel_distance_between_points / real_world_distance_meters
   ```

Confirm the computed `scale` value with the user before creating the scene — an incorrect scale
causes all tracked positions to be wrong by a constant factor.

## Creating the scene from a blueprint image or GLB/PLY mesh

```bash
curl -sk -X POST https://localhost/api/v1/scene \
  -H "Authorization: Token $TOKEN" \
  -F "name=<scene_name>" \
  -F "map=@<path-to-blueprint.png-or-mesh.glb>" \
  -F "scale=<pixels_per_meter>" \
  -F "map_type=map_upload" \
  -F "camera_calibration=Manual"
```

- `scale` is required (and meaningful) for 2D image maps; for `.glb`/`.ply` meshes SceneScape
  auto-computes and overwrites `scale` from an orthographic projection of the mesh — you can omit
  it or pass a placeholder.
- `camera_calibration=Manual` matches the caveat above and is the default; use `Markerless` instead
  if uploading a Polycam `.zip`. (Note the value is capitalized — see the `CameraCalibrationEnum`
  in the OpenAPI schema.)
- The response includes `"uid"` — the new `scene_uid`. Save it; camera registration and the
  geospatial steps below need it.

### Automated camera registration with `camera.json`

When a pre-calibrated `camera.json` file is provided, use
`scripts/register_cameras.py` to batch-register the cameras via REST instead of requiring manual
UI calibration. It auto-detects the per-camera identifier key (`sensor_id`/`uid`/`name`/`id`),
auto-detects euler vs quaternion rotation (the manager API converts quaternion → euler
server-side), and auto-deletes orphaned (scene=None) cameras that collide with a name being
registered (a retry after any prior failed attempt would otherwise 400 with "orphaned camera with
the name ... already exists").

```bash
python3 "$SKILL_DIR/scripts/register_cameras.py" \
  --deploy-dir <deploy_dir> \
  --scene-uid <scene_uid> \
  --camera-json <path_to_camera.json> \
  --camera-ids <id> [<id> ...]
```

`--camera-ids` (the deployed camera_ids) is optional but recommended: with it, the script
validates every camera.json identifier resolves to a known camera_id and refuses to guess. If an
identifier doesn't match (case-insensitively) — e.g. the JSON names a camera `FrontView_L2` but
the deployed `camera_id` is `rearview_l` — it exits with the exact `--camera-map` flags needed:

```bash
python3 "$SKILL_DIR/scripts/register_cameras.py" \
  --deploy-dir <deploy_dir> \
  --scene-uid <scene_uid> \
  --camera-json <path_to_camera.json> \
  --camera-map 'FrontView_L2=rearview_l' 'FrontView_R2=rearview_r' ...
```

Never guess this mapping yourself from filenames alone — confirm it with the user first, the same
way an ambiguous `camera_id`/stream change requires confirmation in Step 1.

Once registered, verify tracking:

```bash
bash "$SKILL_DIR/scripts/verify_tracking.sh" <deploy_dir> <scene_uid> 120
```

### Manual Web UI camera registration (when `camera.json` is not provided)

Register a placeholder camera per `camera_id` using
[scene-and-cameras.md](./scene-and-cameras.md#camera-registration) with this `scene_uid`, then tell
the user the scene/cameras are created and calibration must be completed manually:

> Log in to the SceneScape web UI at `https://<manager-host>`, open **`<scene_name>`**, click each
> camera, and use the 2D or 3D calibration UI to align the camera view with the map (add ≥4
> correspondence points, ideally 8+, avoiding collinear points). Tracked objects will appear once
> calibration is saved.

Do not run `verify_tracking.sh` (step 13) until the user confirms calibration is done — there is no
valid camera pose (and therefore no regulated tracking output) until then. Once they confirm:

```bash
bash scripts/verify_tracking.sh <deploy_dir> <scene_uid> 120
```

## Geospatial map scenes

To additionally publish detected-object GPS coordinates (`lat_long_alt`) alongside local scene
coordinates, the scene needs `output_lla=true` and the geospatial coordinates of its four map
corners (`map_corners_lla`).

### Gather from the user

- The four corners' `[latitude, longitude, altitude]`, **counterclockwise starting at the
  bottom-left corner** of the map (image corners for a 2D map; the XY-plane bounding box of the
  mesh projection for a 3D map).
- Confirm these assumptions hold, since accuracy (~1 meter) depends on them: the scene surface is
  horizontal and relatively flat, both scene dimensions are under 400 meters, and tracked objects
  stay under 2 meters above the surface.

### Create or update the scene

Create the scene first (previous section — a blueprint/GLB/mesh map upload is still required;
this skill does not automate the browser-based "generate a snapshot from an address" flow), then
send the geospatial fields with `PUT /api/v1/scene/<scene_uid>` (the manager applies this as a
partial update — omitted fields like `name`/`map` are left unchanged; the endpoint does not support
`PATCH`):

```bash
curl -sk -X PUT https://localhost/api/v1/scene/<scene_uid> \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "output_lla": true,
    "map_corners_lla": [
      [<lat1>, <lon1>, <alt1>],
      [<lat2>, <lon2>, <alt2>],
      [<lat3>, <lon3>, <alt3>],
      [<lat4>, <lon4>, <alt4>]
    ]
  }'
```

`map_corners_lla` is required whenever `output_lla` is `true` — the manager rejects the request
otherwise.

### Verify geospatial output

After manual camera calibration is complete (see above), subscribe to the regulated scene topic
(TLS template in [command-templates.md](./command-templates.md)) and confirm each object includes
`lat_long_alt`:

```bash
docker container run --rm --network <project>_scenescape \
  -v <deploy_dir>/secrets/certs/scenescape-ca.pem:/ca.pem:ro \
  eclipse-mosquitto:2.0.22 \
  mosquitto_sub -h broker.scenescape.intel.com -p 1883 \
  --cafile /ca.pem --insecure \
  -t 'scenescape/regulated/scene/<scene_uid>' -C 1 -W 120
```

Pass: `.object[].lat_long_alt` is present with plausible latitude/longitude values.

## Notes

- Full field reference for `POST`/`PUT /api/v1/scene` (accepted `map` file types, `map_type`,
  `camera_calibration` enum values, `output_lla`/`map_corners_lla`) is the canonical OpenAPI spec:
  `docs/user-guide/api-docs/api.yaml` (`Scene` schema), rendered at
  `docs/user-guide/api-reference.md`. Don't restate its fields here — link to it.
- The manual `map_corners_lla` update above works regardless of `map_type` — `geospatial_map` is
  only used by the browser-based "generate from address" flow, which cannot be automated by this
  skill.
