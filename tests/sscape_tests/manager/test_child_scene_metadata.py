# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory

from manager import views
from manager.serializers import ChildSceneSerializer


def test_child_scene_metadata_returns_transformed_catalogs():
  scene_id = "b485c77c-8a11-4cc7-a635-1efcaf039e35"
  request = RequestFactory().get(f"/{scene_id}/children/metadata/")
  request.user = SimpleNamespace(is_authenticated=True)
  catalogs = (
      json.dumps([{"uuid": "roi-1"}]),
      json.dumps([{"uuid": "tripwire-1"}]),
      json.dumps([{"title": "sensor-1"}]),
  )

  with patch("manager.views.get_object_or_404"), patch(
      "manager.views.getAllChildrenMetaData", return_value=catalogs
  ) as get_catalogs:
    response = views.child_scene_metadata(request, scene_id)

  assert response.status_code == 200
  assert json.loads(response.content) == {
      "rois": [{"uuid": "roi-1"}],
      "tripwires": [{"uuid": "tripwire-1"}],
      "sensors": [{"title": "sensor-1"}],
  }
  get_catalogs.assert_called_once()


def test_child_scene_metadata_requires_login():
  scene_id = "b485c77c-8a11-4cc7-a635-1efcaf039e35"
  request = RequestFactory().get(f"/{scene_id}/children/metadata/")
  request.user = SimpleNamespace(is_authenticated=False)

  response = views.child_scene_metadata(request, scene_id)

  assert response.status_code == 302


def test_remote_child_catalog_update_notifies_parent():
  from manager.models import sendUpdateCommand

  instance = SimpleNamespace(pk=12, cached_rois=[])
  serializer = ChildSceneSerializer(instance=instance)

  with patch("manager.serializers.ChildScene.objects.filter") as update, patch(
      "manager.serializers.transaction.on_commit"
  ) as commit:
    serializer.update(instance, {"cached_rois": [{"uuid": "roi-1"}]})

  update.assert_called_once_with(pk=instance.pk)
  update.return_value.update.assert_called_once_with(
      cached_rois=[{"uuid": "roi-1"}]
  )
  commit.assert_called_once_with(sendUpdateCommand)