# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from rest_framework.test import APIRequestFactory

from manager import api


@pytest.mark.parametrize(
  ("remote_addr", "expected"),
  [
    ("127.0.0.1", True),
    ("::1", True),
    ("192.0.2.1", False),
    ("not-an-ip", False),
    (None, False),
  ],
)
def test_is_loopback_request(remote_addr, expected):
  request = APIRequestFactory().get(
    "/api/v1/health",
    **({"REMOTE_ADDR": remote_addr} if remote_addr else {}),
  )
  # handle the case where REMOTE_ADDR is not set in request.META
  if not remote_addr:
    request.META.pop("REMOTE_ADDR", None)

  assert api.is_loopback_request(request) is expected


@pytest.mark.parametrize("view_class", [api.ServiceHealth, api.DatabaseReady])
def test_internal_endpoints_reject_non_loopback_requests(view_class):
  request = APIRequestFactory().get(
    "/api/v1/health",
    REMOTE_ADDR="192.0.2.1",
  )

  with patch.object(view_class, "checkDatabase") as check_database:
    response = view_class.as_view()(request)

  assert response.status_code == 403
  check_database.assert_not_called()


def test_database_ready_allows_loopback_request():
  request = APIRequestFactory().get(
    "/api/v1/database-ready",
    REMOTE_ADDR="127.0.0.1",
  )
  database_status = Mock(is_ready=True)

  with patch.object(api.DatabaseReady, "checkDatabase", return_value=True), \
       patch.object(api.DatabaseStatus.objects, "first", return_value=database_status), \
       patch.object(api.User.objects, "count", return_value=1):
    response = api.DatabaseReady.as_view()(request)

  assert response.status_code == 200
  assert response.data == {"databaseReady": True}


def test_service_health_allows_loopback_request():
  request = APIRequestFactory().get(
    "/api/v1/health",
    REMOTE_ADDR="127.0.0.1",
  )
  database_status = Mock(is_ready=True)

  with patch.object(api.ServiceHealth, "checkDatabase", return_value=True), \
       patch.object(api.DatabaseStatus.objects, "first", return_value=database_status), \
       patch.object(api.User.objects, "count", return_value=1):
    response = api.ServiceHealth.as_view()(request)

  assert response.status_code == 200
  assert response.data["status"] == "healthy"


@pytest.mark.parametrize(
  ("resolver_id", "expected_status", "expected_result"),
  [
    ("resolver-a", 200, "allow"),
    ("resolver-b", 403, "deny"),
  ],
)
def test_positioning_status_write_is_bound_to_configured_resolver(
  resolver_id, expected_status, expected_result,
):
  request = Mock(data={
    "username": "positioning",
    "topic": f"scenescape/positioning/status/{resolver_id}",
    "acc": api.WRITE_ONLY,
  })
  user = Mock(is_superuser=False)
  acl = Mock(topic="POSITIONING_STATUS", access=api.WRITE_ONLY)
  user_acls = MagicMock()
  user_acls.exists.return_value = True
  user_acls.__iter__.return_value = iter([acl])

  with patch.dict("os.environ", {"POSITIONING_RESOLVER_ID": "resolver-a"}), \
       patch.object(api.User.objects, "get", return_value=user), \
       patch.object(api.PubSubACL.objects, "filter", return_value=user_acls):
    response = api.ACLCheck().post(request)

  assert response.status_code == expected_status
  assert response.data["result"] == expected_result


def _write_manifest(tmp_path, manifest, name="assignments.json"):
  path = tmp_path / name
  path.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest),
                  encoding="utf-8")
  return str(path)


def _pose_acl_check(username, topic, acls, environ, access=api.WRITE_ONLY):
  request = Mock(data={"username": username, "topic": topic, "acc": access})
  user = Mock(is_superuser=False)
  user_acls = MagicMock()
  user_acls.exists.return_value = True
  user_acls.__iter__.return_value = iter(
    [Mock(topic=name, access=api.WRITE_ONLY) for name in acls])

  with patch.dict("os.environ", environ, clear=False), \
       patch.object(api.User.objects, "get", return_value=user), \
       patch.object(api.PubSubACL.objects, "filter", return_value=user_acls):
    return api.ACLCheck().post(request)


@pytest.mark.parametrize(
  ("topic", "acls", "expected_status", "expected_result"),
  [
    ("scenescape/positioning/pose/cam-a", ["POSITIONING_POSE", "POSITIONING_STATUS"], 200, "allow"),
    ("scenescape/positioning/pose/cam-a", ["POSITIONING_STATUS"], 403, "deny"),
    ("scenescape/data/camera/cam-a", ["POSITIONING_POSE", "POSITIONING_STATUS"], 403, "deny"),
    ("scenescape/positioning/pose/cam-a/extra", ["POSITIONING_POSE"], 403, "deny"),
  ],
)
def test_positioning_pose_write_requires_pose_topic_and_explicit_acl(
  tmp_path, topic, acls, expected_status, expected_result,
):
  environ = {"POSITIONING_RESOLVER_ID": "resolver-a",
             "POSITIONING_ASSIGNMENTS_FILE": _write_manifest(tmp_path, {"cam-a": "resolver-a"})}
  response = _pose_acl_check("positioning", topic, acls, environ)

  assert response.status_code == expected_status
  assert response.data["result"] == expected_result


@pytest.mark.parametrize("username", ["positioning", "pose-publisher"])
@pytest.mark.parametrize(
  ("source_id", "access", "expected_status"),
  [
    ("cam-a", api.WRITE_ONLY, 200),
    ("cam-b", api.WRITE_ONLY, 403),       # assigned to another resolver
    ("cam-z", api.WRITE_ONLY, 403),       # not in the manifest
    ("+", api.WRITE_ONLY, 403),
    ("cam-b", api.READ_AND_WRITE, 403),
    ("cam-z", api.READ_AND_WRITE, 403),
  ],
)
def test_pose_write_is_bound_to_sources_assigned_to_the_resolver(
  tmp_path, username, source_id, access, expected_status,
):
  manifest = {"$comment": "test", "cam-a": "resolver-a", "cam-b": "resolver-b"}
  environ = {"POSITIONING_RESOLVER_ID": "resolver-a",
             "POSITIONING_ASSIGNMENTS_FILE": _write_manifest(tmp_path, manifest)}
  response = _pose_acl_check(username, f"scenescape/positioning/pose/{source_id}",
                             ["POSITIONING_POSE"], environ, access=access)

  assert response.status_code == expected_status


@pytest.mark.parametrize(
  "manifest",
  [
    None,  # POSITIONING_ASSIGNMENTS_FILE not set
    "missing",
    "{not json",
    '["cam-a"]',
    '{"cam-a": "resolver/a"}',
    '{"cam-a": ""}',
  ],
)
def test_pose_write_is_denied_without_a_valid_manifest(tmp_path, monkeypatch, manifest):
  monkeypatch.delenv("POSITIONING_ASSIGNMENTS_FILE", raising=False)
  environ = {"POSITIONING_RESOLVER_ID": "resolver-a"}
  if manifest == "missing":
    environ["POSITIONING_ASSIGNMENTS_FILE"] = str(tmp_path / "absent.json")
  elif manifest is not None:
    environ["POSITIONING_ASSIGNMENTS_FILE"] = _write_manifest(tmp_path, manifest)

  response = _pose_acl_check(
    "positioning", "scenescape/positioning/pose/cam-a", ["POSITIONING_POSE"], environ)

  assert response.status_code == 403
  assert response.data["result"] == "deny"


def test_pose_write_follows_manifest_changes(tmp_path):
  path = _write_manifest(tmp_path, {"cam-a": "resolver-a"})
  environ = {"POSITIONING_RESOLVER_ID": "resolver-a", "POSITIONING_ASSIGNMENTS_FILE": path}
  topic = "scenescape/positioning/pose/cam-a"
  assert _pose_acl_check("positioning", topic, ["POSITIONING_POSE"], environ).status_code == 200

  replacement = _write_manifest(tmp_path, {"cam-a": "resolver-b"}, name="next.json")
  os.replace(replacement, path)
  assert _pose_acl_check("positioning", topic, ["POSITIONING_POSE"], environ).status_code == 403
