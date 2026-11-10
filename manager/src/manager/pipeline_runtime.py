# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Connect stored pipelines with ViPPET (import) and DLSPS 2.0 (per-camera runtime).

ViPPET and DLSPS are called synchronously from the calling request. Callers must be restricted
to superusers because DLSPS executes the stored GStreamer strings as-is. Nothing here contacts
ViPPET or DLSPS unless the MLOps flow is enabled (``settings.ENABLE_MLOPS_FLOW``).
"""

import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, List, Optional, Set, Tuple

from django.conf import settings
from django.db import IntegrityError, transaction

from manager.dlsps import (
  DLSPS_URL_ENV,
  DLSPSClient,
  DLSPSConflictError,
  DLSPSError,
  DLSPSNotFoundError,
  RestartConfig,
)
from manager.models import Cam, Pipeline
from manager.vippet import VIPPET_URL_ENV, ViPPETClient, ViPPETError
from scene_common import log

RESTART_CONFIG = RestartConfig(enabled=True)
VIPPET_ID_SEPARATOR = "/"
MAX_PIPELINE_NAME_LENGTH = Pipeline._meta.get_field('name').max_length
MAX_FILTER_TAGS = 20
MAX_FILTER_TAG_LENGTH = 100


class PipelineSyncError(Exception):
  """ViPPET could not be queried at all; no pipelines were changed."""


def mlops_flow_enabled() -> bool:
  """Return True when Manager runs with the ViPPET / DLSPS integration enabled."""
  return bool(settings.ENABLE_MLOPS_FLOW)


@dataclass(frozen=True)
class TagFilter:
  """Case-insensitive selection of ViPPET pipelines by their tags.

  ``labels`` keep the spelling the user entered (for messages); matching uses ``keys``.
  An empty filter matches every pipeline.
  """

  labels: Tuple[str, ...] = ()
  match_all: bool = False

  @property
  def keys(self) -> FrozenSet[str]:
    return frozenset(label.casefold() for label in self.labels)

  def matches(self, pipeline_tags: Iterable[str]) -> bool:
    if not self.labels:
      return True
    tags = {tag.casefold() for tag in pipeline_tags}
    if self.match_all:
      return self.keys <= tags
    return not self.keys.isdisjoint(tags)

  def describe(self) -> str:
    mode = "all" if self.match_all else "any"
    return f"tags {mode} of: {', '.join(self.labels)}"


def parse_tag_filter(text: Optional[str], match_all: bool = False) -> TagFilter:
  """Build a ``TagFilter`` from comma-separated user input.

  Blank entries are dropped and duplicates (ignoring case) keep their first spelling.

  Raises:
    ValueError: Too many tags, a tag is too long, or a tag contains control characters.
  """
  labels: List[str] = []
  seen: Set[str] = set()
  for raw in (text or "").split(","):
    label = raw.strip()
    if not label or label.casefold() in seen:
      continue
    if len(label) > MAX_FILTER_TAG_LENGTH:
      raise ValueError(f"Each tag must be at most {MAX_FILTER_TAG_LENGTH} characters long.")
    if any(unicodedata.category(char) == "Cc" for char in label):
      raise ValueError("Tags must not contain control characters.")
    seen.add(label.casefold())
    labels.append(label)
  if len(labels) > MAX_FILTER_TAGS:
    raise ValueError(f"Enter at most {MAX_FILTER_TAGS} tags.")
  return TagFilter(labels=tuple(labels), match_all=match_all)


@dataclass(frozen=True)
class VippetPipelineDefinition:
  """One ViPPET pipeline variant reduced to what Manager stores."""

  vippet_pipeline_id: str
  name: str
  pipeline: str


@dataclass
class SyncResult:
  """Outcome of a ViPPET sync, reported to the user."""

  created: List[str] = field(default_factory=list)
  updated: List[str] = field(default_factory=list)
  unchanged: int = 0
  skipped: List[str] = field(default_factory=list)
  warnings: List[str] = field(default_factory=list)
  pipelines_total: int = 0
  pipelines_matched: int = 0


def sync_vippet_pipelines(tag_filter: Optional[TagFilter] = None) -> SyncResult:
  """Import ViPPET vision pipeline variants as ``Pipeline`` rows.

  Rows are matched on ``vippet_pipeline_id`` (``<pipeline id>/<variant id>``) and named
  ``<pipeline name> (<variant name>)``. Rows no longer present in ViPPET are kept. A variant whose
  name is already used by another pipeline is skipped. Cameras assigned to a pipeline whose
  string changed get their DLSPS instance restarted.

  ``tag_filter`` limits which ViPPET pipelines are imported. Variants that were imported before
  are still updated even when their pipeline no longer matches; other non-matching variants are
  skipped without fetching their pipeline string.

  Raises:
    PipelineSyncError: The MLOps flow is disabled, ViPPET is not configured, or its pipeline
      list could not be fetched.
  """
  if not mlops_flow_enabled():
    raise PipelineSyncError(settings.MLOPS_FLOW_DISABLED_HINT)
  result = SyncResult()
  for definition in _fetch_vippet_definitions(result, tag_filter or TagFilter()):
    pipeline = _store_definition(definition, result)
    if pipeline is not None:
      result.warnings.extend(restart_pipeline_cameras(pipeline))
  return result


def _fetch_vippet_definitions(result: SyncResult,
                              tag_filter: TagFilter) -> List[VippetPipelineDefinition]:
  try:
    client = ViPPETClient()
  except ValueError as e:
    raise PipelineSyncError(
      f"ViPPET is not configured: set {VIPPET_URL_ENV} to the ViPPET API URL.") from e
  with client:
    try:
      summaries = client.get_pipelines()
    except ViPPETError as e:
      log.error(f"Failed to list ViPPET pipelines: {e}")
      raise PipelineSyncError(
        "Could not fetch pipelines from ViPPET; see Manager logs for details.") from e
    imported = set(Pipeline.objects.exclude(vippet_pipeline_id=None)
                   .values_list('vippet_pipeline_id', flat=True))
    result.pipelines_total = len(summaries)
    definitions = []
    for summary in summaries:
      matched = tag_filter.matches(summary.tags)
      result.pipelines_matched += matched
      for variant in summary.variants:
        if matched or _vippet_id(summary, variant) in imported:
          definitions.append(_fetch_variant(client, summary, variant, result))
    return [definition for definition in definitions if definition is not None]


def _vippet_id(summary, variant) -> str:
  return f"{summary.id}{VIPPET_ID_SEPARATOR}{variant.id}"


def _fetch_variant(client: ViPPETClient, summary, variant,
                   result: SyncResult) -> Optional[VippetPipelineDefinition]:
  name = f"{summary.name} ({variant.name})"
  try:
    pipeline_string = client.get_pipeline_string(summary.id, variant.id)
  except (ValueError, ViPPETError) as e:
    log.warning(f"Skipping ViPPET pipeline {summary.id} variant {variant.id}: {e}")
    result.skipped.append(f"{name}: could not fetch its pipeline string")
    return None
  return VippetPipelineDefinition(
    vippet_pipeline_id=_vippet_id(summary, variant),
    name=name,
    pipeline=pipeline_string,
  )


def _store_definition(definition: VippetPipelineDefinition,
                      result: SyncResult) -> Optional[Pipeline]:
  """Create or update the row; return it only when its pipeline string changed."""
  if len(definition.name) > MAX_PIPELINE_NAME_LENGTH:
    result.skipped.append(
      f"{definition.name[:60]}...: name exceeds {MAX_PIPELINE_NAME_LENGTH} characters")
    return None
  existing = Pipeline.objects.filter(vippet_pipeline_id=definition.vippet_pipeline_id).first()
  name_owners = Pipeline.objects.filter(name=definition.name)
  if existing is not None:
    name_owners = name_owners.exclude(pk=existing.pk)
  if name_owners.exists():
    result.skipped.append(f"{definition.name}: another pipeline already uses this name")
    return None
  if existing is None:
    _create_definition(definition, result)
    return None
  return _update_definition(existing, definition, result)


def _create_definition(definition: VippetPipelineDefinition, result: SyncResult) -> None:
  try:
    with transaction.atomic():
      Pipeline.objects.create(name=definition.name, pipeline=definition.pipeline,
                              vippet_pipeline_id=definition.vippet_pipeline_id)
  except IntegrityError:
    result.skipped.append(f"{definition.name}: another pipeline already uses this name")
    return
  result.created.append(definition.name)


def _update_definition(existing: Pipeline, definition: VippetPipelineDefinition,
                       result: SyncResult) -> Optional[Pipeline]:
  if existing.name == definition.name and existing.pipeline == definition.pipeline:
    result.unchanged += 1
    return None
  string_changed = existing.pipeline != definition.pipeline
  existing.name = definition.name
  existing.pipeline = definition.pipeline
  try:
    with transaction.atomic():
      existing.save(update_fields=['name', 'pipeline'])
  except IntegrityError:
    result.skipped.append(f"{definition.name}: another pipeline already uses this name")
    return None
  result.updated.append(definition.name)
  return existing if string_changed else None


def restart_pipeline_cameras(pipeline: Pipeline) -> List[str]:
  """Restart the DLSPS instance of each camera using ``pipeline``; return user warnings."""
  if not mlops_flow_enabled():
    return []
  warnings = []
  for cam_pk in pipeline.cameras.values_list('pk', flat=True):
    warnings.extend(apply_camera_pipeline(cam_pk, pipeline_changed=True))
  return warnings


def apply_camera_pipeline(cam_pk: int, *, pipeline_changed: bool) -> List[str]:
  """Start or stop the camera's DLSPS instance to match its selected pipeline.

  - Pipeline cleared: the running instance is stopped.
  - Pipeline selected or changed: the old instance (if any) is stopped and a new one started
    with automatic restarts enabled.
  - Pipeline unchanged: an instance is started only if none is recorded (e.g. a previous
    start failed), so saving the camera again retries.

  The camera row is locked while DLSPS is called so concurrent saves cannot start duplicate
  instances. DLSPS failures never raise; they are logged and returned as user-facing warnings.
  Does nothing while the MLOps flow is disabled.
  """
  if not mlops_flow_enabled():
    return []
  with transaction.atomic():
    cam = Cam.objects.select_for_update().get(pk=cam_pk)
    has_instance = cam.dlsps_instance_id is not None
    should_stop = has_instance and (cam.pipeline_id is None or pipeline_changed)
    should_start = cam.pipeline_id is not None and (should_stop or not has_instance)
    if not (should_stop or should_start):
      return []
    try:
      client = DLSPSClient()
    except ValueError:
      return [f"Camera '{cam.name}': DLSPS is not configured (set {DLSPS_URL_ENV}); "
              "its pipeline was not started or stopped."]
    with client:
      if should_stop and not _stop_camera_instance(client, cam):
        return [f"Camera '{cam.name}': failed to stop its running DLSPS pipeline; "
                "save the camera again to retry. See Manager logs for details."]
      if should_start:
        return _start_camera_instance(client, cam)
  return []


def _stop_camera_instance(client: DLSPSClient, cam: Cam) -> bool:
  try:
    client.delete_pipeline(cam.dlsps_instance_id)
  except (DLSPSNotFoundError, DLSPSConflictError):
    log.info(f"DLSPS instance {cam.dlsps_instance_id} of camera {cam.sensor_id} "
             "was already not running")
  except DLSPSError as e:
    log.error(f"Failed to stop DLSPS instance {cam.dlsps_instance_id} "
              f"of camera {cam.sensor_id}: {e}")
    return False
  _set_instance_id(cam, None)
  return True


def _start_camera_instance(client: DLSPSClient, cam: Cam) -> List[str]:
  pipeline = cam.pipeline
  try:
    instance_id = uuid.UUID(client.create_pipeline(pipeline.pipeline,
                                                   restart_config=RESTART_CONFIG))
  except (DLSPSError, ValueError) as e:
    log.error(f"Failed to start DLSPS pipeline '{pipeline.name}' for camera {cam.sensor_id}: {e}")
    return [f"Camera '{cam.name}': failed to start pipeline '{pipeline.name}' on DLSPS. "
            "Save the camera again to retry. See Manager logs for details."]
  _set_instance_id(cam, instance_id)
  log.info(f"Camera {cam.sensor_id} runs pipeline '{pipeline.name}' as DLSPS instance {instance_id}")
  return []


def _set_instance_id(cam: Cam, instance_id: Optional[uuid.UUID]) -> None:
  Cam.objects.filter(pk=cam.pk).update(dlsps_instance_id=instance_id)
  cam.dlsps_instance_id = instance_id


def stop_dlsps_instance(instance_id: uuid.UUID) -> None:
  """Best-effort stop of an instance whose camera no longer exists; errors are only logged."""
  try:
    with DLSPSClient() as client:
      client.delete_pipeline(instance_id)
  except (DLSPSNotFoundError, DLSPSConflictError):
    log.info(f"DLSPS instance {instance_id} was already not running")
  except ValueError:
    log.warning(f"DLSPS is not configured; instance {instance_id} of a deleted camera "
                "was not stopped")
  except DLSPSError as e:
    log.error(f"Failed to stop DLSPS instance {instance_id} of a deleted camera: {e}")
