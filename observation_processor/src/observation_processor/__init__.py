# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Observation Processor service.

Implements scenescape.observation_processor.v1.ObservationProcessorService: conditions 2D camera
detections into mesh-aware world-space measurements using the frustum_gaussian
and observation_conditioning (amodal reasoner) libraries.
"""
