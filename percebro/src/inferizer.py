# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from dataclasses import dataclass

from detector import Detector, Distributed, REIDDetector
from detector_3d import Detector3D
from detector_atag import ATagDetector
from detector_ds import DetectorDS
from detector_geti import GetiDetector
from detector_motion import MotionKnnDetector, MotionMog2Detector
from detector_ocr import TextDetector, TextRecognition, TrOCR
from detector_pose import PoseEstimator
from detector_tesseract import TesseractDetector
try:
  from detector_yolo import YoloV8Detector
except ImportError as e:
  print(f"Warning: Could not import YoloV8Detector: {e}")
  YoloV8Detector = None

from scene_common import log

@dataclass
class InferenceParameters:
  threshold: float
  ovcores: int
  ovmshost: str

class Inferizer:
  engine_mapping = {
    'ATagDetector': ATagDetector,
    'Detector': Detector,
    'Detector3D': Detector3D,
    'DetectorDS': DetectorDS,
    'GetiDetector': GetiDetector,
    'MotionKnnDetector': MotionKnnDetector,
    'MotionMog2Detector': MotionMog2Detector,
    'PoseEstimator': PoseEstimator,
    'REIDDetector': REIDDetector,
    'TesseractDetector': TesseractDetector,
    'TextDetector': TextDetector,
    'TextRecognition': TextRecognition,
    'TrOCR': TrOCR,
    'YoloV8Detector': YoloV8Detector
  }

  #Valid config entries for model-config:
  valid_entries = [ 'blacklist',
                    'categories',
                    'colorspace',
                    'directory',
                    'external_id',
                    'history',
                    'keep_aspect',
                    'model_path',
                    'nms_threshold',
                    'normalize_input',
                    'normalized_output',
                    'output_order',
                    'password_file',
                    'pattern',
                    'secondary_model_path',
                    'threshold',
                    'xml' ]

  def __init__(self, spec, params, device="CPU"):
    self.params = params
    self.device = device
    self.dependencies = None

    # FIXME - allow specifying threshold in `spec`
    specParams = spec.split('=')
    self.modelID = specParams[0]
    if len(specParams) > 1:
      self.device = specParams[1]

    if self.device in Distributed.__members__:
      self.distributed = Distributed(self.device)
      self.device = "CPU"

    self.startEngine()
    return

  def startEngine(self):
    device = self.device.upper()
    dist = Distributed.NONE

    if device in Distributed.__members__:
      dist = Distributed(device)
      device = "CPU"

    vdict = self.modelWithName(self.modelID)
    self.engine = vdict['engine'](asynchronous=True, distributed=dist)

    log.info("Starting model", self.modelID, "on", device)

    modelConfig = self.modelID

    if isinstance(vdict,dict) and len(vdict) > 1:
      modelConfig = { 'model': self.modelID }
      modelConfig.update( vdict )

    if dist == Distributed.OVMS:
      config = {
        'model': self.modelID,
        'external_id': vdict['external_id'],
        'ovmshost': self.params.ovmshost
      }

      if isinstance(modelConfig, dict):
        modelConfig.update(config)
      else:
        modelConfig = config

      if 'categories' not in modelConfig and 'categories' in vdict:
        modelConfig['categories'] = vdict['categories']

    self.engine.setParameters(modelConfig, device, None,
                              self.params.threshold, self.params.ovcores)

    return

  @staticmethod
  def loadModelConfig(path):
    if not os.path.exists(path) and not os.path.isabs(path):
      script = os.path.realpath(__file__)
      path = os.path.join(os.path.dirname(script), path)

    with open(path) as json_file:
      data = json.load(json_file)
    Inferizer.visionModels = {}
    for cfg in data:
      mdict = {
        'engine': Inferizer.engine_mapping.get(cfg['engine']),
      }
      for entry in Inferizer.valid_entries:
        if entry in cfg:
          mdict[entry] = cfg[entry]
      Inferizer.visionModels[cfg['model']] = mdict

    return

  @staticmethod
  def modelWithName(modelName):
    return Inferizer.visionModels.get(modelName, None)

  def __repr__(self):
    return f"Name: {self.modelID} Device: {self.device} Depends: {self.dependencies}"
