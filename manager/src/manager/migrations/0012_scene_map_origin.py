# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene map image origin: world coordinates of the 2D map's bottom-left corner."""

import io
import logging
import os

from django.db import migrations, models

log = logging.getLogger(__name__)


def backfill_map_origins(apps, schema_editor):
  """Re-render GLB thumbnails so each stored image matches its stored origin and scale."""
  import numpy as np
  from PIL import Image
  from scene_common.glb_top_view import generateOrthoView

  Scene = apps.get_model('manager', 'Scene')
  Region = apps.get_model('manager', 'Region')
  Tripwire = apps.get_model('manager', 'Tripwire')
  SingletonSensor = apps.get_model('manager', 'SingletonSensor')
  db = schema_editor.connection.alias
  for scene in Scene.objects.using(db).exclude(map='').exclude(map__isnull=True):
    if os.path.splitext(scene.map.name)[1].lower() != '.glb':
      continue
    try:
      img_data, pixels_per_meter, origin = generateOrthoView(scene, scene.map.path)
      buf = io.BytesIO()
      Image.fromarray(np.uint8(img_data)).save(buf, format='PNG')
      # Overwrite in place so source maps that share this thumbnail stay consistent.
      if scene.thumbnail:
        with scene.thumbnail.storage.open(scene.thumbnail.name, 'wb') as f:
          f.write(buf.getvalue())
      else:
        scene.thumbnail.save(f"{scene.name}_2d.png", io.BytesIO(buf.getvalue()), save=False)
    except Exception as exc:  # A broken map must not block the upgrade.
      log.warning("Skipping map origin backfill for scene %s: %s", scene.pk, exc)
      continue
    Scene.objects.using(db).filter(pk=scene.pk).update(
      thumbnail=scene.thumbnail.name, scale=pixels_per_meter,
      map_origin_x=origin[0], map_origin_y=origin[1])
    if not (origin[0] or origin[1]):
      continue
    # Shapes drawn in the 2D view before this upgrade ignored the origin, so they now render shifted.
    regions = Region.objects.using(db).filter(scene=scene.pk).count()
    tripwires = Tripwire.objects.using(db).filter(scene=scene.pk).count()
    areas = SingletonSensor.objects.using(db).filter(scene=scene.pk).exclude(area='scene').count()
    if regions or tripwires or areas:
      log.warning(
        "Scene %s (%s) now has 2D map origin (%.3f, %.3f) m. Its %d region(s), %d tripwire(s) "
        "and %d sensor area(s) keep their stored world coordinates but will appear shifted on "
        "the 2D map; re-check them.",
        scene.pk, scene.name, origin[0], origin[1], regions, tripwires, areas)


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0011_cam_pose_provenance'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='map_origin_x',
      field=models.FloatField(default=0.0, editable=False, verbose_name='Map image origin X (meters)'),
    ),
    migrations.AddField(
      model_name='scene',
      name='map_origin_y',
      field=models.FloatField(default=0.0, editable=False, verbose_name='Map image origin Y (meters)'),
    ),
    migrations.RunPython(backfill_map_origins, migrations.RunPython.noop),
  ]
