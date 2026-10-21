#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for OSM ROI preview and creation endpoints."""

import json
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from manager.models import Scene, Region, RegionPoint
from manager.osm_roi import STANDARD_LANE_WIDTH_M
from scene_common.earth_lla import calculateTRSLocal2LLAFromSurfacePoints


# Map corner coordinates (LLA) reused from functional tests
MAP_CORNERS_LLA = [
  [37.38685435, -121.96408120, 8.0],
  [37.38693520, -121.96408120, 8.0],
  [37.38693520, -121.96413896, 8.0],
  [37.38685435, -121.96413896, 8.0],
]

# Local corner coordinates (scene meters), forming a simple square
MAP_XYZ_CORNERS = [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]]


def _post_previews(client, scene_uid, payload=None):
  return client.post(
    reverse("osm_roi_previews", kwargs={"scene_uid": scene_uid}),
    data=json.dumps(payload or {}),
    content_type="application/json",
  )


class TestOsmRoiPreviews(TestCase):
  """Verifies the osm-roi-previews endpoint: auth, calibration check, and geometry conversion."""

  def setUp(self):
    """Create superuser and geospatial scene with trs_matrix and map_corners_lla."""
    self.user = User.objects.create_superuser("test_user", "test_user@intel.com", "testpassword")

    # Create scene with geospatial setup
    self.scene = Scene.objects.create(
      name="test_scene_geospatial",
      map_type="geospatial",
      output_lla=True,
      # v3: OSM query bbox is derived from map_corners_lla, no separate bbox fields
      map_corners_lla=MAP_CORNERS_LLA,
    )

    # Compute and set trs_matrix (convert numpy array to list for JSON serialization)
    trs_matrix = calculateTRSLocal2LLAFromSurfacePoints(MAP_XYZ_CORNERS, MAP_CORNERS_LLA)
    self.scene.trs_matrix = trs_matrix.tolist() if hasattr(trs_matrix, "tolist") else list(trs_matrix)
    self.scene.save()

  def test_authenticated_preview_returns_rois_with_correct_names(self):
    """Test that preview endpoint returns ROIs with correct naming (de-duplicated by type)."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Mock osm_query.query_osm_ways_geometry to return 3 test ways with tags
    # Use MAP_CORNERS_LLA endpoints for round-trip consistency
    fake_ways = [
      {
        "type": "footway",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": {"highway": "footway", "footway": "sidewalk", "lit": "yes", "surface": "paving_stones"},
      },
      {
        "type": "footway",
        "coords": [[MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]],
                   [MAP_CORNERS_LLA[2][0], MAP_CORNERS_LLA[2][1]]],
        "tags": {"highway": "footway", "footway": "crossing", "lit": "yes", "tactile_paving": "yes"},
      },
      {
        "type": "residential",
        "coords": [[MAP_CORNERS_LLA[2][0], MAP_CORNERS_LLA[2][1]],
                   [MAP_CORNERS_LLA[3][0], MAP_CORNERS_LLA[3][1]]],
        "tags": {"highway": "residential", "lanes": "2", "lit": "yes", "surface": "asphalt"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fake_ways):
      response = _post_previews(self.client, self.scene.id)

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertIn("rois", result)
    self.assertEqual(len(result["rois"]), 3)

    # Verify naming: should use enhanced names with footway subtype, without bracketed tag comments
    # E.g., "Sidewalk", "Pedestrian Crossing", etc.
    names = [roi["name"] for roi in result["rois"]]
    # Should have at least one sidewalk and one crossing, plus residential street
    self.assertTrue(any("Sidewalk" in name for name in names), f"Expected 'Sidewalk' in names: {names}")
    self.assertTrue(any("Crossing" in name for name in names), f"Expected 'Crossing' in names: {names}")
    self.assertTrue(any("Residential" in name for name in names), f"Expected 'Residential' in names: {names}")
    self.assertTrue(all("[" not in name for name in names), f"Names must not include bracketed tag comments: {names}")

    # Each ROI should have points, type, uuid, tags, and width_m fields
    for roi in result["rois"]:
      self.assertIn("points", roi)
      self.assertIn("type", roi)
      self.assertIn("uuid", roi)  # temporary tracking UUID
      self.assertIn("tags", roi)  # full OSM tags
      self.assertIn("width_m", roi)  # computed or extracted width
      self.assertGreaterEqual(len(roi["points"]), 3)  # Buffered polygon should have >= 3 points
      self.assertIsInstance(roi["width_m"], (int, float))  # Width should be numeric
      self.assertGreater(roi["width_m"], 0)  # Width should be positive

  def test_preview_uses_lane_based_width_for_minor_road_types(self):
    """Regression: tertiary/unclassified/living_street previously weren't in the lane-based
    lookup, so their 'lanes' tag was silently ignored and every such way fell back to the
    flat DEFAULT_ROAD_WIDTH_M (4.0m) regardless of actual lane count.
    """
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    fake_ways = [
      {
        "type": "tertiary",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": {"highway": "tertiary", "lanes": "2", "name": "Rudzka"},
      },
      {
        "type": "unclassified",
        "coords": [[MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]],
                   [MAP_CORNERS_LLA[2][0], MAP_CORNERS_LLA[2][1]]],
        "tags": {"highway": "unclassified", "lanes": "2"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fake_ways):
      response = _post_previews(self.client, self.scene.id)

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    widths = {roi["type"]: roi["width_m"] for roi in result["rois"]}
    self.assertEqual(widths["tertiary"], 2 * STANDARD_LANE_WIDTH_M)
    self.assertEqual(widths["unclassified"], 2 * STANDARD_LANE_WIDTH_M)

  def test_preview_refreshes_stale_cache_missing_tags(self):
    """Test that a pre-existing cache without 'tags' (old schema) is treated as stale and re-fetched."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Simulate a cache written before "tags" was added to query results
    stale_ways = [
      {"type": "footway", "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                                      [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]]},
    ]
    self.scene.osm_ways_cache = stale_ways
    self.scene.save()

    fresh_ways = [
      {
        "type": "residential",
        "coords": [[MAP_CORNERS_LLA[2][0], MAP_CORNERS_LLA[2][1]],
                   [MAP_CORNERS_LLA[3][0], MAP_CORNERS_LLA[3][1]]],
        "tags": {"highway": "residential", "lanes": "3", "name": "Grójecka"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fresh_ways) as mock_query:
      response = _post_previews(self.client, self.scene.id)

    mock_query.assert_called_once()  # Stale cache must not be reused
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(len(result["rois"]), 1)
    self.assertIn("Grójecka", result["rois"][0]["name"])
    self.assertEqual(result["rois"][0]["width_m"], 3 * STANDARD_LANE_WIDTH_M)  # lanes-based width

    self.scene.refresh_from_db()
    self.assertEqual(self.scene.osm_ways_cache, fresh_ways)  # cache overwritten with fresh data

  def test_preview_refreshes_stale_cache_list_format_tags(self):
    """Test that a cache storing tags as list-of-pairs (raw ohsome parquet shape) is treated as stale.

    Pandas/pyarrow decode the ohsome Map<string,string> 'tags' column as a list of
    [key, value] pairs rather than a dict; if such a cache were reused as-is, every
    width/lanes-based lookup would silently fall through to the generic default.
    """
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    stale_ways = [
      {
        "type": "way",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": [["highway", "secondary"], ["lanes", "3"], ["name", "Grójecka"]],
      },
    ]
    self.scene.osm_ways_cache = stale_ways
    self.scene.save()

    fresh_ways = [
      {
        "type": "residential",
        "coords": [[MAP_CORNERS_LLA[2][0], MAP_CORNERS_LLA[2][1]],
                   [MAP_CORNERS_LLA[3][0], MAP_CORNERS_LLA[3][1]]],
        "tags": {"highway": "residential", "lanes": "3", "name": "Grójecka"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fresh_ways) as mock_query:
      response = _post_previews(self.client, self.scene.id)

    mock_query.assert_called_once()  # List-format cache must not be reused
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(result["rois"][0]["width_m"], 3 * STANDARD_LANE_WIDTH_M)  # lanes-based width, not the generic default

  def test_preview_caches_osm_ways_and_skips_requery(self):
    """Test that a second preview call reuses osm_ways_cache instead of re-querying OSM."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    fake_ways = [
      {
        "type": "footway",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": {"highway": "footway", "footway": "sidewalk", "lit": "yes"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fake_ways) as mock_query:
      response1 = _post_previews(self.client, self.scene.id)
      response2 = _post_previews(self.client, self.scene.id)

    self.assertEqual(response1.status_code, 200)
    self.assertEqual(response2.status_code, 200)
    mock_query.assert_called_once()  # Second call must reuse the cached ways

    self.scene.refresh_from_db()
    # Verify cache was populated
    self.assertIsNotNone(self.scene.osm_ways_cache)
    self.assertEqual(len(self.scene.osm_ways_cache), len(fake_ways))

  def test_preview_rejects_malformed_scene_uid_in_path(self):
    """Test that a non-UUID scene path segment does not resolve to the endpoint."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    response = self.client.post(
      "/api/v1/scene/not-a-uuid/osm-roi-previews",
      data=json.dumps({}),
      content_type="application/json",
    )

    self.assertEqual(response.status_code, 404)

  def test_preview_requires_map_corners_lla(self):
    """Test that preview endpoint rejects scene without map_corners_lla set (v3: bbox derived from it)."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Create scene without map_corners_lla set
    scene_no_corners = Scene.objects.create(
      name="test_scene_no_corners",
      map_type="geospatial",
      output_lla=True,
    )

    response = _post_previews(self.client, scene_no_corners.id)

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    self.assertIn("error", result)
    self.assertIn("map corners", result["error"])

  def test_preview_requires_scene_with_trs_matrix(self):
    """Test that preview rejects scene without trs_matrix."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Create scene without trs_matrix but with map_corners_lla set
    scene_no_trs = Scene.objects.create(
      name="test_scene_no_trs",
      map_type="geospatial",
      map_corners_lla=MAP_CORNERS_LLA,
    )

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry") as mock_query:
      response = _post_previews(self.client, scene_no_trs.id)

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    self.assertIn("error", result)
    # Message is intentionally generic, no internal field names leaked
    self.assertIn("Unable to preview ROIs", result["error"])
    # Verify we didn't call the upstream query (fail fast)
    mock_query.assert_not_called()

  def test_preview_handles_osm_query_error(self):
    """Test that preview endpoint surfaces upstream OSM query errors."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    from manager.osm_query import OsmQueryError

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry") as mock_query:
      mock_query.side_effect = OsmQueryError("API key missing")

      response = _post_previews(self.client, self.scene.id)

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    # Message is intentionally generic, no upstream exception text leaked
    self.assertIn("Unable to fetch OSM data", result["error"])

  def test_preview_rejects_invalid_scene_uuid(self):
    """Test that preview endpoint returns 404 for invalid/non-existent scene UUID."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    response = _post_previews(self.client, "00000000-0000-0000-0000-000000000000")

    self.assertEqual(response.status_code, 404)
    result = json.loads(response.content)
    self.assertIn("error", result)

  def test_unauthenticated_preview_is_rejected(self):
    """Test that unauthenticated requests to preview endpoint are rejected with 403."""
    response = _post_previews(self.client, self.scene.id)

    self.assertEqual(response.status_code, 403)

  def test_preview_includes_bearing_for_canvas_rotation(self):
    """Test that preview response includes map bearing for canvas alignment."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Set scene map_bearing to non-zero value
    self.scene.map_bearing = 45.0
    self.scene.save()

    fake_ways = [
      {
        "type": "footway",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": {"highway": "footway"},
      },
    ]

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=fake_ways):
      response = _post_previews(self.client, self.scene.id)

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertIn("bearing", result)
    self.assertEqual(result["bearing"], 45.0)


class TestOsmRoiPreviewsBounds(TestCase):
  """Verifies the "bounds" param: keeps the full shape of any overlapping ROI, unclipped."""

  def setUp(self):
    self.user = User.objects.create_superuser("test_user", "test_user@intel.com", "testpassword")
    self.scene = Scene.objects.create(
      name="test_scene_geospatial",
      map_type="geospatial",
      output_lla=True,
      map_corners_lla=MAP_CORNERS_LLA,
    )
    trs_matrix = calculateTRSLocal2LLAFromSurfacePoints(MAP_XYZ_CORNERS, MAP_CORNERS_LLA)
    self.scene.trs_matrix = trs_matrix.tolist() if hasattr(trs_matrix, "tolist") else list(trs_matrix)
    self.scene.save()
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})
    self.fake_ways = [
      {
        "type": "residential",
        "coords": [[MAP_CORNERS_LLA[0][0], MAP_CORNERS_LLA[0][1]],
                   [MAP_CORNERS_LLA[1][0], MAP_CORNERS_LLA[1][1]]],
        "tags": {"highway": "residential"},
      },
    ]

  def test_bounds_keeps_full_roi_that_only_partially_overlaps(self):
    """A box that only covers a corner of the road's buffer polygon must not clip it."""
    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=self.fake_ways):
      unbounded = _post_previews(self.client, self.scene.id)
    full_points = json.loads(unbounded.content)["rois"][0]["points"]
    xs = [p[0] for p in full_points]
    ys = [p[1] for p in full_points]
    bounds = {
      "minX": min(xs) - 1, "minY": min(ys) - 1,
      "maxX": (min(xs) + max(xs)) / 2, "maxY": (min(ys) + max(ys)) / 2,
    }

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=self.fake_ways):
      response = _post_previews(self.client, self.scene.id, {"bounds": bounds})

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(len(result["rois"]), 1)
    self.assertEqual(result["rois"][0]["points"], full_points)

  def test_bounds_excludes_roi_with_no_overlap(self):
    far_away_bounds = {"minX": 10000, "minY": 10000, "maxX": 10001, "maxY": 10001}

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry", return_value=self.fake_ways):
      response = _post_previews(self.client, self.scene.id, {"bounds": far_away_bounds})

    self.assertEqual(response.status_code, 200)
    self.assertEqual(json.loads(response.content)["rois"], [])

  def test_invalid_bounds_returns_400(self):
    response = _post_previews(
      self.client, self.scene.id, {"bounds": {"minX": "oops", "minY": 0, "maxX": 10, "maxY": 10}})

    self.assertEqual(response.status_code, 400)
    self.assertIn("error", json.loads(response.content))


class TestOsmRois(TestCase):
  """Verifies osm-rois persists posted ROIs without touching other regions."""

  def setUp(self):
    self.user = User.objects.create_superuser("test_user", "test_user@intel.com", "testpassword")
    self.scene = Scene.objects.create(name="test_scene_accept", map_type="geospatial")
    self.existing_region = Region.objects.create(scene=self.scene, name="manual_roi")
    RegionPoint.objects.create(region=self.existing_region, x=0, y=0, sequence=0)
    RegionPoint.objects.create(region=self.existing_region, x=1, y=0, sequence=1)
    RegionPoint.objects.create(region=self.existing_region, x=1, y=1, sequence=2)
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

  def _post(self, payload, scene_uid=None):
    return self.client.post(
      reverse("osm_rois", kwargs={"scene_uid": scene_uid or self.scene.id}),
      data=json.dumps(payload),
      content_type="application/json",
    )

  def test_accept_creates_regions_and_leaves_existing_ones_untouched(self):
    response = self._post({
      "rois": [{"points": [[1, 1], [2, 1], [2, 2]], "name": "Bike Path", "type": "cycleway"}],
    })

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(len(result["created"]), 1)
    self.assertEqual(result["created"][0]["name"], "Bike Path")

    new_region = Region.objects.get(uuid=result["created"][0]["uuid"])
    self.assertEqual(new_region.scene_id, self.scene.id)
    self.assertEqual(new_region.roi_type, "cycleway")
    self.assertEqual(
      [(p.x, p.y) for p in new_region.points.order_by("sequence")], [(1, 1), (2, 1), (2, 2)])

    # Additive-only: existing region in the scene must be untouched, unlike saveROI's full replace.
    self.assertTrue(Region.objects.filter(pk=self.existing_region.pk).exists())
    self.assertEqual(Region.objects.filter(scene=self.scene).count(), 2)

  def test_accept_requires_nonempty_rois_list(self):
    response = self._post({"rois": []})
    self.assertEqual(response.status_code, 400)

  def test_accept_rejects_roi_with_too_few_points(self):
    response = self._post({"rois": [{"points": [[0, 0], [1, 0]]}]})

    self.assertEqual(response.status_code, 400)
    # Nothing created when one entry in the batch is invalid.
    self.assertEqual(Region.objects.filter(scene=self.scene).count(), 1)

  def test_accept_rejects_unknown_scene(self):
    response = self._post(
      {"rois": [{"points": [[0, 0], [1, 0], [1, 1]]}]},
      scene_uid="00000000-0000-0000-0000-000000000000",
    )
    self.assertEqual(response.status_code, 404)

  def test_unauthenticated_accept_is_rejected(self):
    self.client.logout()
    response = self._post({"rois": [{"points": [[0, 0], [1, 0], [1, 1]]}]})
    self.assertEqual(response.status_code, 403)

  def test_non_superuser_accept_is_rejected(self):
    User.objects.create_user("regular_user", "regular@intel.com", "testpassword")
    self.client.logout()
    self.client.post(reverse("sign_in"), data={"username": "regular_user", "password": "testpassword"})

    response = self._post({"rois": [{"points": [[0, 0], [1, 0], [1, 1]]}]})
    self.assertEqual(response.status_code, 403)

  def test_accept_rejects_uuid_of_existing_region_without_changes(self):
    """Additive-only: a posted uuid that already exists is rejected, and nothing in the batch is created."""
    response = self._post({
      "rois": [
        {"points": [[1, 1], [2, 1], [2, 2]], "name": "new"},
        {"uuid": str(self.existing_region.uuid), "points": [[5, 5], [6, 5], [6, 6]], "name": "overwritten"},
      ],
    })

    self.assertEqual(response.status_code, 409)
    self.assertIn(str(self.existing_region.uuid), json.loads(response.content)["existing"])
    self.existing_region.refresh_from_db()
    self.assertEqual(self.existing_region.name, "manual_roi")
    self.assertEqual(
      [(p.x, p.y) for p in self.existing_region.points.order_by("sequence")], [(0, 0), (1, 0), (1, 1)])
    self.assertEqual(Region.objects.filter(scene=self.scene).count(), 1)

  def test_accept_rejects_duplicate_uuids_in_request(self):
    dup = "11111111-1111-1111-1111-111111111111"
    response = self._post({"rois": [
      {"uuid": dup, "points": [[0, 0], [1, 0], [1, 1]]},
      {"uuid": dup, "points": [[2, 2], [3, 2], [3, 3]]},
    ]})

    self.assertEqual(response.status_code, 400)
    self.assertEqual(Region.objects.filter(scene=self.scene).count(), 1)

  def test_accept_rejects_overlong_name_or_type(self):
    for field, length in (("name", 201), ("type", 151)):
      with self.subTest(field=field):
        response = self._post({"rois": [{"points": [[0, 0], [1, 0], [1, 1]], field: "x" * length}]})
        self.assertEqual(response.status_code, 400)
    self.assertEqual(Region.objects.filter(scene=self.scene).count(), 1)
