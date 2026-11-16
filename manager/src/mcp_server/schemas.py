# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Explicit contracts for the configuration inventory tools."""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_OFFSET = 100000


class Arguments(BaseModel):
  model_config = ConfigDict(extra='forbid')


class ListArguments(Arguments):
  limit: int = Field(default=25, ge=1, le=25)
  offset: int = Field(default=0, ge=0, le=MAX_OFFSET)


class SceneArguments(Arguments):
  scene_id: UUID


class SceneSummary(BaseModel):
  id: UUID
  name: str
  map_type: str | None
  scale: float | None
  use_tracker: bool


ItemT = TypeVar('ItemT', bound=BaseModel)


class Page(BaseModel, Generic[ItemT]):
  items: list[ItemT]
  next_offset: int | None
