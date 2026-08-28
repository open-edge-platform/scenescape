# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models
import manager.fields


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0003_add_cached_geometries_to_childscene'),
  ]

  operations = [
    migrations.CreateModel(
      name='Radar',
      fields=[
        ('sensor_ptr', models.OneToOneField(
          auto_created=True,
          on_delete=models.deletion.CASCADE,
          parent_link=True,
          primary_key=True,
          serialize=False,
          to='manager.sensor',
        )),
        ('transforms', manager.fields.ListField(blank=True, default=list)),
        ('transform_type', models.CharField(
          choices=[
            ('matrix', 'Matrix'),
            ('euler', 'Euler Angles'),
            ('quaternion', 'Quaternion'),
          ],
          default='euler',
          max_length=26,
        )),
      ],
      bases=('manager.sensor',),
    ),
    migrations.AlterField(
      model_name='sensor',
      name='type',
      field=models.CharField(
        choices=[
          ('camera', 'Camera'),
          ('generic', 'generic'),
          ('radar', 'Radar'),
        ],
        max_length=200,
      ),
    ),
    migrations.AlterField(
      model_name='pubsubacl',
      name='topic',
      field=models.CharField(
        choices=[
          ('CHANNEL', 'CHANNEL'),
          ('CMD_CAMERA', 'CMD_CAMERA'),
          ('CMD_DATABASE', 'CMD_DATABASE'),
          ('CMD_KUBECLIENT', 'CMD_KUBECLIENT'),
          ('CMD_SCENE_UPDATE', 'CMD_SCENE_UPDATE'),
          ('DATA_AUTOCALIB_CAM_POSE', 'DATA_AUTOCALIB_CAM_POSE'),
          ('DATA_CAMERA', 'DATA_CAMERA'),
          ('DATA_EXTERNAL', 'DATA_EXTERNAL'),
          ('DATA_RADAR', 'DATA_RADAR'),
          ('DATA_REGION', 'DATA_REGION'),
          ('DATA_REGULATED', 'DATA_REGULATED'),
          ('DATA_SCENE', 'DATA_SCENE'),
          ('DATA_SENSOR', 'DATA_SENSOR'),
          ('EVENT', 'EVENT'),
          ('IMAGE_CALIBRATE', 'IMAGE_CALIBRATE'),
          ('IMAGE_CAMERA', 'IMAGE_CAMERA'),
          ('SYS_CHILDSCENE_STATUS', 'SYS_CHILDSCENE_STATUS'),
          ('ANALYTICS_CLUSTERS', 'ANALYTICS_CLUSTERS'),
          ('DATA_CHILD_TRIPWIRES', 'DATA_CHILD_TRIPWIRES'),
          ('DATA_CHILD_ROIS', 'DATA_CHILD_ROIS'),
        ],
        max_length=50,
      ),
    ),
  ]
