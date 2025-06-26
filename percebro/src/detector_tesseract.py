#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
from PIL import Image
from tesserocr import RIL, iterate_level, PyTessBaseAPI

from scene_common.geometry import Point, Rectangle

from detector import Detector, Distributed, IAData

class TesseractDetector(Detector):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    """! TesseractDetector is used for Optical Character Recognition (OCR)
    using a library called tesseract-ocr.

    @param    asynchronous    Flag to enable asynchronous mode. Default is False.
    @param    distributed     Flag to enable distributed mode. Default is False.
    """

    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.tess_api = PyTessBaseAPI(lang="eng", path="/usr/share/tesseract-ocr/4.00/tessdata/")
    return

  def detect(self, input, debugFlag=False):
    """! Detects and returns the detected text with bounding box.

    @param    input       Input frame/image
    @param    debugFlag   Flag to enable debug mode. Default is False.

    @return   A dictionary of detected text and bounding box information
    """

    if input is not None:
      blocks = []
      mono = self.preprocess(input)
      for frame in mono:
        pil_frame = Image.fromarray(frame)
        self.tess_api.SetImage(pil_frame)
        self.tess_api.Recognize()

        iter = self.tess_api.GetIterator()
        for word in iterate_level(iter, RIL.WORD):
          bbox = word.BoundingBox(RIL.WORD)
          if bbox is None:
            continue

          text = word.GetUTF8Text(RIL.WORD).strip()
          if not len(text):
            continue

          blocks.append([bbox, text])

      result = IAData(blocks, input.id)
      self.taskLock.acquire()
      self.tasksComplete.append([result])
      self.taskLock.release()

    return super().detect(None, debugFlag=debugFlag)

  def preprocess(self, input):
    """! Converts the frame from RGB to grayscale.

    @param    input       Input frame/image
    @return   A grayscale image
    """

    monochrome = []

    for frame in input.data:
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      monochrome.append(gray)

    return monochrome

  def postprocess(self, result):
    """! Creates a dictionary for each of the detected words.

    @param    result    A list of detected words.
    @return   A list of dictionary of detected text and bounding box information
    """

    words = []
    for output in result.data:
      (x_min, y_min, x_max, y_max), text = output
      box = Rectangle(origin=Point(x_min, y_min),
                      opposite=Point(x_max, y_max))

      word = {
        'id': len(words) + 1,
        'category': 'text',
        'text': text,
        'bounding_box': box.asDict
      }
      words.append(word)

    return words
