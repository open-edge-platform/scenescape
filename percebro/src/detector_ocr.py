#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import re

import cv2
import numpy as np
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

from scene_common import log
from detector import Detector, Distributed, IAData

class TextDetector(Detector):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous, distributed)
    self.normalized_output = False
    return

  def setParameters(self, model, device, plugin, threshold, ov_cores):
    super().setParameters(model, device, plugin, threshold, ov_cores)
    self.saveDict = False
    return

  def detect(self, input, debugFlag=False):
    self.output_blob = "boxes"
    return super().detect(input, debugFlag)

  def postprocess(self, result):
    detections = []
    outputs = result.data
    outputs = outputs[~np.all(outputs == 0, axis=1)]

    for output in outputs:
      x_min, y_min, x_max, y_max, confidence = int(output[0]), \
                                                int(output[1]), \
                                                int(output[2]), \
                                                int(output[3]), \
                                                round(float(output[4]), 2)

      box = self.recalculateBoundingBox([x_min, y_min, x_max, y_max],
                                        result.save[0],
                                        result.save[1])
      text = {
        'id': len(detections) + 1,
        'category': 'text',
        'confidence': confidence,
        'bounding_box': box.asDict,
      }
      detections.append(text)

    return detections

class TextRecognition(Detector):
  def findXML(self, directory, xml, device,
              default_path="/opt/intel/openvino/deployment_tools/intel_models/public/"):
    return super().findXML(directory, xml, device, default_path)

  def loadConfig(self, mdict):
    self.pattern = None
    if 'pattern' in mdict:
      log.info("Using pattern", mdict['pattern'])
      self.pattern = re.compile(mdict['pattern'])
    return

  def preprocess(self, input):
    input.data = list(map(lambda frame: cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), input.data))
    return super().preprocess(input)

  # Filter out matches based on requested pattern.
  def match_pattern(self, detection):
    if self.pattern is None:
      return detection

    result = ''
    matches = re.findall(self.pattern, detection)
    if matches:
      result = matches[0]
    return result

  def postprocess(self, result):
    letters = "~0123456789abcdefghijklmnopqrstuvwxyz"

    recognition_results_test = np.squeeze([result.data])
    # Read annotation based on probabilities from output layer
    annotation = ""
    for letter in recognition_results_test:
      parsed_letter = letters[letter.argmax()]

      # Returning 0 index from argmax signalises end of string
      if parsed_letter == letters[0]:
        break
      annotation += parsed_letter

    return self.match_pattern(annotation)

class TrOCR(TextRecognition):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous, distributed)
    self.normalized_output = False
    #Default pattern
    self.pattern = None
    return

  def loadConfig(self, mdict):
    self.model_path = None
    self.vision_model_path = None
    if 'model_path' in mdict:
      self.model_path = mdict['model_path']
    if 'secondary_model_path' in mdict:
      self.vision_model_path = mdict['secondary_model_path']
    if 'pattern' in mdict:
      log.info("Using pattern", mdict['pattern'])
      self.pattern = re.compile(mdict['pattern'])
    return

  def configureDetector(self):
    self.model = TrOCRProcessor.from_pretrained(self.model_path)
    self.enc_dec = VisionEncoderDecoderModel.from_pretrained(self.vision_model_path)
    return

  def detect(self, input, debugFlag=False):
    post_res = []
    if input:
      for frame in input.data:
        if np.prod(frame.shape):
          as_pil = Image.fromarray(frame)

          det_pixel_values = self.model(images=as_pil, return_tensors="pt").pixel_values
          generated_ids = self.enc_dec.generate(det_pixel_values)
          generated_text = self.model.batch_decode(generated_ids, skip_special_tokens=True)[0]

          result = self.match_pattern(generated_text)
          post_res.append([result])
      return IAData(post_res, id=input.id)
    return None

  # This class uses TrOCRProcessor and VisionEncoderDecoderModel synchronously,
  # hence there won't be any 'waiting' tasks.
  @property
  def waitingIDs(self):
    return []
  @property
  def waitingCount(self):
    return 0
  def getDone(self):
    return None
