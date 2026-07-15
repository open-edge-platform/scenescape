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

## Caveat: manual calibration is required

Auto-reconstruction estimates camera pose (position + orientation) as a side effect of building
the mesh from captured frames. A pre-made blueprint/GLB/geospatial map has no such frames to
estimate pose from, so cameras must be calibrated **manually** through the SceneScape web UI (2D
or 3D calibration UI) after the scene is created. This skill cannot automate that step — it
requires interactively adding/dragging correspondence points in a browser. Confirm the user
accepts this tradeoff before proceeding.

Exception: uploading a `.zip` Polycam scan (a mobile 3D scan) instead of a blueprint/GLB enables
`markerless` auto-calibration — mention this option if the user has a mobile 3D scan rather than a
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
TOKEN=$(curl -sk -X POST https://web.scenescape.intel.com/api/v1/auth \
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

   Example: a 960-pixel-wide image that spans 12 meters across the real scene →
   `960 / 12 = 80` pixels per meter.

2. **Two known reference points** (more accurate when the image isn't a straight-on/orthographic
   view of the whole area): the pixel distance and real-world distance between two identifiable
   landmarks (e.g. parking-line centers, wall corners).

   ```
   scale = pixel_distance_between_points / real_world_distance_meters
   ```

   Example: two points 475 pixels apart on the image are 18.59 meters apart in reality →
   `475 / 18.59 ≈ 25.55` pixels per meter.

Confirm the computed `scale` value with the user before creating the scene — an incorrect scale
causes all tracked positions to be wrong by a constant factor.

## Creating the scene from a blueprint image or GLB/PLY mesh

```bash
curl -sk -X POST https://web.scenescape.intel.com/api/v1/scene \
  -H "Authorization: Token $TOKEN" \
  -F "name=<scene_name>" \
  -F "map=@<path-to-blueprint.png-or-mesh.glb>" \
  -F "scale=<pixels_per_meter>" \
  -F "map_type=map_upload" \
  -F "camera_calibration=manual"
```

- `scale` is required (and meaningful) for 2D image maps; for `.glb`/`.ply` meshes SceneScape
  auto-computes and overwrites `scale` from an orthographic projection of the mesh — you can omit
  it or pass a placeholder.
- `camera_calibration=manual` matches the caveat above and is the default; use `markerless` instead
  if uploading a Polycam `.zip`.
- The response includes `"uid"` — the new `scene_uid`. Save it; camera registration and the
  geospatial steps below need it.

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
PATCH it with the geospatial fields:

```bash
curl -sk -X PATCH https://web.scenescape.intel.com/api/v1/scene/<scene_uid> \
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
docker run --rm --network <project>_scenescape \
  -v <deploy_dir>/secrets/certs/scenescape-ca.pem:/ca.pem:ro \
  eclipse-mosquitto:2 \
  mosquitto_sub -h broker.scenescape.intel.com -p 1883 \
  --cafile /ca.pem --insecure \
  -t 'scenescape/regulated/scene/<scene_uid>' -C 1 -W 120
```

Pass: `.object[].lat_long_alt` is present with plausible latitude/longitude values.

## Notes

- `map` accepts `.glb`, `.ply`, `.png`, `.jpg`/`.jpeg`, `.zip` (Polycam scan), or video
  (`.mp4`/`.mov`/`.mkv`/`.webm`/`.avi`) for keyframe extraction.
- `map_type` is `map_upload` for blueprint/GLB/mesh uploads. `geospatial_map` is only used by the
  browser-based "generate from address" flow, which cannot be automated by this skill; the manual
  `map_corners_lla` PATCH above works regardless of `map_type`.
