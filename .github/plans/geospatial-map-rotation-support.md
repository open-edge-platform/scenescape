<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Geospatial Map Rotation Support

## Status

Planned follow-up to PR #2023 (OSM auto-ROI). PR #2023 disables Mapbox
rotation as a stopgap; this plan restores rotation with correct geospatial
corners and removes the stopgap.

## Problem

For geospatial scenes the manager stores `map_corners_lla` (SW, NW, NE, SE)
and a 1280x1280 snapshot used as the scene map. The controller derives the
local-to-LLA transform from these corners
(`controller/src/controller/scene.py` `trs_xyz_to_lla` ->
`calculateTRSLocal2LLAFromSurfacePoints`), and the manager stores the result
in `Scene.trs_matrix`, which OSM ROI generation uses.

When a Mapbox map is rotated (`bearing != 0`):

- `mapbox-plugin.js` `generateBounds()` reads corners from `map.getBounds()`.
  For a rotated view Mapbox returns the smallest axis-aligned box enclosing
  the visible area, not the rotated viewport corners.
- `generateSnapshot()` requests the static image with the bearing, so the
  snapshot is rotated.
- Result: corners and image disagree in orientation and extent, so the
  transform is wrong in rotation and scale. All LLA output for the scene is
  affected, not only OSM ROIs.
- `scene-update-osm-roi.js` rotates previewed ROI points by the bearing around
  `map_center` (server returns `bearing` and `center`) to partially hide this.
  That compensation is not exact because the transform's scale is also wrong.

Bbox validation is not the issue: `osm_roi.bbox_from_map_corners()` takes the
min/max of the corners and is already correct for any rotated rectangle.

## Goals

- Mapbox scenes can be saved at any bearing with exact corners for the
  rotated snapshot.
- OSM ROIs and all LLA output are correct for rotated scenes without
  client-side bearing compensation.
- Existing scenes saved with a non-zero bearing are repaired or clearly
  flagged.
- One shared, tested implementation of "view -> corners" math.

## Non-goals

- Rotation for Google Maps. Its snapshot is stitched from north-up static
  tiles; PR #2023 sets `rotateControl: false`, `heading: 0`, and resets the
  heading before collecting corners. Keep that as is.
- Pitch/tilt support. Views stay orthographic.
- Clipping OSM queries to non-rectangular areas on the ohsome side.

## Design

### 1. Corner computation from view parameters

Compute corners analytically from the parameters the static snapshot is
requested with (center, zoom, bearing, 1280x1280 px, 512 px Web Mercator
tiles), instead of from the interactive map's container. This guarantees
corners match the saved image even if the container size differs from the
snapshot size.

For each image corner pixel offset `(dx, dy)` from the image center
(`(-w/2, +h/2)` = bottom-left, `(-w/2, -h/2)` = top-left, `(+w/2, -h/2)` =
top-right, `(+w/2, +h/2)` = bottom-right):

1. Rotate the offset by the bearing (screen -> world pixel axes; Mapbox
   bearing is clockwise degrees from north).
2. Add to the center's world pixel coordinates at the zoom.
3. Convert world pixels back to lat/lng.

Corner order stays SW, NW, NE, SE in image terms (bottom-left, top-left,
top-right, bottom-right); `alignCornerWinding` already accepts this order.

Implementation:

- Python: add `mapViewCornersLLA(center_lat, center_lng, zoom, bearing_deg,
width_px, height_px, tile_size=512)` to `scene_common/src/scene_common/earth_lla.py`.
  Refactor `tools/px4_sih_demo/setup_geospatial_drone_scene.py`
  `map_view_corners()` to call it (bearing 0).
- JavaScript: mirror the function in
  `manager/src/manager/static/js/geospatial/map-math.js` (new, ES module or
  plain script matching how the plugins are loaded) and use it in
  `MapboxPlugin.generateBounds()`.
- Before relying on the container, verify whether `map.unproject()` on the
  container corners would be equivalent; keep the analytic version regardless
  so the server can reuse it (see section 4).

### 2. Mapbox plugin

- Revert the PR #2023 stopgap: `dragRotate: true`, re-enable touch/keyboard
  rotation, always show the compass, remove the `jumpTo({ bearing: 0 })` in
  `generateBounds()` and the legacy-rotation `console.warn`.
- `generateBounds()` uses the corner function with `getCenter()`,
  `getZoom()`, `getBearing()`, and the snapshot size constants shared with
  `generateSnapshot()` (hoist `1280` to a single constant).
- Keep the PR #2023 ordering in `scene-form.js` (generate bounds, then save
  settings) so `map_bearing` is the bearing the corners were computed with.

### 3. OSM ROI preview

- Remove `rotatePointAroundPivot` and its use from
  `scene-update-osm-roi.js`; draw previewed points as returned.
- Remove `bearing` and `center` from the `osm-roi-previews` response in
  `views.py` (`OsmRoiPreviews`), the pivot computation, and the matching
  fields in `docs/user-guide/api-docs/api.yaml`.
- Optional: in `osm_roi.build_roi_previews()`, drop polygons that do not
  intersect the scene's local map rectangle. With rotation, the min/max
  bbox can cover up to ~2x the scene area, so this keeps previews on-map and
  makes the `OSM_MAX_ROI_FEATURES` cap less likely to be hit by off-map ways.

### 4. Existing rotated scenes

Scenes saved before this change with `geospatial_provider == "mapbox"` and
`map_bearing != 0` have wrong corners but a correct rotated snapshot.

- Data migration in `manager/src/manager/migrations/`: for those scenes,
  recompute `map_corners_lla` with `mapViewCornersLLA(map_center_lat,
map_center_lng, map_zoom, map_bearing, 1280, 1280)` (altitude from the
  existing corners), and clear `trs_matrix`, `osm_ways_cache`, and
  `osm_ways_cache_bbox` so they are rebuilt.
- Skip (and log) scenes missing center/zoom.
- Risk: before PR #2023, `scene-form.js` saved center/zoom/bearing before
  generating the snapshot, so a scene where the map moved between the two
  steps would get mismatched corners. See open questions; fallback is a UI
  warning asking the user to regenerate bounds.
- Controller: confirm the cached `_trs_xyz_to_lla` is invalidated on scene
  update so the new corners take effect without restart.

### 5. Documentation

- `configure-geospatial-coordinates.md`: remove the PR #2023 "always
  north-up" and "reset to north-up" lines; state that Mapbox maps can be
  rotated and Google Maps stays north-up.
- `api.yaml`: drop `bearing`/`center` from the preview response.
- Manager docs/changelog: note the migration for previously rotated scenes.

## Testing

Unit (`tests/sscape_tests/`):

- `geospatial/test_earth_lla.py`: `mapViewCornersLLA` at bearings 0, 30, 90,
  180, 270 and at high latitude:
  - bearing 0 matches the existing north-up corners.
  - corners feed `calculateTRSLocal2LLAFromSurfacePoints` with the image
    rectangle `[0,0]..[w/scale,h/scale]`; round-trip error < 1 m per corner.
  - side lengths equal `width_px / scale` and `height_px / scale` within 1%.
- `views/test_osm_roi_views.py`: preview response no longer includes
  `bearing`/`center`; ROI points for a rotated scene land inside the map
  rectangle.
- `manager`: data migration test with a rotated Mapbox scene (corners
  recomputed, caches cleared) and a north-up/Google scene (untouched).

Manual / UI:

- Mapbox scene at ~30 deg bearing: generate bounds, save, confirm OSM ROI
  preview aligns with roads on the snapshot; confirm a tracked object's LLA
  output matches the snapshot position.
- Repeat at bearing 0 to confirm no regression.
- Google Maps scene unchanged.

## Rollout

1. Land corner math + tests (scene_common, tool refactor).
2. Mapbox plugin and OSM preview changes, docs, API spec.
3. Data migration for existing rotated scenes.

Steps can be one PR; ship 3 with 2 so repaired scenes and new behavior arrive
together.

## Open Questions

- Do saved `map_center_lat/lng`, `map_zoom`, `map_bearing` reliably match the
  stored snapshot for scenes created before PR #2023? If not, should the
  migration only flag scenes (UI warning) instead of rewriting corners?
- Is the off-map polygon filter (section 3) wanted in the same PR, or as a
  separate cap-efficiency change?
