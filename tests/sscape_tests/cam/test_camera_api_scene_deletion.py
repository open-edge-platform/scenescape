# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from manager.api import ListThings
from manager.models import Cam, Scene
from manager.serializers import CamSerializer


TEST_NAME = "NEX-T28215"


class CameraAPISceneDeletionTestCase(TestCase):
  def test_camera_list_serialization_survives_concurrent_scene_deletion(self):
    scene = Scene.objects.create(name='camera_scene')
    Cam.objects.create(sensor_id='camera1', name='Camera 1', scene=scene)

    view = ListThings()
    request = APIRequestFactory().get('/api/v1/cameras')
    view.request = view.initialize_request(request)
    view.args = ('cameras',)

    cameras = list(view.get_queryset())
    scene_id = scene.pk
    scene.delete()

    data = CamSerializer(cameras, many=True).data

    self.assertEqual(data[0]['uid'], 'camera1')
    self.assertEqual(data[0]['scene'], str(scene_id))
