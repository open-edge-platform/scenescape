# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Fields shared between the form, serializer, and scene import
CAM_COMMON_FIELDS = (
    "name",
    "scale",
    "intrinsics",
    "command",
    "cv_subsystem",
    "camerachain",
    "undistort",
    "modelconfig",
    "use_camera_pipeline",
)

# Additional fields only needed by the Django form (UI/legacy)
CAM_FORM_ONLY_FIELDS = [
    'threshold', 'aspect', 'sensor', 'sensorchain', 'sensorattrib',
    'window', 'usetimestamps', 'virtual', 'debug', 'override_saved_intrinstics',
    'frames', 'stats', 'waitforstable', 'preprocess', 'realtime', 'faketime',
    'rootcert', 'cert', 'cvcores', 'ovcores', 'unwarp', 'ovmshost',
    'framerate', 'maxcache', 'filter', 'disable_rotation', 'maxdistance',
]

# Fields only present in Kubernetes deployments
CAM_KUBERNETES_FIELDS = ['command', 'camerachain', 'camera_pipeline']

# Advanced fields shown in both form and serializer
CAM_ADVANCED_FIELDS = ['cv_subsystem', 'undistort', 'modelconfig',
                       'use_camera_pipeline', 'detection_labels']

# Full form field list
CAM_FORM_FIELDS = [
    'name', 'sensor_id', 'scene', 'transforms', 'transform_type',
    'width', 'height',
    'intrinsics_fx', 'intrinsics_fy', 'intrinsics_cx', 'intrinsics_cy',
    'distortion_k1', 'distortion_k2', 'distortion_p1', 'distortion_p2', 'distortion_k3',
] + CAM_ADVANCED_FIELDS + CAM_KUBERNETES_FIELDS + CAM_FORM_ONLY_FIELDS

# Serializer API fields
CAM_SERIALIZER_FIELDS = [
    'uid', 'name', 'sensor_id', 'intrinsics', 'transform_type', 'transforms',
    'distortion', 'translation', 'rotation', 'scale', 'resolution', 'scene',
    'threshold', 'aspect',
] + CAM_ADVANCED_FIELDS + CAM_KUBERNETES_FIELDS
