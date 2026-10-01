# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for geospatial child transform preview UUID validation."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

TEST_NAME = "NEX-T18752"


class PreviewGeospatialChildTransformTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_superuser(
      "geo_user", "geo@example.com", "testpassword",
    )
    self.token = Token.objects.create(user=self.user)
    self.client = APIClient()
    self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
    self.url = "/api/v1/childscene/preview-geospatial-transform/"

  def test_malformed_parent_uuid_returns_400(self):
    response = self.client.post(
      self.url,
      {"parent": "not-a-uuid", "child": "11111111-1111-1111-1111-111111111111"},
      format="json",
    )
    self.assertEqual(response.status_code, 400)
    self.assertIn("parent", response.data)
    self.assertNotIn("child", response.data)

  def test_malformed_child_uuid_returns_400(self):
    response = self.client.post(
      self.url,
      {"parent": "11111111-1111-1111-1111-111111111111", "child": "bad"},
      format="json",
    )
    self.assertEqual(response.status_code, 400)
    self.assertIn("child", response.data)

  def test_missing_fields_return_400(self):
    response = self.client.post(self.url, {}, format="json")
    self.assertEqual(response.status_code, 400)
    self.assertIn("parent", response.data)
    self.assertIn("child", response.data)

  def test_unknown_scenes_return_404(self):
    response = self.client.post(
      self.url,
      {
        "parent": "11111111-1111-1111-1111-111111111111",
        "child": "22222222-2222-2222-2222-222222222222",
      },
      format="json",
    )
    self.assertEqual(response.status_code, 404)
