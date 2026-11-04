# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Connect stored pipelines with ViPPET (import) and DLSPS 2.0 (per-camera runtime).

ViPPET and DLSPS are called synchronously from the calling request. Callers must be restricted
to superusers because DLSPS executes the stored GStreamer strings as-is.
"""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

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


class PipelineSyncError(Exception):
  """ViPPET could not be queried at all; no pipelines were changed."""


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


def sync_vippet_pipelines() -> SyncResult:
  """Import every ViPPET vision pipeline variant as a ``Pipeline`` row.

  Rows are matched on ``vippet_pipeline_id`` (``<pipeline id>/<variant id>``) and named
  ``<pipeline name> (<variant name>)``. Rows no longer present in ViPPET are kept. A variant whose
  name is already used by another pipeline is skipped. Cameras assigned to a pipeline whose
  string changed get their DLSPS instance restarted.

  Raises:
    PipelineSyncError: ViPPET is not configured or its pipeline list could not be fetched.
  """
  result = SyncResult()
  for definition in _fetch_vippet_definitions(result):
    pipeline = _store_definition(definition, result)
    if pipeline is not None:
      result.warnings.extend(restart_pipeline_cameras(pipeline))
  return result


def _fetch_vippet_definitions(result: SyncResult) -> List[VippetPipelineDefinition]:
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
    definitions = (_fetch_variant(client, summary, variant, result)
                   for summary in summaries for variant in summary.variants)
    return [definition for definition in definitions if definition is not None]


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
    vippet_pipeline_id=f"{summary.id}{VIPPET_ID_SEPARATOR}{variant.id}",
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
  """
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
