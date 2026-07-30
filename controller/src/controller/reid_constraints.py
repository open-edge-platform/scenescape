# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from controller.reid_constants import RESERVED_ENTRY_KEYS
from controller.reid_env import DEFAULT_CONFIDENCE_THRESHOLD
from scene_common import log


def build_query_constraints(object_type, confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
                            **constraints):
  """
  Build TIER 1 metadata constraints shared by ReID vector database adapters.

  Constraint routing logic:
  - Object type is always an AND constraint (required field; not overridable)
  - Dict values with confidence >= threshold become exact-match constraints
  - Low-confidence or missing-confidence constraints are ignored (TIER 2 handles them)
  - Reserved identity/persist keys in metadata are ignored

  @param   object_type           Class of the object (Person, Vehicle, etc.)
  @param   confidence_threshold  Minimum confidence for applying metadata filters
  @param   constraints           Optional metadata filters
  @return  query_constraints     Dictionary mapping property names to ["==", value]
  """
  query_constraints = {
    "type": ["==", f"{object_type}"]
  }

  log.debug(
    f"[ReID] Building constraints for object_type={object_type}, "
    f"threshold={confidence_threshold}")
  log.debug(f"[ReID] Input constraints: {constraints}")

  if constraints:
    for key, value in constraints.items():
      if key in RESERVED_ENTRY_KEYS:
        log.debug(f"[ReID] Skipping reserved constraint key '{key}'")
        continue
      if value is None:
        log.debug(f"[ReID] Skipping {key}: value is None")
        continue

      actual_value = value
      confidence = None

      if isinstance(value, dict) and 'label' in value:
        actual_value = value['label']
        confidence = value.get('confidence', None)
        log.debug(
          f"[ReID] {key}: dict format - label={actual_value}, confidence={confidence}")
      else:
        log.debug(f"[ReID] {key}: non-dict or no label - value={value}, type={type(value)}")

      try:
        if confidence is not None:
          conf_value = float(confidence)
          if conf_value >= confidence_threshold:
            query_constraints[key] = ["==", str(actual_value)]
            log.debug(
              f"[ReID] ADDED: {key}={actual_value} "
              f"(confidence={conf_value} >= {confidence_threshold})")
          else:
            log.debug(
              f"[ReID] IGNORED: {key} "
              f"(confidence={conf_value} < {confidence_threshold}, will use TIER 2)")
        else:
          log.debug(f"[ReID] IGNORED: {key} (no confidence available, will use TIER 2)")
      except (ValueError, TypeError):
        log.debug(f"[ReID] IGNORED: {key} (confidence not convertible to float)")

  log.debug(f"[ReID] Final TIER 1 query_constraints: {query_constraints}")
  return query_constraints
