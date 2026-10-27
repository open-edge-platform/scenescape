# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Match event payloads by metadata attribute without a fixed field list.

classificationPolicy stores each tensor as ``{name: {label, model_name, confidence}}``
on whatever object the publisher nested it under. A new model field is queryable as
soon as that key appears in the JSON.
"""

from typing import Any

MAX_ATTRIBUTE_FILTERS = 16
MAX_ATTRIBUTE_NAME_LENGTH = 128
MAX_ATTRIBUTE_LABEL_LENGTH = 256


class AttributeFilterError(ValueError):
  """Caller sent an attribute filter the query API will not run."""


def validate_attributes(attributes: dict[str, str] | None) -> dict[str, str]:
  """Return a copy of attribute name → label, or raise AttributeFilterError."""
  if not attributes:
    return {}
  if len(attributes) > MAX_ATTRIBUTE_FILTERS:
    raise AttributeFilterError(
      f'at most {MAX_ATTRIBUTE_FILTERS} attribute filters are allowed')
  cleaned: dict[str, str] = {}
  for name, label in attributes.items():
    if not isinstance(name, str) or not name.strip():
      raise AttributeFilterError('attribute name must be a non-empty string')
    if len(name) > MAX_ATTRIBUTE_NAME_LENGTH or '\x00' in name:
      raise AttributeFilterError('attribute name is too long')
    if not isinstance(label, str) or len(label) > MAX_ATTRIBUTE_LABEL_LENGTH or '\x00' in label:
      raise AttributeFilterError('attribute label is invalid')
    cleaned[name] = label
  return cleaned


def attribute_clauses(
  attributes: dict[str, str],
  params: dict[str, Any],
) -> list[str]:
  """SQL fragments that require every attribute label to appear in the payload.

  The attribute name is a bound parameter. It is never interpolated into the
  statement, so a name the server has not seen before needs no query change.
  """
  clauses: list[str] = []
  for index, (name, label) in enumerate(attributes.items()):
    name_key = f'attr_name_{index}'
    label_key = f'attr_label_{index}'
    params[name_key] = name
    params[label_key] = label
    clauses.append(
      f"""EXISTS (
        SELECT 1 FROM jsonb_path_query(payload, '$.**') AS elem(node)
        WHERE jsonb_typeof(node) = 'object'
          AND (
            (jsonb_typeof(node -> %({name_key})s) = 'object'
              AND node -> %({name_key})s ->> 'label' = %({label_key})s)
            OR (jsonb_typeof(node -> %({name_key})s) IN ('string', 'number', 'boolean')
              AND node ->> %({name_key})s = %({label_key})s)
          )
      )"""
    )
  return clauses
