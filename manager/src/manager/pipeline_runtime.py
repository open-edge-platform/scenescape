# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Connect stored pipelines with ViPPET (import) and DLSPS 2.0 (per-camera runtime).

ViPPET and DLSPS are called synchronously from the calling request. Callers must be restricted
to superusers because DLSPS executes the stored GStreamer strings as-is. Nothing here contacts
ViPPET or DLSPS unless the MLOps Flow is enabled (``settings.ENABLE_MLOPS_FLOW``).
"""

import hashlib
import re
import time
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
  PipelineState,
  PipelineStatus,
  RestartConfig,
)
from manager.models import Cam, PendingDLSPSStop, Pipeline
from manager.vippet import VIPPET_URL_ENV, ViPPETClient, ViPPETError
from scene_common import log

RESTART_CONFIG = RestartConfig(enabled=True)
ALIVE_STATES = frozenset({PipelineState.QUEUED, PipelineState.RUNNING, PipelineState.RESTARTING})
STOP_POLL_INTERVAL_S = 0.5
STATUS_DISPLAY_TIMEOUT_S = 2
MAX_STATUS_MESSAGE_LENGTH = 300
MAX_PENDING_STOP_ATTEMPTS = 10
VIPPET_ID_SEPARATOR = "/"
MAX_PIPELINE_NAME_LENGTH = Pipeline._meta.get_field('name').max_length
MAX_FILTER_TAGS = 20
MAX_FILTER_TAG_LENGTH = 100
PUBLISH_ELEMENT = "sscape_post_inference_data_publish"
# The publish element followed by its "key=value" properties (values may be double-quoted).
_PUBLISH_ELEMENT_RE = re.compile(
  rf'(?<![\w-]){PUBLISH_ELEMENT}(?![\w-])(?:\s+[\w-]+=(?:"(?:[^"\\]|\\.)*"|[^\s!"]+))*')
_CAMERAID_PROPERTY_RE = re.compile(r'\s+cameraid=(?:"(?:[^"\\]|\\.)*"|[^\s!"]+)')


class PipelineSyncError(Exception):
  """ViPPET could not be queried at all; no pipelines were changed."""


def mlops_flow_enabled() -> bool:
  """Return True when Manager runs with the MLOps Flow (ViPPET / DLSPS integration) enabled."""
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
    PipelineSyncError: The MLOps Flow is disabled, ViPPET is not configured, or its pipeline
      list could not be fetched.
  """
  if not mlops_flow_enabled():
    raise PipelineSyncError(settings.MLOPS_FLOW_DISABLED_HINT)
  result = SyncResult()
  for definition in _fetch_vippet_definitions(result, tag_filter or TagFilter()):
    pipeline = _store_definition(definition, result)
    if pipeline is not None:
      result.warnings.extend(reconcile_pipeline_cameras(pipeline))
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


def reconcile_pipeline_cameras(pipeline: Pipeline) -> List[str]:
  """Reconcile the DLSPS instance of each camera using ``pipeline``; return user warnings."""
  if not mlops_flow_enabled():
    return []
  warnings = []
  for cam_pk in pipeline.cameras.values_list('pk', flat=True):
    warnings.extend(reconcile_camera_pipeline(cam_pk))
  return warnings


def bind_pipeline_to_camera(pipeline_string: str, sensor_id: str) -> str:
  """Set ``cameraid`` on every Scenescape publish element to the camera's sensor id.

  Pipelines imported from ViPPET do not know which Scenescape camera they run for, and the
  publish element sends nothing until ``cameraid`` is set. Any existing value is replaced.
  """
  escaped = sensor_id.replace('\\', '\\\\').replace('"', '\\"')

  def bind(match: re.Match) -> str:
    element = _CAMERAID_PROPERTY_RE.sub('', match.group(0))
    return f'{element} cameraid="{escaped}"'

  return _PUBLISH_ELEMENT_RE.sub(bind, pipeline_string)


def _bound_pipeline(cam: Cam) -> Optional[Tuple[str, str]]:
  """Return the pipeline string DLSPS should run for ``cam`` and its digest, or None."""
  if cam.pipeline is None:
    return None
  bound = bind_pipeline_to_camera(cam.pipeline.pipeline, cam.sensor_id)
  return bound, hashlib.sha256(bound.encode()).hexdigest()


def reconcile_camera_pipeline(cam_pk: int) -> List[str]:
  """Make the camera's DLSPS instance match its selected pipeline.

  The desired state is the selected pipeline bound to the camera's current ID. The recorded
  instance is kept only while it is alive in DLSPS and runs exactly that string; otherwise it
  is stopped (and confirmed stopped) before a new instance is started with automatic restarts.
  So a changed selection, an edited or synced pipeline string, a changed camera ID, an
  instance that DLSPS rejected or that ended, and an earlier failed stop or start are all
  handled by saving the camera again.

  The camera row is locked while DLSPS is called. An instance that cannot be confirmed stopped
  stays recorded and no replacement is started, so one camera never runs two instances.
  DLSPS failures never raise; they are logged and returned as user-facing warnings.
  Does nothing while the MLOps Flow is disabled.
  """
  if not mlops_flow_enabled():
    return []
  retry_pending_stops()
  with transaction.atomic():
    cam = Cam.objects.select_for_update().get(pk=cam_pk)
    desired = _bound_pipeline(cam)
    if cam.dlsps_instance_id is None and desired is None:
      return []
    try:
      client = DLSPSClient()
    except ValueError:
      return [f"Camera '{cam.name}': DLSPS is not configured (set {DLSPS_URL_ENV}); "
              "its pipeline was not started or stopped."]
    with client:
      return _reconcile(client, cam, desired)


def _reconcile(client: DLSPSClient, cam: Cam, desired: Optional[Tuple[str, str]]) -> List[str]:
  warnings: List[str] = []
  if cam.dlsps_instance_id is not None:
    try:
      status = _instance_status(client, cam.dlsps_instance_id)
    except DLSPSError as e:
      log.error(f"Failed to query DLSPS instance {cam.dlsps_instance_id} "
                f"of camera {cam.sensor_id}: {e}")
      return [f"Camera '{cam.name}': could not check its DLSPS pipeline, so it was not "
              "updated. Save the camera again to retry. See Manager logs for details."]
    if not _is_alive(status):
      warnings.extend(_report_ended_instance(cam, status))
      _set_runtime(cam, None, None)
    elif desired is not None and cam.dlsps_pipeline_digest == desired[1]:
      return warnings
    elif _stop_and_confirm(client, cam.dlsps_instance_id, status):
      _set_runtime(cam, None, None)
    else:
      return warnings + [
        f"Camera '{cam.name}': its running DLSPS pipeline has not stopped yet, so the new "
        "pipeline was not started. Save the camera again to retry."]
  if desired is not None:
    warnings.extend(_start_camera_instance(client, cam, *desired))
  return warnings


def _instance_status(client: DLSPSClient, instance_id: uuid.UUID) -> Optional[PipelineStatus]:
  """Return the instance status, or None when DLSPS no longer knows the instance."""
  try:
    return client.get_pipeline_status(instance_id)
  except DLSPSNotFoundError:
    return None


def _is_alive(status: Optional[PipelineStatus]) -> bool:
  return status is not None and status.state in ALIVE_STATES


def _report_ended_instance(cam: Cam, status: Optional[PipelineStatus]) -> List[str]:
  state = status.state.value if status is not None else "unknown to DLSPS"
  log.warning(f"DLSPS instance {cam.dlsps_instance_id} of camera {cam.sensor_id} "
              f"is no longer running ({state})")
  if status is None or status.state is not PipelineState.ERROR:
    return []
  detail = f": {status.message[:MAX_STATUS_MESSAGE_LENGTH]}" if status.message else ""
  return [f"Camera '{cam.name}': its previous DLSPS pipeline failed{detail}"]


def _stop_and_confirm(client: DLSPSClient, instance_id: uuid.UUID,
                      status: Optional[PipelineStatus] = None,
                      timeout_s: Optional[float] = None) -> bool:
  """Stop an instance and return True only once DLSPS reports it ended or unknown.

  DLSPS acknowledges ``DELETE`` before the pipeline actually stops and cannot stop a QUEUED
  instance at all, so the state is polled for up to ``timeout_s`` (default
  ``settings.DLSPS_STOP_TIMEOUT_S``). Returns False when the stop is not confirmed in time or
  DLSPS cannot be reached; the caller must then keep the instance recorded.
  """
  timeout_s = settings.DLSPS_STOP_TIMEOUT_S if timeout_s is None else timeout_s
  deadline = time.monotonic() + timeout_s
  stop_requested = False
  try:
    if status is None:
      status = _instance_status(client, instance_id)
    while _is_alive(status):
      if not stop_requested and status.state is not PipelineState.QUEUED:
        _request_stop(client, instance_id)
        stop_requested = True
      elif time.monotonic() >= deadline:
        log.warning(f"DLSPS instance {instance_id} did not stop within {timeout_s:g} s "
                    f"(state {status.state.value})")
        return False
      else:
        time.sleep(STOP_POLL_INTERVAL_S)
      status = _instance_status(client, instance_id)
    return True
  except DLSPSError as e:
    log.error(f"Failed to stop DLSPS instance {instance_id}: {e}")
    return False


def _request_stop(client: DLSPSClient, instance_id: uuid.UUID) -> None:
  try:
    client.delete_pipeline(instance_id)
  except (DLSPSNotFoundError, DLSPSConflictError) as e:
    # Not running (anymore): the state poll that follows decides whether it ended.
    log.info(f"DLSPS did not accept a stop of instance {instance_id}: {e}")


def _start_camera_instance(client: DLSPSClient, cam: Cam, bound_pipeline: str,
                           digest: str) -> List[str]:
  pipeline = cam.pipeline
  try:
    instance_id = uuid.UUID(client.create_pipeline(bound_pipeline, restart_config=RESTART_CONFIG))
  except (DLSPSError, ValueError) as e:
    log.error(f"Failed to start DLSPS pipeline '{pipeline.name}' for camera {cam.sensor_id}: {e}")
    return [f"Camera '{cam.name}': failed to start pipeline '{pipeline.name}' on DLSPS. "
            "Save the camera again to retry. See Manager logs for details."]
  _set_runtime(cam, instance_id, digest)
  log.info(f"Camera {cam.sensor_id} runs pipeline '{pipeline.name}' as DLSPS instance {instance_id}")
  return []


def _set_runtime(cam: Cam, instance_id: Optional[uuid.UUID], digest: Optional[str]) -> None:
  Cam.objects.filter(pk=cam.pk).update(dlsps_instance_id=instance_id,
                                       dlsps_pipeline_digest=digest)
  cam.dlsps_instance_id = instance_id
  cam.dlsps_pipeline_digest = digest


def stop_deleted_camera_instance(instance_id: uuid.UUID) -> None:
  """Stop the instance of a deleted camera; remember it for later retries if not confirmed."""
  try:
    with DLSPSClient() as client:
      if _stop_and_confirm(client, instance_id):
        log.info(f"Stopped DLSPS instance {instance_id} of a deleted camera")
        return
  except ValueError:
    log.warning(f"DLSPS is not configured; instance {instance_id} of a deleted camera "
                "will be stopped once it is")
  PendingDLSPSStop.objects.get_or_create(instance_id=instance_id)


def retry_pending_stops(timeout_s: float = 0) -> None:
  """Retry stopping instances of deleted cameras; give up after ``MAX_PENDING_STOP_ATTEMPTS``.

  Each attempt requests the stop without waiting (unless ``timeout_s`` is set); a later attempt
  confirms that the instance ended. Rows locked by a concurrent retry are skipped.
  """
  if not mlops_flow_enabled():
    return
  with transaction.atomic():
    pending = list(PendingDLSPSStop.objects.select_for_update(skip_locked=True))
    if not pending:
      return
    try:
      client = DLSPSClient()
    except ValueError:
      return
    with client:
      for entry in pending:
        _retry_pending_stop(client, entry, timeout_s)


def _retry_pending_stop(client: DLSPSClient, entry: PendingDLSPSStop, timeout_s: float) -> None:
  if _stop_and_confirm(client, entry.instance_id, timeout_s=timeout_s):
    log.info(f"Stopped DLSPS instance {entry.instance_id} of a deleted camera")
    entry.delete()
    return
  entry.attempts += 1
  if entry.attempts >= MAX_PENDING_STOP_ATTEMPTS:
    log.error(f"Giving up stopping DLSPS instance {entry.instance_id} of a deleted camera "
              f"after {entry.attempts} attempts; stop it manually")
    entry.delete()
    return
  entry.last_error = "stop not confirmed"
  entry.save(update_fields=['attempts', 'last_error'])


def stop_all_camera_instances() -> None:
  """Stop every recorded camera instance and pending stop, waiting for each (demo shutdown)."""
  if not mlops_flow_enabled():
    return
  try:
    client = DLSPSClient()
  except ValueError:
    log.warning("DLSPS is not configured; no camera pipelines were stopped")
    return
  with client:
    for cam_pk in Cam.objects.exclude(dlsps_instance_id=None).values_list('pk', flat=True):
      with transaction.atomic():
        cam = Cam.objects.select_for_update().get(pk=cam_pk)
        if cam.dlsps_instance_id is not None \
            and _stop_and_confirm(client, cam.dlsps_instance_id):
          _set_runtime(cam, None, None)
  retry_pending_stops(timeout_s=settings.DLSPS_STOP_TIMEOUT_S)


def describe_camera_instance(cam: Cam) -> Optional[dict]:
  """Live DLSPS state of the camera's recorded instance for display, or None if none.

  Uses a short timeout and never raises: an unreachable DLSPS is reported as state "UNKNOWN".
  """
  if not mlops_flow_enabled() or cam.pk is None or cam.dlsps_instance_id is None:
    return None
  try:
    with DLSPSClient(timeout=STATUS_DISPLAY_TIMEOUT_S) as client:
      status = _instance_status(client, cam.dlsps_instance_id)
  except ValueError:
    return {'state': 'UNKNOWN', 'message': f"DLSPS is not configured (set {DLSPS_URL_ENV})."}
  except DLSPSError as e:
    log.warning(f"Failed to query DLSPS instance {cam.dlsps_instance_id}: {e}")
    return {'state': 'UNKNOWN', 'message': "DLSPS could not be reached."}
  if status is None:
    return {'state': 'NOT FOUND',
            'message': "DLSPS no longer knows this instance; save the camera to restart it."}
  return {'state': status.state.value, 'message': status.message[:MAX_STATUS_MESSAGE_LENGTH]}
