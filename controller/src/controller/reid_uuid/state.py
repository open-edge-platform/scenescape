# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum


class ReidState(Enum):
  """State of ReID query and matching for an object."""

  PENDING_COLLECTION = "pending_collection"
  QUERY_NO_MATCH = "query_no_match"
  MATCHED = "matched"
  REID_DISABLED = "reid_disabled"
