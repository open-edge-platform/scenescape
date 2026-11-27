# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Child-link REST endpoints: admin-only writes, batch attach responses, and placed-child creation."""

import json
import uuid

import numpy as np
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from manager import placement
from manager.models import ChildScene, Scene
from tests.utils.geo_footprint import localFootprintCornersLLA

PARENT_CORNERS = localFootprintCornersLLA(
  center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0, width_m=100.0, height_m=80.0,
).tolist()


def _post(client, url, payload):
  return client.post(url, data=json.dumps(payload), content_type="application/json")


class TestChildLinkViews(TestCase):

  def setUp(self):
    self.admin = User.objects.create_superuser("admin", "admin@intel.com", "adminpass")
    self.viewer = User.objects.create_user("viewer", "viewer@intel.com", "viewerpass")
    self.parent = Scene.objects.create(name="city", map_type="geospatial_map", map_corners_lla=PARENT_CORNERS)
    self.block = Scene.objects.create(
      name="block",
      map_type="geospatial_map",
      map_corners_lla=placement.footprint_corners_lla(np.array(PARENT_CORNERS), 10.0, 10.0, 20.0, 20.0),
    )
    self.links_url = reverse("child_links", kwargs={"scene_uid": self.parent.pk})
    self.placed_url = reverse("child_links_placed", kwargs={"scene_uid": self.parent.pk})

  def test_anonymous_user_cannot_attach(self):
    response = _post(self.client, self.links_url, {"children": [{"child": str(self.block.pk)}]})

    self.assertIn(response.status_code, (401, 403))
    self.assertFalse(ChildScene.objects.exists())

  def test_viewer_can_read_but_not_attach(self):
    self.client.force_login(self.viewer)

    read = self.client.get(self.links_url)
    write = _post(self.client, self.links_url, {"children": [{"child": str(self.block.pk)}]})

    self.assertEqual(read.status_code, 200)
    self.assertEqual(json.loads(read.content), {"results": []})
    self.assertEqual(write.status_code, 403)

  def test_admin_attaches_batch_then_reports_unchanged(self):
    self.client.force_login(self.admin)
    payload = {"children": [{"child": str(self.block.pk)}]}

    first = _post(self.client, self.links_url, payload)
    second = _post(self.client, self.links_url, payload)

    self.assertEqual(first.status_code, 200)
    self.assertEqual(json.loads(first.content)["results"][0]["status"], "created")
    self.assertEqual(json.loads(second.content)["results"][0]["status"], "unchanged")
    status = json.loads(self.client.get(self.links_url).content)["results"]
    self.assertEqual(status[0]["child"], str(self.block.pk))
    self.assertFalse(status[0]["stale"])

  def test_empty_batch_is_rejected(self):
    self.client.force_login(self.admin)

    response = _post(self.client, self.links_url, {"children": []})

    self.assertEqual(response.status_code, 400)

  def test_unknown_child_reports_per_item_error_and_writes_nothing(self):
    self.client.force_login(self.admin)
    missing = str(uuid.uuid4())

    response = _post(self.client, self.links_url, {"children": [{"child": str(self.block.pk)}, {"child": missing}]})

    self.assertEqual(response.status_code, 400)
    self.assertEqual(json.loads(response.content)["errors"][0]["child"], missing)
    self.assertFalse(ChildScene.objects.exists())

  def test_unknown_parent_is_not_found(self):
    self.client.force_login(self.admin)
    url = reverse("child_links", kwargs={"scene_uid": uuid.uuid4()})

    response = _post(self.client, url, {"children": [{"child": str(self.block.pk)}]})

    self.assertEqual(response.status_code, 404)

  def test_admin_creates_placed_child(self):
    self.client.force_login(self.admin)

    response = _post(self.client, self.placed_url, {"name": "Block B", "x": 0, "y": 0, "width": 10, "height": 10})

    self.assertEqual(response.status_code, 201)
    body = json.loads(response.content)
    self.assertEqual(body["name"], "Block B")
    self.assertTrue(Scene.objects.filter(pk=body["child"]).exists())
    self.assertLess(body["residual_m"], 0.05)

  def test_placed_child_rejects_non_numeric_rectangle(self):
    self.client.force_login(self.admin)

    response = _post(self.client, self.placed_url, {"name": "Block C", "x": 0, "y": 0, "width": "wide", "height": 10})

    self.assertEqual(response.status_code, 400)
    self.assertFalse(Scene.objects.filter(name="Block C").exists())
