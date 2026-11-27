# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Migration 0013 clears the cached trs_matrix of GLB geospatial scenes only."""

import importlib

import pytest
from django.apps import apps as django_apps

from manager.models import Scene

migration = importlib.import_module('manager.migrations.0013_geospatial_glb_layers')

CACHED = {'trs': 'cached'}


@pytest.mark.django_db
def test_clears_trs_matrix_only_on_geospatial_glb_scenes():
  glb_applied = Scene.objects.create(name='glb-applied', map_type='geospatial_map', output_lla=True,
                                     map='applied.glb', use_glb_map=True, trs_matrix=CACHED)
  glb_map = Scene.objects.create(name='glb-map', map_type='geospatial_map', output_lla=True,
                                 map='legacy.glb', use_glb_map=False, trs_matrix=CACHED)
  plain_map = Scene.objects.create(name='plain-map', map_type='geospatial_map', output_lla=True,
                                   map='plan.png', use_glb_map=False, trs_matrix=CACHED)
  non_geo = Scene.objects.create(name='non-geo', map_type='map_upload', map='other.glb',
                                 use_glb_map=False, trs_matrix=CACHED)

  migration.clear_glb_trs_matrix_migration(django_apps, None)

  for scene in (glb_applied, glb_map):
    scene.refresh_from_db()
    assert scene.trs_matrix is None, scene.name
  for scene in (plain_map, non_geo):
    scene.refresh_from_db()
    assert scene.trs_matrix == CACHED, scene.name
