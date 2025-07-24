#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

def test_detect(ocr_detect, ocr_sample_image, ocr_positions):
  """! Verifies the output of 'detector.TextDetector.detect()' method.

  @param    ocr_detect          TextDetector object
  @param    ocr_sample_image    IAData object that contains an image with text
  """

  detections = ocr_detect.detect(ocr_sample_image)
  boxes = [x['bounding_box'] for x in detections.data[0]]
  assert len(ocr_positions) == len(boxes)
  for box, position in zip(boxes, ocr_positions):
    assert abs((position[0] - box['x']) / position[0]) < 0.05
    assert abs((position[1] - (box['y'] + box["height"])) / position[1]) < 0.05

  return

def test_recognize(ocr_recognize, ocr_sample_text, ocr_words):
  """! Verifies the output of 'detector.TextDetector.detect()' method.

  @param    ocr_recognize       TextRecognize object
  @param    ocr_sample_image    IAData object that contains images with text
  """

  words = ocr_recognize.detect(ocr_sample_text)

  assert len(words.data) == len(ocr_words)
  for word in ocr_words:
    assert word in words.data

  return
