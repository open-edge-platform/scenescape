# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Manager ui-bootstrap payloads (chrome off-k8s regression)."""

from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager.services.ui_bootstrap import (
  build_chrome_bootstrap,
  build_models_directory_bootstrap,
  user_auth_token,
)

TEST_NAME = "NEX-T18750"


@override_settings(KUBERNETES_SERVICE_HOST=False)
class ChromeBootstrapOffKubernetesTests(TestCase):
  """Compose demos are not Kubernetes; chrome must not reverse model_list."""

  def setUp(self):
    self.factory = RequestFactory()
    self.user = User.objects.create_superuser(
      "chrome_user", "chrome@example.com", "testpassword",
    )

  def test_build_chrome_bootstrap_omits_models_url(self):
    request = self.factory.get("/")
    request.user = self.user
    payload = build_chrome_bootstrap(request)
    self.assertFalse(payload["isKubernetes"])
    self.assertNotIn("models", payload["urls"])
    self.assertEqual(payload["urls"]["cameras"], reverse("cam_list"))

  def test_ui_bootstrap_chrome_api_returns_200(self):
    client = APIClient()
    client.force_authenticate(user=self.user)
    response = client.get("/api/v1/ui-bootstrap/", {"page": "chrome"})
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("models", response.data["urls"])
    self.assertTrue(response.data["authenticated"])

  def test_ui_bootstrap_chrome_anonymous_ok(self):
    client = APIClient()
    response = client.get("/api/v1/ui-bootstrap/", {"page": "chrome"})
    self.assertEqual(response.status_code, 200)
    self.assertFalse(response.data["authenticated"])
    self.assertNotIn("models", response.data["urls"])


@override_settings(KUBERNETES_SERVICE_HOST=False)
class AuthTokenProvisionTests(TestCase):
  def test_user_auth_token_creates_missing_token(self):
    user = User.objects.create_user("tok_user", "tok@example.com", "pw")
    self.assertFalse(Token.objects.filter(user=user).exists())
    key = user_auth_token(user)
    self.assertTrue(key)
    self.assertTrue(Token.objects.filter(user=user, key=key).exists())

  def test_user_auth_token_anonymous_empty(self):
    self.assertEqual(user_auth_token(AnonymousUser()), "")
    self.assertEqual(user_auth_token(None), "")


@override_settings(KUBERNETES_SERVICE_HOST=False)
class ModelsDirectoryBootstrapTests(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    self.user = User.objects.create_superuser(
      "models_user", "models@example.com", "testpassword",
    )

  def test_models_bootstrap_includes_auth_token(self):
    request = self.factory.get("/")
    request.user = self.user
    payload = build_models_directory_bootstrap(request)
    self.assertTrue(payload["isSuperuser"])
    self.assertTrue(payload["authToken"])
    self.assertEqual(payload["authToken"], user_auth_token(self.user))
