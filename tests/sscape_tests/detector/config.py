#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
