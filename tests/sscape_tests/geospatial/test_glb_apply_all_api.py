# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Apply all GLBs endpoint: PUT /scene/{id}/geospatial-glbs/apply-all.

Covers the server-side switch state (Scene.glb_apply_all):
  - ON enables every stored layer and places the scene map from them
  - OFF disables every layer and restores the flat base map
  - A new scene starts with the switch ON
  - ON without a flat base map is rejected (400) and changes nothing
  - Non-bool body (400), non-admin and anonymous callers (403)
  - The scene page renders the stored value, so the switch is restored on reentry
  - The flag follows every layer write (enable, disable, remove, commit, flat map upload):
    True only when the scene has layers and all are enabled
  - ON without layers, ON over an applied GLB, non-geospatial scene (400), unknown scene (404)
  - Data migration 0014: geospatial scenes get the flag from their applied GLB state
"""

import importlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from manager import glb_staging, glb_state
from manager.models import GlbLayer, Scene
from tests.utils.geo_footprint import localFootprintCornersLLA

migration = importlib.import_module('manager.migrations.0014_scene_glb_apply_all')

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"
NO_BASE_MAP_ERROR = 'Scene needs a flat base map (image) before a GLB can be placed'


def _store_layer(scene, anchor, enabled=False, name='stored.glb'):
  """Store the test GLB as a layer of the scene; the layer file is written under MEDIA_ROOT."""
  layer = GlbLayer(scene=scene, anchor=anchor, enabled=enabled, order=scene.glb_layers.count())
  with open(TEST_GLB_FILE, 'rb') as f_src:
    layer.file.save(name, File(f_src), save=False)
  layer.save()
  return layer


class TestGlbApplyAllApi(TransactionTestCase):
  """Tests for PUT /scene/{id}/geospatial-glbs/apply-all."""

  def setUp(self):
    """Create a superuser, a geospatial scene with two stored GLB layers and a flat base map."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="apply_all_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    self.scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    self.scene.save()
    self._set_snapshot_map()

    anchor = {'lat': 37.38, 'lng': -121.96, 'heading_deg': 0.0,
              'footprint_m': {'width': 10.0, 'height': 10.0}}
    self.layer_a = _store_layer(self.scene, anchor, enabled=False, name='a.glb')
    self.layer_b = _store_layer(self.scene, dict(anchor, lat=37.381), enabled=False, name='b.glb')
    # The stored layers are disabled, so the stored flag starts consistent with them
    Scene.objects.filter(pk=self.scene.pk).update(glb_apply_all=False)
    self.scene = Scene.objects.get(pk=self.scene.pk)
    self.client.force_login(self.user)

  def _set_snapshot_map(self):
    """Give the scene a PNG snapshot map, as a geospatial scene has before a GLB is applied."""
    png_path = os.path.join(self.temp_dir.name, 'snap.png')
    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(png_path, format='PNG')
    self.scene.map = 'snap.png'
    with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
      self.scene.save()
    self.scene = Scene.objects.get(pk=self.scene.pk)

  def _url(self):
    return reverse('geospatial_glb_apply_all', kwargs={'scene_uid': self.scene.id})

  def _put(self, payload, user=None):
    """PUT the apply-all endpoint with thumbnail and MQTT side effects stubbed."""
    if user is not None:
      self.client.force_login(user)
    with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
      return self.client.put(self._url(), data=json.dumps(payload), content_type='application/json')

  def test_on_enables_every_layer_and_places_the_map(self):
    """ON: every stored layer is enabled, the scene map is placed and the flag is stored."""
    response = self._put({'apply': True})

    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertTrue(body['glb_apply_all'])
    self.assertEqual(body['state_token'], glb_state.scene_state_token(Scene.objects.get(pk=self.scene.pk)))
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.glb_apply_all)
    self.assertTrue(self.scene.use_glb_map)
    self.assertEqual(body['scene_fields'], glb_state.scene_form_fields(self.scene))
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {True})
    self.assertTrue(self.scene.base_map.name)

  def test_off_disables_every_layer_and_restores_the_base_map(self):
    """OFF: every layer is disabled, the flat base map returns and the flag is stored as False."""
    pre_apply_corners = self.scene.map_corners_lla
    self.assertEqual(self._put({'apply': True}).status_code, 200)

    response = self._put({'apply': False})

    self.assertEqual(response.status_code, 200)
    self.assertFalse(response.json()['glb_apply_all'])
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.glb_apply_all)
    self.assertFalse(self.scene.use_glb_map)
    self.assertEqual(self.scene.map_corners_lla, pre_apply_corners)
    self.assertFalse(self.scene.base_map)
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {False})
    self.assertEqual(response.json()['scene_fields'], glb_state.scene_form_fields(self.scene))

  def test_new_scene_defaults_to_on(self):
    """A scene created without the flag starts with the switch ON."""
    scene = Scene.objects.create(name="fresh_scene", map_type="geospatial_map")

    self.assertTrue(Scene.objects.get(pk=scene.pk).glb_apply_all)

  def test_on_without_flat_base_map_returns_400_and_changes_nothing(self):
    """ON needs a flat base map: 400 with the reason, and the flag and layers stay as they were."""
    Scene.objects.filter(pk=self.scene.pk).update(map='', glb_apply_all=False)

    response = self._put({'apply': True})

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json(), {'error': NO_BASE_MAP_ERROR})
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.glb_apply_all)
    self.assertFalse(self.scene.use_glb_map)
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {False})

  def test_non_bool_apply_returns_400(self):
    """A body whose apply is not a boolean is rejected and the flag is not written."""
    for value in ('yes', 1, None):
      with self.subTest(apply=value):
        response = self._put({'apply': value})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'apply must be a boolean'})
    self.assertFalse(Scene.objects.get(pk=self.scene.pk).glb_apply_all)
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {False})

  def test_non_admin_is_forbidden(self):
    """Authenticated non-admin users cannot change the switch."""
    viewer = User.objects.create_user("viewer", "viewer@intel.com", "pass")

    response = self._put({'apply': True}, user=viewer)

    self.assertEqual(response.status_code, 403)
    self.assertFalse(Scene.objects.get(pk=self.scene.pk).glb_apply_all)
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {False})

  def test_anonymous_is_forbidden(self):
    """Anonymous callers cannot change the switch."""
    self.client.logout()
    with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
      response = self.client.put(self._url(), data=json.dumps({'apply': True}), content_type='application/json')

    self.assertEqual(response.status_code, 403)
    self.assertFalse(Scene.objects.get(pk=self.scene.pk).glb_apply_all)
    self.assertEqual(set(self.scene.glb_layers.values_list('enabled', flat=True)), {False})

  def test_scene_page_restores_the_stored_value(self):
    """Reentry: the scene page renders the switch from the stored value, not from browser state."""
    Scene.objects.filter(pk=self.scene.pk).update(glb_apply_all=False)

    response = self.client.get(reverse('sceneDetail', args=[self.scene.id]))

    self.assertEqual(response.status_code, 200)
    tag = re.search(r'<input[^>]*id="apply-all-glbs"[^>]*>', response.content.decode())
    self.assertIsNotNone(tag)
    self.assertNotIn('checked', tag.group(0))

    Scene.objects.filter(pk=self.scene.pk).update(glb_apply_all=True)
    tag = re.search(r'<input[^>]*id="apply-all-glbs"[^>]*>', self.client.get(reverse('sceneDetail', args=[self.scene.id])).content.decode())
    self.assertIn('checked', tag.group(0))

  @contextmanager
  def _stubbed(self):
    """Stub the thumbnail render and the MQTT update that a scene write triggers."""
    with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
      yield

  def _fresh(self):
    """The scene as stored, as a request would load it."""
    return Scene.objects.get(pk=self.scene.pk)

  def _flag_and_states(self):
    """(glb_apply_all, per-layer enabled states in draw order) as stored."""
    scene = self._fresh()
    return scene.glb_apply_all, list(scene.glb_layers.order_by('order').values_list('enabled', flat=True))

  def _commit_new_layer(self, enable):
    """Commit a new staged GLB as a layer of the scene."""
    upload = SimpleUploadedFile('new.glb', TEST_GLB_FILE.read_bytes(), content_type='model/gltf-binary')
    token = glb_staging.stage_glb(upload)
    anchor = {'lat': 37.38, 'lng': -121.96, 'heading_deg': 0.0}
    with self._stubbed():
      return glb_state.commit_layer(self._fresh(), token, anchor, enable=enable)

  def test_single_layer_enable_and_disable_recompute_the_flag(self):
    """Per-layer enable and disable: the flag is on only while every layer is enabled."""
    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_a, True)
    self.assertEqual(self._flag_and_states(), (False, [True, False]))

    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_b, True)
    self.assertEqual(self._flag_and_states(), (True, [True, True]))

    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_b, False)
    self.assertEqual(self._flag_and_states(), (False, [True, False]))

    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_a, False)
    self.assertEqual(self._flag_and_states(), (False, [False, False]))
    self.assertFalse(self._fresh().use_glb_map)

  def test_rejected_layer_enable_leaves_the_flag_alone(self):
    """Negative: enabling an already enabled layer is rejected and the flag is not rewritten."""
    self.assertEqual(self._put({'apply': True}).status_code, 200)

    with self._stubbed(), self.assertRaises(glb_staging.GlbAlignmentError) as raised:
      glb_state.set_layer_enabled(self._fresh(), self.layer_a, True)

    self.assertEqual(raised.exception.status, 400)
    self.assertEqual(self._flag_and_states(), (True, [True, True]))

  def test_layer_removal_recomputes_the_flag(self):
    """Removing a layer: the flag follows the layers that are left, and is off with none."""
    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_a, True)
    self.assertEqual(self._flag_and_states(), (False, [True, False]))

    with self._stubbed():
      glb_state.remove_layer(self._fresh(), self.layer_b)
    self.assertEqual(self._flag_and_states(), (True, [True]))

    with self._stubbed():
      glb_state.remove_layer(self._fresh(), self.layer_a)
    self.assertEqual(self._flag_and_states(), (False, []))
    self.assertFalse(self._fresh().use_glb_map)

  def test_new_layer_commit_recomputes_the_flag(self):
    """Committing a new layer: a disabled one turns the flag off, an enabled one keeps it on."""
    self.assertEqual(self._put({'apply': True}).status_code, 200)
    self.assertEqual(self._flag_and_states(), (True, [True, True]))

    self._commit_new_layer(enable=True)
    self.assertEqual(self._flag_and_states(), (True, [True, True, True]))

    self._commit_new_layer(enable=False)
    self.assertEqual(self._flag_and_states(), (False, [True, True, True, False]))

  def test_flat_map_upload_over_applied_glb_turns_the_flag_off(self):
    """Uploading a flat map over an applied GLB disables every layer and the flag follows."""
    self.assertEqual(self._put({'apply': True}).status_code, 200)
    png_path = os.path.join(self.temp_dir.name, 'replacement.png')
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(png_path, format='PNG')

    scene = self._fresh()
    scene.map = 'replacement.png'
    with self._stubbed(), patch.object(Scene, 'autoAlignSceneMap'):
      scene.save(send_update_command=False)

    self.assertEqual(self._flag_and_states(), (False, [False, False]))
    self.assertFalse(self._fresh().use_glb_map)

  def test_on_without_layers_is_accepted_and_leaves_the_flag_off(self):
    """ON for a scene with no layers changes nothing: 200, the flag stays off, no GLB is applied."""
    self.scene.glb_layers.all().delete()

    response = self._put({'apply': True})

    self.assertEqual(response.status_code, 200)
    self.assertFalse(response.json()['glb_apply_all'])
    self.assertEqual(self._flag_and_states(), (False, []))
    self.assertFalse(self._fresh().use_glb_map)

  def test_on_while_a_glb_is_already_applied_enables_the_rest(self):
    """ON over an applied GLB enables the other layers and keeps the base map snapshot."""
    with self._stubbed():
      glb_state.set_layer_enabled(self._fresh(), self.layer_a, True)
    applied = self._fresh()
    self.assertTrue(applied.use_glb_map)
    base_map_name = applied.base_map.name
    self.assertTrue(base_map_name)

    response = self._put({'apply': True})

    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()['glb_apply_all'])
    self.assertEqual(self._flag_and_states(), (True, [True, True]))
    scene = self._fresh()
    self.assertTrue(scene.use_glb_map)
    self.assertEqual(scene.base_map.name, base_map_name)
    self.assertTrue(scene.map.name.endswith('.glb'))

  def test_non_geospatial_scene_returns_400(self):
    """A scene that is not a geospatial map is rejected and left unchanged."""
    other = Scene.objects.create(name="flat_scene", map_type="map_upload")

    with self._stubbed():
      response = self.client.put(
        reverse('geospatial_glb_apply_all', kwargs={'scene_uid': other.id}),
        data=json.dumps({'apply': False}), content_type='application/json')

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json(), {'error': 'Scene map type must be geospatial_map'})
    self.assertTrue(Scene.objects.get(pk=other.pk).glb_apply_all)

  def test_unknown_scene_returns_404(self):
    """A scene uid that does not exist returns 404."""
    with self._stubbed():
      response = self.client.put(
        reverse('geospatial_glb_apply_all', kwargs={'scene_uid': uuid.uuid4()}),
        data=json.dumps({'apply': True}), content_type='application/json')

    self.assertEqual(response.status_code, 404)
    self.assertEqual(response.json(), {'error': 'Scene not found'})


class TestGlbApplyAllMigration(TransactionTestCase):
  """Data migration 0014 sets the flag of existing scenes from their GLB state."""

  def _scene(self, name, map_type='geospatial_map', use_glb_map=False, layers=(), flag=True):
    """A scene with one stored layer per enabled state in layers; use_glb_map is set directly."""
    scene = Scene.objects.create(name=name, map_type=map_type)
    Scene.objects.filter(pk=scene.pk).update(use_glb_map=use_glb_map, glb_apply_all=flag)
    for order, enabled in enumerate(layers):
      GlbLayer.objects.create(scene=scene, order=order, enabled=enabled, file=f'{name}_{order}.glb', anchor={})
    return scene

  def _flag(self, scene):
    return Scene.objects.get(pk=scene.pk).glb_apply_all

  def test_flag_is_on_only_for_geospatial_scenes_with_the_glb_applied(self):
    """Geospatial scenes: on when applied with every layer enabled, off in every other case."""
    applied = self._scene('applied', use_glb_map=True, layers=(True, True))
    partly = self._scene('partly', use_glb_map=True, layers=(True, False))
    not_applied = self._scene('not-applied', use_glb_map=False, layers=(False,))
    only_stored = self._scene('only-stored', use_glb_map=False, layers=(True,))
    no_layers = self._scene('no-layers', use_glb_map=True)
    without_glb = self._scene('without-glb')

    migration.set_glb_apply_all(django_apps, None)

    self.assertTrue(self._flag(applied))
    for scene in (partly, not_applied, only_stored, no_layers, without_glb):
      self.assertFalse(self._flag(scene), scene.name)

  def test_scenes_of_other_map_types_are_not_touched(self):
    """Non-geospatial scenes have no switch: both stored values survive the migration."""
    on = self._scene('other-on', map_type='map_upload', flag=True)
    off = self._scene('other-off', map_type='map_upload', flag=False)

    migration.set_glb_apply_all(django_apps, None)

    self.assertTrue(self._flag(on))
    self.assertFalse(self._flag(off))

  def test_reverse_is_a_noop(self):
    """The reverse leaves the data as it is."""
    scene = self._scene('reverse', use_glb_map=True, layers=(True,), flag=True)

    self.assertIsNone(migration.keep_glb_apply_all(django_apps, None))

    self.assertTrue(self._flag(scene))
