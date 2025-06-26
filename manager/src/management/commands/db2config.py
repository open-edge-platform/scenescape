# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
import re
from django.core.management.base import BaseCommand
from manager.models import Scene

class Command(BaseCommand):
  def add_arguments(self, parser):
    parser.add_argument("config", nargs="?", help="config file to write")
    return

  def handle(self, *args, **options):
    scenes = Scene.objects.all()

    if len(scenes) != 1:
      print("Don't know which scene to create config for")
      exit(1)

    scene = scenes[0]
    ss_scene = scene.scenescapeScene
    scene.scenescapeSceneUpdateRegions(ss_scene)

    config = {'name': scene.name}
    if scene.map:
      config['map'] = os.path.basename(scene.map.path)
    if scene.scale:
      config['scale'] = scene.scale

    if len(ss_scene.sensors):
      config['sensors'] = {}
      for name in ss_scene.sensors:
        sensor = ss_scene.sensors[name]
        sdict = {}
        if hasattr(sensor.pose, "camCoords"):
          sdict['camera points'] = sensor.pose.camCoords
          sdict['map points'] = sensor.pose.mapCoords
        if sensor.pose.intrinsics:
          # FIXME - convert to fov if possible
          intrins = sensor.pose.intrinsics.intrinsics
          sdict['intrinsics'] = [intrins[0, 0], intrins[1, 1], intrins[0, 2], intrins[1, 2]]
        if hasattr(sensor.pose, "resolution"):
          sdict['width'] = sensor.pose.resolution[0]
          sdict['height'] = sensor.pose.resolution[1]
        config['sensors'][name] = sdict

    if len(ss_scene.regions):
      config['regions'] = {}
      for name in ss_scene.regions:
        region = ss_scene.regions[name]
        config['regions'][name] = [(pt.x, pt.y) for pt in region.points]

    pretty = json.dumps(config, indent=4)
    pretty = re.sub(r"\[\s+", r"[", pretty)
    pretty = re.sub(r"\s+\]", r"]", pretty)
    pretty = re.sub(r",\s+([0-9])", r", \1", pretty)
    pretty = re.sub(r",\s+\[", r", [", pretty)
    pretty = re.sub(r"([0-9]+)\.0([^0-9])", r"\1\2", pretty)

    if options['config']:
      with open(options['config'], "w") as f:
        f.write(pretty)
        f.write("\n")
    else:
      print(pretty)

    return
