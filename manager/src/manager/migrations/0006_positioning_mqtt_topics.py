# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0005_default_asset3d_objects"),
  ]

  operations = [
    migrations.AlterField(
      model_name="pubsubacl",
      name="topic",
      field=models.CharField(
        choices=[
          ("CHANNEL", "CHANNEL"),
          ("CMD_CAMERA", "CMD_CAMERA"),
          ("CMD_DATABASE", "CMD_DATABASE"),
          ("CMD_KUBECLIENT", "CMD_KUBECLIENT"),
          ("CMD_SCENE_UPDATE", "CMD_SCENE_UPDATE"),
          ("DATA_AUTOCALIB_CAM_POSE", "DATA_AUTOCALIB_CAM_POSE"),
          ("DATA_CAMERA", "DATA_CAMERA"),
          ("DATA_EXTERNAL", "DATA_EXTERNAL"),
          ("DATA_REGION", "DATA_REGION"),
          ("DATA_REGULATED", "DATA_REGULATED"),
          ("DATA_SCENE", "DATA_SCENE"),
          ("DATA_SENSOR", "DATA_SENSOR"),
          ("EVENT", "EVENT"),
          ("IMAGE_CALIBRATE", "IMAGE_CALIBRATE"),
          ("IMAGE_CAMERA", "IMAGE_CAMERA"),
          ("POINTCLOUD_CAMERA", "POINTCLOUD_CAMERA"),
          ("SYS_CHILDSCENE_STATUS", "SYS_CHILDSCENE_STATUS"),
          ("ANALYTICS_CLUSTERS", "ANALYTICS_CLUSTERS"),
          ("DATA_CHILD_TRIPWIRES", "DATA_CHILD_TRIPWIRES"),
          ("DATA_CHILD_ROIS", "DATA_CHILD_ROIS"),
          ("DATA_CHILD_SENSORS", "DATA_CHILD_SENSORS"),
          ("CMD_CAMERA_CONFIG", "CMD_CAMERA_CONFIG"),
          ("POSITIONING_POSE", "POSITIONING_POSE"),
          ("POSITIONING_STATUS", "POSITIONING_STATUS"),
        ],
        max_length=50,
      ),
    ),
  ]