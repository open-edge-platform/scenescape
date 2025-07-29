# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
from model_api.models.ssd import SSD, find_layer_by_name
from model_api.models.result.Detection import DetectionResult

class OTXSSDModel(SSD):
  __model__ = 'OTX_SSD'

  def __init__(self, model_adapter, configuration=None, preload=False):
    super(SSD, self).__init__(model_adapter, configuration, preload)
    self.image_info_blob_name = self.image_info_blob_names[0] if len(self.image_info_blob_names) == 1 else None

    self.output_parser = BatchBoxesLabelsParser(
      self.outputs,
      self.inputs[self.image_blob_name].shape[2:][::-1],
    )

  def _get_outputs(self):
    output_match_dict = {}
    output_names = ["boxes", "labels", "feature_vector", "saliency_map"]
    for output_name in output_names:
      for node_name, node_meta in self.outputs.items():
        if output_name in node_meta.names:
          output_match_dict[output_name] = node_name
          break
    return output_match_dict

class BatchBoxesLabelsParser:
  """Batched output parser."""

  def __init__(self, layers, input_size, labels_layer="labels", default_label=0):
    try:
      self.labels_layer = find_layer_by_name(labels_layer, layers)
    except ValueError:
      self.labels_layer = None
      self.default_label = default_label

    try:
      self.bboxes_layer = self.find_layer_bboxes_output(layers)
    except ValueError:
      self.bboxes_layer = find_layer_by_name("boxes", layers)

    self.input_size = input_size
    return


  @staticmethod
  def find_layer_bboxes_output(layers):
    filter_outputs = [name for name, data in layers.items() if len(data.shape) == 3 and data.shape[-1] == 5]
    return filter_outputs[0]

  def __call__(self, outputs):
    bboxes = outputs[self.bboxes_layer]
    if bboxes.shape[0] == 1:
      bboxes = bboxes[0]
    assert bboxes.ndim == 2
    scores = bboxes[:, 4]
    bboxes = bboxes[:, :4]
    bboxes[:, 0::2] /= self.input_size[0]
    bboxes[:, 1::2] /= self.input_size[1]
    if self.labels_layer:
      labels = outputs[self.labels_layer]
    else:
      labels = np.full(len(bboxes), self.default_label, dtype=bboxes.dtype)
    if labels.shape[0] == 1:
      labels = labels[0]

    detections = DetectionResult(bboxes=bboxes, labels=labels, scores=scores)
    return detections

