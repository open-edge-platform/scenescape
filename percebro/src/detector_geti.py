# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os

import numpy as np

from scene_common import log
from openvino.runtime import Core
from model_api.adapters import OpenvinoAdapter, create_core
from model_api.models import Model
from model_api.models.utils import Detection
from detector import Detector, Distributed, IAData
from wrapper_otxssd import OTXSSDModel

from scene_common.geometry import Point, Rectangle

def getDetectionCoords(detection : Detection):
  return [detection.xmin, detection.ymin, detection.xmax, detection.ymax]

class GetiDetector(Detector):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.ie = None
    self.threshold = 0.5
    self.detector = None
    self.asynchronous = asynchronous
    self.saveDict = True
    self.categories = []
    self.normalized_output = False
    self.core = None
    return

  def preprocess(self, input):
    if self.distributed == Distributed.OVMS:
      return super().preprocess(input)

    processed = []
    if input is not None:
      for image in input.data:
        if image is None:
          processed.append(IAData(None, input.id))
          continue

        image = self.preprocessColorspace(image)

        dict_data, input_meta = self.detector.preprocess(image)
        processed.append(IAData(dict_data['image'], input.id, input_meta) )

    return processed

  def postprocess(self, result):
    if self.distributed == Distributed.OVMS:
      return self.postprocessAsDict(result)

    found = []

    if result.data is None:
      return []

    input_meta = result.save

    if 'boxes' in result.data:
      res_shape = result.data['boxes'].shape
      # Make bi-dimensional result vectors 3-dimensional so detector.postprocess is happy
      if len(res_shape) == 2:
        result.data['boxes'] = np.expand_dims( result.data['boxes'], axis=0 )
        result.data['labels'] = np.expand_dims( result.data['labels'], axis=0 )

    try:
      predictions = self.detector.postprocess(result.data, input_meta)
    except Exception as e:
      log.warn("Geti detector postprocessing failed ", str(e))
      return found

    # 'predictions' is now of type DetectionResult
    # which is a tuple of (detections, saliency_map, feature_vector).
    # Therefore just looking at first tuple member.
    for res in predictions[0]:
      # Leave early when we're done with high confidence detections
      if res.score < self.threshold:
        continue

      # Avoid crash due to out of bounds index
      if res.id >= len(self.categories):
        log.debug("Skipping out of bounds category index")
        continue

      if self.categories[res.id] in self.blacklist:
        log.debug(f"Skipping blacklisted category {self.categories[res.id]}")
        continue

      bounds = [None] * 4
      rect = getDetectionCoords(res)
      bounds[0] = rect[0]
      bounds[1] = rect[1]
      bounds[2] = rect[2]
      bounds[3] = rect[3]
      # Avoid reporting invalid detections (0 height or width)
      if bounds[0] == bounds[2] \
          or bounds[1] == bounds[3]:
        continue

      if bounds[2] < bounds[0]:
        tmp = bounds[0]
        bounds[0] = bounds[2]
        bounds[2] = tmp
      if bounds[3] < bounds[1]:
        tmp = bounds[0]
        bounds[0] = bounds[3]
        bounds[3] = tmp

      bound_box = Rectangle(origin=Point(bounds[0], bounds[1]),
                            opposite=Point(bounds[2], bounds[3]))
      comw = bound_box.width / 3
      comh = bound_box.height / 4
      center_of_mass = Rectangle(origin=Point(bound_box.x + comw, bound_box.y + comh),
                                 size=(comw, comh))
      object = {
        'id': len(found) + 1,
        'category': self.categories[res.id] ,
        'confidence': float(res.score),
        'bounding_box': bound_box.asDict,
        'center_of_mass': center_of_mass.asDict
      }
      found.append( object )

    return found

  def modelPreconfigure(self):
    parameters = None
    self.model_params = None
    self.model_type = None

    # Assumes config.json can be found in same dir as model.xml/model.bin
    params_file = os.path.join(os.path.dirname(self.model_path), 'config.json')
    if os.path.exists( params_file ):
      with open(params_file, "r", encoding="utf8") as file:
        parameters = json.load(file)

    if parameters is None:
      self.model_type = "ssd"
      self.model_params = None
    else:
      if 'type_of_model' in parameters:
        self.model_type = parameters["type_of_model"]
      else:
        self.model_type = parameters["model_type"]

      if self.model_type.startswith( "OTE_" ):
        self.model_type = self.model_type.replace( 'OTE_', "", 1 )

      self.model_params = parameters["model_parameters"]

      if "labels" in self.model_params and isinstance(self.model_params["labels"], dict):
        self.categories = self._loadCategories( self.model_params["labels"] )

      # Empty out labels, they confuse the inference engine
      self.model_params["labels"] = []

    # Set up the performance hints and threading config
    super().modelPreconfigure()
    return

  # This stage loads the model into an Adapter, but does not compile it.
  def modelLoad(self):
    self.detector = Model.create_model(self.model_path,
                                    model_type=self.model_type,
                                    preload=False,
                                    core=None,
                                    configuration={'confidence_threshold': self.threshold},
                                    max_num_requests=self.num_req,
                                    nstreams=f'{self.ov_cores}',
                                    nthreads=f'{self.ov_cores}',
                                    device=self.device)
    self.core = self.detector.inference_adapter.core

    model_shape = list(self.detector.inputs[self.detector.image_blob_name].shape)

    return

  # This stage compiles the model onto the requested device.
  def modelCompile(self):
    self.detector.load()
    self.exec_network = self.detector.inference_adapter.compiled_model
    self.inputs_info = self.detector.inference_adapter.get_input_layers()

    self.input_blob = next(iter(self.inputs_info))
    self.output_blob = next(iter(self.detector.inference_adapter.get_output_layers()))

    self.async_queue = []
    for i in range(self.num_req):
      self.async_queue.append(self.exec_network.create_infer_request())
    return

  # We don't populate/use the model's n,c,h,w values since they are internal to the Adapter layer.
  def getModelShape(self):
    return
