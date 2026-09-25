# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared defaults for detection-to-track association (Controller + Tracker)."""

ASSOCIATION_METHOD_EUCLIDEAN = "euclidean"
ASSOCIATION_METHOD_POSITION_MAHALANOBIS = "position_mahalanobis"
VALID_ASSOCIATION_METHODS = frozenset({
  ASSOCIATION_METHOD_EUCLIDEAN,
  ASSOCIATION_METHOD_POSITION_MAHALANOBIS,
})

DEFAULT_ASSOCIATION_GATE_PROBABILITY = 0.99
# Euclidean association distance (m). Also the hard ceiling when Mahalanobis is
# enabled without an explicit larger max_radius_m.
DEFAULT_ASSOCIATION_EUCLIDEAN_MAX_RADIUS_M = 2.0
# Production Mahalanobis ceiling so the chi-squared gate can widen with uncertainty.
DEFAULT_ASSOCIATION_MAHALANOBIS_MAX_RADIUS_M = 10.0

DEFAULT_ASSOCIATION_CONFIG = {
  "method": ASSOCIATION_METHOD_POSITION_MAHALANOBIS,
  "gate_probability": DEFAULT_ASSOCIATION_GATE_PROBABILITY,
  "max_radius_m": DEFAULT_ASSOCIATION_MAHALANOBIS_MAX_RADIUS_M,
}
