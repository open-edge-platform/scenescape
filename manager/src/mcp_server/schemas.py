# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Explicit contracts for the configuration inventory tools."""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Arguments(BaseModel):
  model_config = ConfigDict(extra='forbid')


class ListArguments(Arguments):
  limit: int = Field(default=25, ge=1, le=25)
  offset: int = Field(default=0, ge=0, le=100000)


class SceneArguments(Arguments):
  scene_id: UUID


class SceneListArguments(ListArguments):
  scene_id: UUID | None = None


class SceneSummary(BaseModel):
  id: UUID
  name: str
  map_type: str | None
  scale: float | None
  use_tracker: bool


class CameraSummary(BaseModel):
  sensor_id: str
  name: str
  scene_id: UUID | None
  pose_locked: bool


class RegionSummary(BaseModel):
  uuid: UUID
  name: str
  scene_id: UUID
  height: float
  volumetric: bool | None
  roi_type: str


ItemT = TypeVar('ItemT', bound=BaseModel)


class Page(BaseModel, Generic[ItemT]):
  items: list[ItemT]
  next_offset: int | None
