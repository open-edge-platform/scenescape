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


class TestPreviewRoisFromOsm(TestCase):
  """Verifies the preview-rois-from-osm endpoint: auth, calibration check, and geometry conversion."""

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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),  # v2: bbox read from scene model
        content_type="application/json",
      )

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

    # Each ROI should have points, type, uuid, checked, tags, and width_m fields
    for roi in result["rois"]:
      self.assertIn("points", roi)
      self.assertIn("type", roi)
      self.assertIn("uuid", roi)  # temporary tracking UUID
      self.assertIn("checked", roi)  # default checked state
      self.assertIn("tags", roi)  # full OSM tags
      self.assertIn("width_m", roi)  # computed or extracted width
      self.assertTrue(roi["checked"])  # Should default to True
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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    widths = {roi["type"]: roi["width_m"] for roi in result["rois"]}
    self.assertEqual(widths["tertiary"], 2 * 3.5)
    self.assertEqual(widths["unclassified"], 2 * 3.5)

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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )

    mock_query.assert_called_once()  # Stale cache must not be reused
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(len(result["rois"]), 1)
    self.assertIn("Grójecka", result["rois"][0]["name"])
    self.assertEqual(result["rois"][0]["width_m"], 3 * 3.5)  # lanes-based width

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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )

    mock_query.assert_called_once()  # List-format cache must not be reused
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(result["rois"][0]["width_m"], 3 * 3.5)  # lanes-based width, not the generic default

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
      response1 = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )
      response2 = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )

    self.assertEqual(response1.status_code, 200)
    self.assertEqual(response2.status_code, 200)
    mock_query.assert_called_once()  # Second call must reuse the cached ways

    self.scene.refresh_from_db()
    # Verify cache was populated
    self.assertIsNotNone(self.scene.osm_ways_cache)
    self.assertEqual(len(self.scene.osm_ways_cache), len(fake_ways))

  def test_preview_requires_scene_id(self):
    """Test that preview endpoint rejects missing scene ID."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    response = self.client.post(
      reverse("preview_rois_from_osm"),
      data=json.dumps({}),  # Missing scene
      content_type="application/json",
    )

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    self.assertIn("error", result)

  def test_preview_requires_map_corners_lla(self):
    """Test that preview endpoint rejects scene without map_corners_lla set (v3: bbox derived from it)."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    # Create scene without map_corners_lla set
    scene_no_corners = Scene.objects.create(
      name="test_scene_no_corners",
      map_type="geospatial",
      output_lla=True,
    )

    response = self.client.post(
      reverse("preview_rois_from_osm"),
      data=json.dumps({"scene": str(scene_no_corners.id)}),
      content_type="application/json",
    )

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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(scene_no_trs.id)}),
        content_type="application/json",
      )

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    self.assertIn("error", result)
    self.assertIn("trs_matrix", result["error"])
    # Verify we didn't call the upstream query (fail fast)
    mock_query.assert_not_called()

  def test_preview_handles_osm_query_error(self):
    """Test that preview endpoint surfaces upstream OSM query errors."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    from manager.osm_query import OsmQueryError

    with patch("manager.osm_roi.osm_query.query_osm_ways_geometry") as mock_query:
      mock_query.side_effect = OsmQueryError("API key missing")

      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),  # v2: bbox from model
        content_type="application/json",
      )

    self.assertEqual(response.status_code, 400)
    result = json.loads(response.content)
    self.assertIn("API key", result["error"])

  def test_preview_rejects_invalid_scene_uuid(self):
    """Test that preview endpoint returns 404 for invalid/non-existent scene UUID."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "testpassword"})

    response = self.client.post(
      reverse("preview_rois_from_osm"),
      data=json.dumps({"scene": "00000000-0000-0000-0000-000000000000"}),  # v2: bbox from model
      content_type="application/json",
    )

    self.assertEqual(response.status_code, 404)
    result = json.loads(response.content)
    self.assertIn("error", result)

  def test_unauthenticated_preview_is_rejected(self):
    """Test that unauthenticated requests to preview endpoint are rejected with 403."""
    response = self.client.post(
      reverse("preview_rois_from_osm"),
      data=json.dumps({"scene": str(self.scene.id)}),  # v2: bbox from model
      content_type="application/json",
    )

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
      response = self.client.post(
        reverse("preview_rois_from_osm"),
        data=json.dumps({"scene": str(self.scene.id)}),
        content_type="application/json",
      )

    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertIn("bearing", result)
    self.assertEqual(result["bearing"], 45.0)
