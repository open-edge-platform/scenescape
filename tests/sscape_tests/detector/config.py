#!/usr/bin/env python3

# Copyright (C) 2022 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import numpy as np

from percebro import detector

no_keypoints_poses = [detector.IAData({
  'Mconv7_stage2_L1': np.zeros((1, 38, 32, 57)),
  'Mconv7_stage2_L2': np.zeros((1, 19, 32, 57))
}, 1, (256, 256))]

path = "/opt/intel/openvino/deployment_tools/intel_models/intel/"
model_name = "person-detection-retail-0013"
detector_model = {
  "model": "test2", "engine": "Detector", "keep_aspect": 0,
  "directory": path + model_name,
  "categories": ["background", "person"],
  "xml": model_name + ".xml"
}
ovms_retail_model = {
  'model': 'retail',
  'external_id': 'person-detection-retail-0013',
  'ovmshost': 'ovms:9000'
}
ovms_hpe_model = {
  'model': 'hpe',
  'external_id': 'human-pose-estimation-0001',
  'ovmshost': 'ovms:9000'
}
dummy_ovms_result = detector.IAData(data={
    'boxes': np.array([90, 110, 120, 150, 0.99]),
    'labels': np.array([0])
  },
  save=[640, 640]
)
