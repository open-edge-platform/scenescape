# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared constants and metric helpers for ReID vector database adapters."""

import math

SCHEMA_NAME = "reid_vector"
K_NEIGHBORS = 1
SIMILARITY_METRIC = "IP"
# Tolerance applied to the theoretical [-1, 1] IP score bounds to absorb
# float32 rounding errors from vector normalization and inner-product computation.
COSINE_SIMILARITY_TOLERANCE = 1e-6
SCHEMA_MARKER_COLLECTION = "_reid_schema_markers"
RESERVED_ENTRY_KEYS = frozenset({
  "uuid",
  "rvid",
  "type",
  "persist",
  "persist_timestamp",
})
DEFAULT_CONFIG_SIMILARITY_METRIC = "COSINE"
SUPPORTED_CONFIG_SIMILARITY_METRICS = frozenset({"COSINE", "L2"})


def is_inner_product_metric(metric):
  """Return True when descriptor metric is Inner Product."""
  return str(metric).strip().upper() == "IP"


def is_higher_better_metric(metric):
  """Return True when higher scores are better for the descriptor metric."""
  return is_inner_product_metric(metric)


def is_within_inner_product_range(value):
  """Return True when an Inner Product score lies within the tolerated [-1, 1] bounds."""
  bound = 1.0 + COSINE_SIMILARITY_TOLERANCE
  return -bound <= value <= bound


def normalize_config_similarity_metric(metric, default=DEFAULT_CONFIG_SIMILARITY_METRIC):
  """Normalize a controller-facing similarity metric (COSINE/L2)."""
  normalized = str(metric).strip().upper()
  if normalized not in SUPPORTED_CONFIG_SIMILARITY_METRICS:
    return default
  return normalized


def resolve_database_similarity_metric(configured_metric):
  """Map controller-facing metric to the backend descriptor metric."""
  metric = normalize_config_similarity_metric(configured_metric)
  if metric == "COSINE":
    return "IP"
  return metric


def normalize_similarity_score(score, metric):
  """
  Return a canonical float similarity score, or None when invalid.

  IP scores must lie in the tolerated [-1, 1] range. L2 distances must be
  finite and non-negative; adapters that receive signed wire scores should
  convert them before calling this helper.
  """
  try:
    value = float(score)
  except (TypeError, ValueError):
    return None

  if not math.isfinite(value):
    return None

  if is_inner_product_metric(metric):
    if not is_within_inner_product_range(value):
      return None
  elif value < 0.0:
    return None

  return value


def is_similarity_match(score, threshold, metric):
  """Evaluate threshold semantics for the active descriptor metric."""
  if score is None or not math.isfinite(score):
    return False
  if is_higher_better_metric(metric):
    if not is_within_inner_product_range(score):
      return False
    return score > threshold
  return score < threshold


def pick_best_metric_value(metric_values, metric):
  """Pick the best metric value according to descriptor metric semantics."""
  if not metric_values:
    return None
  if is_higher_better_metric(metric):
    return max(metric_values)
  return min(metric_values)
