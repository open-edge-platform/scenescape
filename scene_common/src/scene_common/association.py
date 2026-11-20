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


def add_uncertainty(obj_dict, obj):
  """Set the output ``uncertainty`` of ``obj`` (the tracker's covariance of the published state) in ``obj_dict``.

  ``obj_dict`` may start from the incoming detection (``obj.info``), which can carry the ``uncertainty`` of
  another tracker (a child scene). The field is authoritative on ``obj``: when it has none, the key is removed.
  Hierarchy callers that trust a child's tracks (``retrack=False``) must promote the child's
  ``uncertainty`` onto ``obj`` before publish; leaving it only in ``info`` is not enough.
  """
  uncertainty = getattr(obj, 'uncertainty', None)
  if uncertainty:
    obj_dict['uncertainty'] = uncertainty
  else:
    obj_dict.pop('uncertainty', None)


def add_association_window(obj_dict, obj):
  """Copy the tracker's ``association_window`` of ``obj`` into ``obj_dict`` when it has one."""
  association_window = getattr(obj, 'association_window', None)
  if association_window:
    obj_dict['association_window'] = association_window
