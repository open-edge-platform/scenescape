# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from controller.person_pose.bbox_adjuster import PersonPoseAdjuster

MIN_POSE_CACHE_TTL = 10.0
POSE_CACHE_TTL_MULTIPLIER = 30
PERSON_POSE_ADJUSTMENT_ENV_VAR = 'CONTROLLER_ENABLE_PERSON_POSE_ADJUSTMENT'

__all__ = [
  'PersonPoseAdjuster',
  'MIN_POSE_CACHE_TTL',
  'POSE_CACHE_TTL_MULTIPLIER',
  'PERSON_POSE_ADJUSTMENT_ENV_VAR',
]
