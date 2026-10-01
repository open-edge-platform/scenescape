# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Serializer and refresh tests for geospatial child-scene linking."""

import io
import json
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.authtoken.models import Token

from manager.models import ChildScene, Scene
from manager.serializers import ChildSceneSerializer
from scene_common.options import (
    EULER, TRANSFORM_SOURCE_GEOSPATIAL, TRANSFORM_SOURCE_MANUAL,
    TRANSFORM_SOURCE_VISUAL)

TEST_NAME = "NEX-T22111"

MAP_CORNERS_LLA = [
    [37.38685435, -121.96408120, 8.0],
    [37.38693520, -121.96408120, 8.0],
    [37.38693520, -121.96413896, 8.0],
    [37.38685435, -121.96413896, 8.0],
]
SHIFTED_CORNERS_LLA = [
    [37.38685435, -121.96420000, 8.0],
    [37.38693520, -121.96420000, 8.0],
    [37.38693520, -121.96425776, 8.0],
    [37.38685435, -121.96425776, 8.0],
]


def _png_bytes(width=90, height=64):
  buffer = io.BytesIO()
  Image.new('RGB', (width, height), color=(80, 80, 80)).save(buffer, format='PNG')
  return buffer.getvalue()


def _map_upload(name='map.png'):
  return SimpleUploadedFile(name, _png_bytes(), content_type='image/png')


def _geo_scene(name, corners=None):
  scene = Scene(
      name=name,
      output_lla=True,
      map_corners_lla=corners or MAP_CORNERS_LLA,
      scale=10.0,
  )
  scene.map.save(f'{name}.png', _map_upload(f'{name}.png'), save=False)
  scene.save()
  return scene


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GeospatialChildLinkSerializerTest(TestCase):
  def setUp(self):
    self.user = User.objects.create_superuser(
        'geo_user', 'geo_user@intel.com', 'testpassword')
    self.token = Token.objects.create(user=self.user)
    self.parent = _geo_scene('geo_parent')
    self.child = _geo_scene('geo_child')
    self.plain = Scene.objects.create(name='plain_child', scale=10.0)

  def _auth_headers(self):
    return {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}

  def test_geospatial_source_fills_euler_transform(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
        'transform_source': TRANSFORM_SOURCE_GEOSPATIAL,
    })
    self.assertTrue(serializer.is_valid(), serializer.errors)
    link = serializer.save()
    self.assertEqual(link.transform_source, TRANSFORM_SOURCE_GEOSPATIAL)
    self.assertEqual(link.transform_type, EULER)
    self.assertAlmostEqual(link.transform1, 0.0, delta=0.2)
    self.assertAlmostEqual(link.transform2, 0.0, delta=0.2)
    self.assertAlmostEqual(link.transform7, 1.0, delta=0.1)

  def test_manual_zeros_are_preserved(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
        'transform_source': TRANSFORM_SOURCE_MANUAL,
        'transform_type': EULER,
        'transform1': 0,
        'transform2': 0,
        'transform3': 0,
        'transform4': 0,
        'transform5': 0,
        'transform6': 0,
        'transform7': 1,
        'transform8': 1,
        'transform9': 1,
    })
    self.assertTrue(serializer.is_valid(), serializer.errors)
    link = serializer.save()
    self.assertEqual(link.transform_source, TRANSFORM_SOURCE_MANUAL)
    self.assertEqual(link.transform1, 0)
    self.assertEqual(link.transform2, 0)
    self.assertEqual(link.transform3, 0)

  def test_geospatial_ineligible_child_is_rejected(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.plain.pk,
        'child_type': 'local',
        'transform_source': TRANSFORM_SOURCE_GEOSPATIAL,
    })
    self.assertFalse(serializer.is_valid())
    self.assertIn('child', serializer.errors)

  def test_geospatial_ineligible_parent_is_rejected(self):
    bare_parent = Scene.objects.create(name='bare_parent')
    serializer = ChildSceneSerializer(data={
        'parent': bare_parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
        'transform_source': TRANSFORM_SOURCE_GEOSPATIAL,
    })
    self.assertFalse(serializer.is_valid())
    self.assertIn('parent', serializer.errors)

  def test_omitted_transform_auto_computes_when_both_georeferenced(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
    })
    self.assertTrue(serializer.is_valid(), serializer.errors)
    link = serializer.save()
    self.assertEqual(link.transform_source, TRANSFORM_SOURCE_GEOSPATIAL)
    self.assertEqual(link.transform_type, EULER)

  def test_scene_corner_update_refreshes_geospatial_links_only(self):
    geo_link = ChildScene.objects.create(
        parent=self.parent,
        child=self.child,
        child_type='local',
        transform_source=TRANSFORM_SOURCE_GEOSPATIAL,
        transform_type=EULER,
        transform1=0, transform2=0, transform3=0,
        transform4=0, transform5=0, transform6=0,
        transform7=1, transform8=1, transform9=1,
    )
    other_child = _geo_scene('manual_child')
    manual_link = ChildScene.objects.create(
        parent=self.parent,
        child=other_child,
        child_type='local',
        transform_source=TRANSFORM_SOURCE_MANUAL,
        transform_type=EULER,
        transform1=5, transform2=6, transform3=0,
        transform4=0, transform5=0, transform6=0,
        transform7=1, transform8=1, transform9=1,
    )

    self.child.map_corners_lla = SHIFTED_CORNERS_LLA
    self.child.save()
    geo_link.refresh_from_db()
    manual_link.refresh_from_db()

    self.assertEqual(geo_link.transform_source, TRANSFORM_SOURCE_GEOSPATIAL)
    offset = (geo_link.transform1 ** 2 + geo_link.transform2 ** 2) ** 0.5
    self.assertGreater(offset, 1.0, f"expected geospatial refresh to move the child, got tx={geo_link.transform1} ty={geo_link.transform2}")
    self.assertEqual(manual_link.transform1, 5)
    self.assertEqual(manual_link.transform2, 6)

  def test_preview_endpoint_returns_pose(self):
    response = self.client.post(
        '/api/v1/childscene/preview-geospatial-transform/',
        data=json.dumps({
            'parent': str(self.parent.pk),
            'child': str(self.child.pk),
        }),
        content_type='application/json',
        **self._auth_headers())
    self.assertEqual(response.status_code, 200, response.content)
    body = response.json()
    self.assertIn('translation', body)
    self.assertIn('rotation', body)
    self.assertIn('scale', body)
    self.assertIn('residual_m', body)
    self.assertEqual(len(body['translation']), 3)

  def test_preview_endpoint_rejects_ineligible_child(self):
    response = self.client.post(
        '/api/v1/childscene/preview-geospatial-transform/',
        data=json.dumps({
            'parent': str(self.parent.pk),
            'child': str(self.plain.pk),
        }),
        content_type='application/json',
        **self._auth_headers())
    self.assertEqual(response.status_code, 400)
    self.assertIn('child', response.json())

  def test_visual_source_persists_client_euler(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
        'transform_source': TRANSFORM_SOURCE_VISUAL,
        'transform_type': EULER,
        'transform1': 4.5,
        'transform2': -1.25,
        'transform3': 0.5,
        'transform4': 0,
        'transform5': 0,
        'transform6': 30,
        'transform7': 1,
        'transform8': 1,
        'transform9': 1,
    })
    self.assertTrue(serializer.is_valid(), serializer.errors)
    link = serializer.save()
    self.assertEqual(link.transform_source, TRANSFORM_SOURCE_VISUAL)
    self.assertEqual(link.transform_type, EULER)
    self.assertAlmostEqual(link.transform1, 4.5)
    self.assertAlmostEqual(link.transform2, -1.25)
    self.assertAlmostEqual(link.transform3, 0.5)
    self.assertAlmostEqual(link.transform6, 30)

  def test_scene_corner_update_does_not_refresh_visual_links(self):
    visual_child = _geo_scene('visual_child')
    visual_link = ChildScene.objects.create(
        parent=self.parent,
        child=visual_child,
        child_type='local',
        transform_source=TRANSFORM_SOURCE_VISUAL,
        transform_type=EULER,
        transform1=7, transform2=8, transform3=0,
        transform4=0, transform5=0, transform6=15,
        transform7=1, transform8=1, transform9=1,
    )
    visual_child.map_corners_lla = SHIFTED_CORNERS_LLA
    visual_child.save()
    visual_link.refresh_from_db()
    self.assertEqual(visual_link.transform_source, TRANSFORM_SOURCE_VISUAL)
    self.assertEqual(visual_link.transform1, 7)
    self.assertEqual(visual_link.transform2, 8)
    self.assertEqual(visual_link.transform6, 15)

  def test_unknown_transform_source_is_rejected(self):
    serializer = ChildSceneSerializer(data={
        'parent': self.parent.pk,
        'child': self.child.pk,
        'child_type': 'local',
        'transform_source': 'overlay',
        'transform_type': EULER,
        'transform1': 1,
        'transform2': 0,
        'transform3': 0,
        'transform4': 0,
        'transform5': 0,
        'transform6': 0,
        'transform7': 1,
        'transform8': 1,
        'transform9': 1,
    })
    self.assertFalse(serializer.is_valid())
    self.assertIn('transform_source', serializer.errors)

  def test_preview_endpoint_requires_both_ids(self):
    response = self.client.post(
        '/api/v1/childscene/preview-geospatial-transform/',
        data=json.dumps({'parent': str(self.parent.pk)}),
        content_type='application/json',
        **self._auth_headers())
    self.assertEqual(response.status_code, 400)
    self.assertIn('child', response.json())
