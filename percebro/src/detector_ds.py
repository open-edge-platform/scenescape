#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import importlib
import io
import json
import os
import sys

import numpy as np

from detector import Detector, IAData
from scene_common.geometry import Point, Rectangle
from scene_common import log

def sanitizePath(user_path):
  real_path = os.path.abspath(user_path)
  if not os.path.exists(real_path):
    raise ValueError("Requested path", user_path, "does not exist")
  if not os.path.isfile(real_path):
    raise ValueError("Requested path", user_path, "is not a file.")
  return real_path


class DetectorDS(Detector):
  def loadModule(self):
    ds_module_path = os.environ.get('DS_MODULE')
    self.model_loaded = False
    if ds_module_path is not None:
      log.info("DetectorDS: Loading dependencies")
      try:
        mod_path = sanitizePath(ds_module_path)
        mod_dir, mod_file = os.path.split(mod_path)
        mod_name, _ = os.path.splitext(mod_file)

        if mod_dir not in sys.path:
          sys.path.append(mod_dir)

        mod_spec = importlib.util.spec_from_file_location(mod_name, mod_path)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)

        self.model_preprocess = module.preprocess
        self.model_postprocess = module.postprocess
        self.model_decrypt = module.decrypt

        self.model_loaded = True
        log.info("DetectorDS: Success loading module")
      except ValueError:
        log.error("DetectorDS: Failed loading module")
    else:
      log.warn("DetectorDS: Skipping loading")
    return

  def __init__(self, asynchronous=False, distributed=None):
    self.loadModule()
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.threshold = 0.5
    self.nms_threshold = 0.65
    return

  def getPassword(self, password_path):
    password = None
    with open(password_path, 'r') as fd:
      password = fd.readline().strip()

    if password is None:
      log.error("DetectorDS: Failed reading password file")
    return password

  def modelLoad(self):
    if self.password is None:
      log.error("DetectorDS: Need a valid password file path to open this model.")
      raise RuntimeError("DetectorDS: Valid Password file not provided")
    model_bytes = self.model_decrypt(self.password, self.model_path)
    self.model = self.core.read_model(model=io.BytesIO(model_bytes))

    if self.input_shape is not None:
      self.model.reshape({0: self.input_shape})
    self.inputs_info = self.model.inputs
    self.input_blob = [x for x in next(iter(self.inputs_info)).names][0]
    self.output_blob = [x for x in next(iter(self.model.outputs)).names][0]

    model_shape = list(self.model.inputs[0].get_partial_shape())
    if model_shape[0] != 1:
      model_shape[0] = 1
      self.model.reshape({ self.input_blob: model_shape })
    return

  def loadConfig(self, mdict):
    if not 'password_file' in mdict:
      log.error("DetectorDS: Need a password file path to open this model.")
      raise RuntimeError("DetectorDS: Password not provided")

    self.password = self.getPassword(sanitizePath(mdict['password_file']))
    self.model_path = sanitizePath(mdict['model_path'])
    if not self.model_loaded:
      self.exec_network = None
      raise RuntimeError("DetectorDS: Module not loaded")

    if 'nms_threshold' in mdict:
      self.nms_threshold = mdict['nms_threshold']
    if 'threshold' in mdict:
      self.threshold = mdict['threshold']

    self.categories = None
    if 'categories' in mdict:
      if isinstance(mdict['categories'], list):
        self.categories = mdict['categories']
      elif isinstance(mdict['categories'], str):
        categories_path = sanitizePath(mdict['categories'])
        with open(categories_path) as fd:
          self.categories = json.load(fd)
          self.class_ids = [category['id'] for category in self.categories]

    return

  def getModelShape(self):
    self.n, _, self.c, self.h, self.w = next(iter(self.inputs_info)).shape
    return

  def preprocess(self, input):
    prepared = []
    intrinsics = np.dot(np.array(input.cam), np.eye(4)[:3, :])
    max_distance_sq = input.max_distance_squared
    for frame in input.data:
      in_frame, intrinsics_scaled = self.model_preprocess(frame, intrinsics, (self.h, self.w))
      prepared.append(IAData(in_frame, input.id, [ frame.shape[1::-1], intrinsics_scaled, max_distance_sq ] ))
    return prepared

  def postprocess(self, result):
    data = {'output' : result.data}
    shape, intrinsics, max_distance_sq = result.save
    annotations = self.model_postprocess(data,
                                    intrinsics,
                                    (self.h, self.w),
                                    self.class_ids,
                                    score_threshold=self.threshold,
                                    nms_threshold=self.nms_threshold)

    return self.postprocessResults(annotations, max_distance_sq)

  def postprocessResults(self, annotations, max_distance_sq=None):
    objects = []

    for ann in annotations:
      category_id = ann['category_id']
      category = next((item['name'] for item in self.categories if item['id'] == category_id), None)

      if ann['score'] < self.threshold:
        continue

      # Skip detections for unknown categories
      if category is None or len(category) == 0:
        continue

      if max_distance_sq and max_distance_sq > 0:
        obj_dist = ann['translation'][0] ** 2 + ann['translation'][1] ** 2 + ann['translation'][2] ** 2
        if obj_dist > max_distance_sq:
          continue

      obj = {}
      obj['category'] = category
      obj['confidence'] = ann['score']
      obj['translation'] = ann['translation']
      obj['rotation'] = ann['rotation']
      obj['size'] = ann['dimension']
      obj['id'] = len(objects) + 1

      x_min, y_min, z_min = obj['translation']
      x_size, y_size, z_size = obj['size']
      x_max, y_max, z_max = x_min + x_size, y_min + y_size, z_min + z_size
      bounding_box = Rectangle(origin=Point(x_min, y_min, z_min),
                               opposite=Point(x_max, y_max, z_max))

      com_w, com_h = bounding_box.width / 3, bounding_box.height / 4
      com_x, com_y = int(bounding_box.x + com_w), int(bounding_box.y + com_h)
      center_of_mass = Rectangle(origin=Point(com_x, com_y, com_x),
                                 size=(com_w, com_h, com_w))
      obj['center_of_mass'] = center_of_mass.asDict
      objects.append(obj)
    return objects
