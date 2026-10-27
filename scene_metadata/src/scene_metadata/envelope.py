# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Canonical event envelope for Timescale storage."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid


@dataclass
class EventEnvelope:
  """One row in scenescape_events."""

  occurred_at: datetime
  event_type: str
  source_topic: str
  deployment_id: str = 'default'
  scene_id: Optional[str] = None
  region_id: Optional[str] = None
  tripwire_id: Optional[str] = None
  track_id: Optional[str] = None
  identity_id: Optional[str] = None
  camera_id: Optional[str] = None
  source_message_id: Optional[str] = None
  payload: dict[str, Any] = field(default_factory=dict)
  event_id: uuid.UUID = field(default_factory=uuid.uuid4)

  def as_row(self) -> dict[str, Any]:
    row = asdict(self)
    row['event_id'] = str(self.event_id)
    row['occurred_at'] = self.occurred_at
    return row
