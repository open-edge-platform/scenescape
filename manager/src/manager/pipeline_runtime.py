# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Connect stored pipelines with ViPPET (import) and DLSPS 2.0 (per-camera runtime).

ViPPET is called during the request. DLSPS reconciliation runs after any enclosing transaction
commits. Callers must be restricted to superusers because DLSPS executes the stored GStreamer
strings as-is. Nothing here contacts ViPPET or DLSPS unless the MLOps Flow is enabled
(``settings.ENABLE_MLOPS_FLOW``).
"""

import hashlib
import re
import time
import unicodedata
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Callable, FrozenSet, Iterable, List, Optional, Set, Tuple

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q

from manager.dlsps import (
  DLSPS_URL_ENV,
  DLSPSBadRequestError,
  DLSPSClient,
  DLSPSConflictError,
  DLSPSError,
  DLSPSNotFoundError,
  PipelineState,
  PipelineStatus,
  PipelineSummary,
  RestartConfig,
)
from manager.models import Cam, PendingDLSPSStop, Pipeline
from manager.vippet import VIPPET_URL_ENV, ViPPETClient, ViPPETError
from scene_common import log

RESTART_CONFIG = RestartConfig(enabled=True)
ALIVE_STATES = frozenset({PipelineState.QUEUED, PipelineState.RUNNING, PipelineState.RESTARTING})
# DLSPS answered and refused the start, so no instance was created.
START_REJECTIONS = (DLSPSBadRequestError, DLSPSNotFoundError, DLSPSConflictError)
STOP_POLL_INTERVAL_S = 0.5
STATUS_DISPLAY_TIMEOUT_S = 2
MAX_STATUS_MESSAGE_LENGTH = 300
MAX_PENDING_STOP_ATTEMPTS = 10
VIPPET_ID_SEPARATOR = "/"
MAX_PIPELINE_NAME_LENGTH = Pipeline._meta.get_field('name').max_length
MAX_FILTER_TAGS = 20
MAX_FILTER_TAG_LENGTH = 100
PUBLISH_ELEMENT = "sscape_post_inference_data_publish"
# Every launch string gets this inert, unlinked element appended, named after the launch attempt,
# so the instance of a start request whose answer was lost can be found again.
LAUNCH_MARKER_PREFIX = "sscape-launch-"
# One gst-launch token: a property (``key=value``, spaces around ``=`` allowed), a run of unquoted
# characters, backslash escapes and quoted strings, or one of the link characters ``!``, ``(``,
# ``)``. An unterminated quote takes the rest of the string.
_LAUNCH_VALUE = r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\\.|[^\s!()"'\\])"""
_LAUNCH_TOKEN_RE = re.compile(
  rf"""[\w-]+\s*=\s*{_LAUNCH_VALUE}*|{_LAUNCH_VALUE}+|[!()]|["'].*""", re.S)


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
  """Outcome of a ViPPET sync, including warnings from immediate reconciliation."""

  created: List[str] = field(default_factory=list)
  updated: List[str] = field(default_factory=list)
  unchanged: int = 0
  skipped: List[str] = field(default_factory=list)
  warnings: List[str] = field(default_factory=list)
  pipelines_total: int = 0
  pipelines_matched: int = 0


def sync_vippet_pipelines(tag_filter: Optional[TagFilter] = None, *,
                          on_warnings: Optional[Callable[[List[str]], None]] = None) -> SyncResult:
  """Import ViPPET vision pipeline variants as ``Pipeline`` rows.

  Rows are matched on ``vippet_pipeline_id`` (``<pipeline id>/<variant id>``) and named
  ``<pipeline name> (<variant name>)``. Rows no longer present in ViPPET are kept. A variant whose
  name is already used by another pipeline is skipped. Cameras assigned to a pipeline whose
  string changed get their DLSPS instance restarted.

  ``tag_filter`` limits which ViPPET pipelines are imported. Variants that were imported before
  are still updated even when their pipeline no longer matches; other non-matching variants are
  skipped without fetching their pipeline string.

  Deferred reconciliation warnings are delivered through ``on_warnings``, or logged when no
  callback is supplied.

  Raises:
    PipelineSyncError: The MLOps Flow is disabled, ViPPET is not configured, or its pipeline
      list could not be fetched.
  """
  if not mlops_flow_enabled():
    raise PipelineSyncError(settings.MLOPS_FLOW_DISABLED_HINT)
  retry_pending_stops()
  result = SyncResult()
  for definition in _fetch_vippet_definitions(result, tag_filter or TagFilter()):
    pipeline = _store_definition(definition, result)
    if pipeline is not None:
      result.warnings.extend(reconcile_pipeline_cameras(pipeline, on_warnings=on_warnings))
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


def reconcile_pipeline_cameras(
    pipeline: Pipeline, *, on_warnings: Optional[Callable[[List[str]], None]] = None) -> List[str]:
  """Reconcile the DLSPS instance of each camera using ``pipeline``; return user warnings."""
  if not mlops_flow_enabled():
    return []
  warnings = []
  for cam_pk in pipeline.cameras.values_list('pk', flat=True):
    warnings.extend(reconcile_camera_pipeline(cam_pk, on_warnings=on_warnings))
  return warnings


def _launch_tokens(pipeline_string: str) -> List[Tuple[int, int]]:
  """Split a gst-launch string into token spans, keeping quoted text inside its token."""
  return [match.span() for match in _LAUNCH_TOKEN_RE.finditer(pipeline_string)]


def _property_name(token: str) -> Optional[str]:
  """Return the property name of a ``key=value`` token, or None for other tokens."""
  name, separator, _value = token.partition("=")
  name = name.strip()
  if separator and name and all(c.isalnum() or c in "_-" for c in name):
    return name
  return None


def bind_pipeline_to_camera(pipeline_string: str, sensor_id: str) -> str:
  """Set ``cameraid`` on every Scenescape publish element to the camera's sensor id.

  Pipelines imported from ViPPET do not know which Scenescape camera they run for, and the
  publish element sends nothing until ``cameraid`` is set. Any existing value is replaced. Only
  element declarations are changed: the element name inside a quoted property value is not.
  """
  escaped = sensor_id.replace('\\', '\\\\').replace('"', '\\"')
  tokens = _launch_tokens(pipeline_string)
  edits: List[Tuple[int, int, str]] = []
  for index, (start, end) in enumerate(tokens):
    if pipeline_string[start:end] != PUBLISH_ELEMENT:
      continue
    last_end = end
    for prop_start, prop_end in tokens[index + 1:]:
      name = _property_name(pipeline_string[prop_start:prop_end])
      if name is None:
        break
      if name == "cameraid":
        # Drop the property together with the whitespace before it.
        edits.append((last_end, prop_end, ""))
      last_end = prop_end
    edits.append((last_end, last_end, f' cameraid="{escaped}"'))
  for start, end, text in sorted(edits, reverse=True):
    pipeline_string = pipeline_string[:start] + text + pipeline_string[end:]
  return pipeline_string


def _bound_pipeline(cam: Cam) -> Optional[Tuple[str, str]]:
  """Return the pipeline string DLSPS should run for ``cam`` and its digest, or None."""
  if cam.pipeline is None:
    return None
  bound = bind_pipeline_to_camera(cam.pipeline.pipeline, cam.sensor_id)
  return bound, _digest(bound)


def _digest(launch_string: str) -> str:
  return hashlib.sha256(launch_string.encode()).hexdigest()


def launch_marker(launch_id: uuid.UUID) -> str:
  """Suffix appended to the launch string of attempt ``launch_id``.

  An unlinked ``identity`` element never receives data, so it does not change what the pipeline
  does; DLSPS keeps it in the instance's ``launch_command``, which is the only data DLSPS keeps
  for an inline start.
  """
  return f" identity name={LAUNCH_MARKER_PREFIX}{launch_id}"


def reconcile_camera_pipeline(
    cam_pk: int, *, on_warnings: Optional[Callable[[List[str]], None]] = None) -> List[str]:
  """Make the camera's DLSPS instance match its selected pipeline.

  The desired state is the selected pipeline bound to the camera's current ID. The recorded
  instance is kept only while it is alive in DLSPS and runs exactly that string; otherwise it
  is stopped (and confirmed stopped) before a new instance is started with automatic restarts.
  So a changed selection, an edited or synced pipeline string, a changed camera ID, an
  instance that DLSPS rejected or that ended, and an earlier failed stop or start are all
  handled by saving the camera again. When an earlier start request got no answer, the live
  instance carrying that attempt's launch marker (if any) is adopted before anything new is
  started, and nothing is started while DLSPS cannot be checked.

  When called inside a transaction, reconciliation is deferred until commit. Before a start,
  its unique launch id and digest are committed independently; the camera row is then locked
  again while DLSPS is called. A rollback or worker exit cannot erase the recovery handle.
  An instance that cannot be confirmed stopped stays recorded and no replacement is started.

  Warnings are returned for immediate reconciliation and passed to ``on_warnings``, if supplied,
  for both immediate and deferred reconciliation. Deferred warnings without a callback are logged.
  Does nothing while the MLOps Flow is disabled.
  """
  if not mlops_flow_enabled():
    return []
  if transaction.get_connection().in_atomic_block:
    transaction.on_commit(lambda: _reconcile_and_report(cam_pk, on_warnings, deferred=True))
    return []
  if not transaction.get_autocommit():
    raise transaction.TransactionManagementError(
      "DLSPS reconciliation requires autocommit or a transaction.atomic() block.")
  return _reconcile_and_report(cam_pk, on_warnings)


def _reconcile_and_report(cam_pk: int, on_warnings: Optional[Callable[[List[str]], None]],
                          deferred: bool = False) -> List[str]:
  if not mlops_flow_enabled():
    return []
  warnings = _reconcile_camera_pipeline_now(cam_pk)
  if on_warnings is not None:
    on_warnings(warnings)
  elif deferred:
    for warning in warnings:
      log.warning(f"Deferred DLSPS reconciliation: {warning}")
  return warnings


def _reconcile_camera_pipeline_now(cam_pk: int) -> List[str]:
  retry_pending_stops()
  with ExitStack() as stack:
    with transaction.atomic(durable=True):
      cam = Cam.objects.select_for_update().filter(pk=cam_pk).first()
      if cam is None:
        return []
      desired = _bound_pipeline(cam)
      if cam.dlsps_instance_id is None and cam.dlsps_launch_id is None and desired is None:
        return []
      try:
        client = stack.enter_context(DLSPSClient())
      except ValueError:
        return [f"Camera '{cam.name}': DLSPS is not configured (set {DLSPS_URL_ENV}); "
                "its pipeline was not started or stopped."]
      warnings, launch_id = _prepare_reconciliation(client, cam, desired)
    if launch_id is not None:
      warnings.extend(_start_prepared_pipeline(client, cam_pk, launch_id))
    return warnings


def _prepare_reconciliation(
    client: DLSPSClient, cam: Cam,
    desired: Optional[Tuple[str, str]]) -> Tuple[List[str], Optional[uuid.UUID]]:
  if cam.dlsps_start_uncertain and not _resolve_uncertain_start(client, cam):
    return ([f"Camera '{cam.name}': could not check whether its last pipeline start reached "
             "DLSPS, so no new pipeline was started. Save the camera again to retry. See "
             "Manager logs for details."], None)
  warnings: List[str] = []
  if cam.dlsps_instance_id is not None:
    try:
      status = _instance_status(client, cam.dlsps_instance_id)
    except DLSPSError as e:
      log.error(f"Failed to query DLSPS instance {cam.dlsps_instance_id} "
                f"of camera {cam.sensor_id}: {e}")
      return ([f"Camera '{cam.name}': could not check its DLSPS pipeline, so it was not "
               "updated. Save the camera again to retry. See Manager logs for details."], None)
    if not _is_alive(status):
      warnings.extend(_report_ended_instance(cam, status))
      _set_runtime(cam, None, None)
    elif desired is not None and cam.dlsps_pipeline_digest == desired[1]:
      return warnings, None
    elif _stop_and_confirm(client, cam.dlsps_instance_id, status):
      _set_runtime(cam, None, None)
    else:
      return warnings + [
        f"Camera '{cam.name}': its running DLSPS pipeline has not stopped yet, so the new "
        "pipeline was not started. Save the camera again to retry."], None
  if desired is not None:
    launch_id = uuid.uuid4()
    _set_runtime(cam, None, desired[1], launch_id)
    return warnings, launch_id
  return warnings, None


def _start_prepared_pipeline(client: DLSPSClient, cam_pk: int, launch_id: uuid.UUID) -> List[str]:
  """Start only if this committed intent still belongs to the camera's current selection."""
  with transaction.atomic(durable=True):
    cam = Cam.objects.select_for_update().filter(pk=cam_pk).first()
    if cam is None or cam.dlsps_launch_id != launch_id or cam.dlsps_instance_id is not None:
      return []
    desired = _bound_pipeline(cam)
    if desired is None or desired[1] != cam.dlsps_pipeline_digest:
      _set_runtime(cam, None, None)
      if desired is not None:
        return [f"Camera '{cam.name}': its pipeline changed while a start was being prepared. "
                "Save the camera again to retry."]
      return []
    return _start_camera_instance(client, cam, *desired, launch_id)


def _resolve_uncertain_start(client: DLSPSClient, cam: Cam) -> bool:
  """Adopt the instance an unanswered start request may have created; False if unknown."""
  try:
    instance_id = _find_launched_instance(client, cam.dlsps_launch_id, owner_pk=cam.pk)
  except DLSPSError as e:
    log.error(f"Failed to look for the unconfirmed DLSPS start of camera {cam.sensor_id}: {e}")
    return False
  if instance_id is None:
    log.info(f"The unconfirmed DLSPS start of camera {cam.sensor_id} left no running instance")
    _set_runtime(cam, None, None)
  else:
    log.info(f"Camera {cam.sensor_id} adopts DLSPS instance {instance_id} from an unconfirmed start")
    _set_runtime(cam, instance_id, cam.dlsps_pipeline_digest, cam.dlsps_launch_id)
  return True


def _find_launched_instance(client: DLSPSClient, launch_id: uuid.UUID,
                            owner_pk: Optional[int] = None) -> Optional[uuid.UUID]:
  """Return the QUEUED/RUNNING/RESTARTING instance started by launch attempt ``launch_id``.

  Instances recorded by a camera other than ``owner_pk`` are never returned.

  Raises:
    DLSPSError: DLSPS could not be queried, or a live instance has an invalid ID or no launch
      command, so the attempt's instance cannot be ruled out.
  """
  marker = launch_marker(launch_id)
  lookup_error = None
  for status in client.list_pipeline_statuses():
    if status.state not in ALIVE_STATES:
      continue
    found, error = _live_instance_summary(client, status)
    if error is not None:
      lookup_error = error
      continue
    if found is None:
      continue
    summary, launch_command = found
    if not launch_command.endswith(marker):
      continue
    instance_id = _parse_instance_id(summary.id)
    if Cam.objects.filter(dlsps_instance_id=instance_id).exclude(pk=owner_pk).exists():
      log.warning(f"DLSPS instance {instance_id} carries launch marker {launch_id} but is "
                  "recorded by another camera; not adopting it")
      continue
    return instance_id
  if lookup_error is not None:
    raise lookup_error
  return None


def _live_instance_summary(
    client: DLSPSClient, status: PipelineStatus
    ) -> Tuple[Optional[Tuple[PipelineSummary, str]], Optional[DLSPSError]]:
  """Fetch a live instance, retaining inconclusive ID or missing-command errors for the scan."""
  try:
    status_id = _parse_instance_id(status.id)
  except DLSPSError as e:
    return None, e
  try:
    summary = client.get_pipeline(status_id)
  except DLSPSNotFoundError:
    return None, None
  if summary.launch_command is None:
    return None, DLSPSError(f"DLSPS reported no launch command for live instance {status.id}")
  return (summary, summary.launch_command), None


def _parse_instance_id(value: str) -> uuid.UUID:
  try:
    return uuid.UUID(value)
  except ValueError as e:
    raise DLSPSError(f"DLSPS returned an invalid instance id {value!r}") from e


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

  DLSPS acknowledges ``DELETE`` before the pipeline has stopped, and some DLSPS versions reject
  it (409) while the instance is QUEUED, so the stop is requested until accepted and the state
  is polled for up to ``timeout_s`` (default ``settings.DLSPS_STOP_TIMEOUT_S``). Returns False
  when the stop is not confirmed in time or DLSPS cannot be reached; the caller must then keep
  the instance recorded.
  """
  timeout_s = settings.DLSPS_STOP_TIMEOUT_S if timeout_s is None else timeout_s
  deadline = time.monotonic() + timeout_s
  stop_accepted = False
  try:
    if status is None:
      status = _instance_status(client, instance_id)
    while _is_alive(status):
      just_accepted = False
      if not stop_accepted:
        stop_accepted = just_accepted = _request_stop(client, instance_id)
      if not just_accepted:
        if time.monotonic() >= deadline:
          log.warning(f"DLSPS instance {instance_id} did not stop within {timeout_s:g} s "
                      f"(state {status.state.value})")
          return False
        time.sleep(STOP_POLL_INTERVAL_S)
      status = _instance_status(client, instance_id)
    return True
  except DLSPSError as e:
    log.error(f"Failed to stop DLSPS instance {instance_id}: {e}")
    return False


def _request_stop(client: DLSPSClient, instance_id: uuid.UUID) -> bool:
  """Ask DLSPS to stop the instance; False when DLSPS cannot stop it in its current state."""
  try:
    client.delete_pipeline(instance_id)
  except (DLSPSNotFoundError, DLSPSConflictError) as e:
    # Gone, ended, or not stoppable yet (QUEUED): the state poll that follows decides.
    log.info(f"DLSPS did not accept a stop of instance {instance_id}: {e}")
    return False
  return True


def _start_camera_instance(client: DLSPSClient, cam: Cam, bound_pipeline: str,
                           digest: str, launch_id: uuid.UUID) -> List[str]:
  pipeline = cam.pipeline
  try:
    response = client.create_pipeline(bound_pipeline + launch_marker(launch_id),
                                      restart_config=RESTART_CONFIG)
  except (ValueError, *START_REJECTIONS) as e:
    return _report_start_rejection(cam, e)
  except DLSPSError as e:
    if e.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
      return _report_start_rejection(cam, e)
    return _record_uncertain_start(cam, digest, launch_id, e)
  try:
    instance_id = uuid.UUID(response)
  except ValueError as e:
    return _record_uncertain_start(cam, digest, launch_id, e)
  _set_runtime(cam, instance_id, digest, launch_id)
  log.info(f"Camera {cam.sensor_id} runs pipeline '{pipeline.name}' as DLSPS instance {instance_id}")
  return []


def _report_start_rejection(cam: Cam, error: Exception) -> List[str]:
  log.error(f"Failed to start DLSPS pipeline '{cam.pipeline.name}' for camera {cam.sensor_id}: "
            f"{error}")
  _set_runtime(cam, None, None)
  return [f"Camera '{cam.name}': failed to start pipeline '{cam.pipeline.name}' on DLSPS. "
          "Save the camera again to retry. See Manager logs for details."]


def _record_uncertain_start(cam: Cam, digest: str, launch_id: uuid.UUID,
                            error: Exception) -> List[str]:
  """Remember a start whose outcome is unknown, so it is checked before starting again."""
  log.error(f"DLSPS did not confirm the start of pipeline '{cam.pipeline.name}' for camera "
            f"{cam.sensor_id} (launch {launch_id}); it may be running: {error}")
  _set_runtime(cam, None, digest, launch_id)
  return [f"Camera '{cam.name}': DLSPS did not confirm the start of pipeline "
          f"'{cam.pipeline.name}'. Save the camera again to check whether it is running; "
          "no second instance is started before that check succeeds."]


def _set_runtime(cam: Cam, instance_id: Optional[uuid.UUID], digest: Optional[str],
                 launch_id: Optional[uuid.UUID] = None) -> None:
  Cam.objects.filter(pk=cam.pk).update(dlsps_instance_id=instance_id,
                                       dlsps_pipeline_digest=digest,
                                       dlsps_launch_id=launch_id)
  cam.dlsps_instance_id = instance_id
  cam.dlsps_pipeline_digest = digest
  cam.dlsps_launch_id = launch_id


def record_deleted_camera_instance(cam_pk: int) -> None:
  """Queue the stop of a camera's DLSPS instance as part of deleting the camera.

  Must run inside the deletion transaction (``pre_delete``). The row is re-read under the lock
  that reconciliation holds, so an instance started concurrently or after the caller loaded the
  camera is not missed, and the pending stop commits or rolls back with the deletion. The stop
  itself is attempted after commit and retried later if it cannot be confirmed.
  """
  runtime = (Cam.objects.select_for_update().filter(pk=cam_pk)
             .values('dlsps_instance_id', 'dlsps_launch_id').first())
  if runtime is None:
    return
  if runtime['dlsps_instance_id'] is not None:
    entry, _ = PendingDLSPSStop.objects.get_or_create(instance_id=runtime['dlsps_instance_id'])
  elif runtime['dlsps_launch_id'] is not None:
    entry, _ = PendingDLSPSStop.objects.get_or_create(launch_id=runtime['dlsps_launch_id'])
  else:
    return
  transaction.on_commit(lambda: retry_pending_stops(
    timeout_s=settings.DLSPS_STOP_TIMEOUT_S, entry_pk=entry.pk))


def retry_pending_stops(timeout_s: float = 0, entry_pk: Optional[int] = None) -> None:
  """Retry stopping instances of deleted cameras; give up after ``MAX_PENDING_STOP_ATTEMPTS``.

  Each attempt requests the stop without waiting (unless ``timeout_s`` is set); a later attempt
  confirms that the instance ended. ``entry_pk`` limits the retry to one entry. Rows locked by a
  concurrent retry are skipped.
  """
  if not mlops_flow_enabled():
    return
  with transaction.atomic():
    pending = PendingDLSPSStop.objects.select_for_update(skip_locked=True)
    if entry_pk is not None:
      pending = pending.filter(pk=entry_pk)
    pending = list(pending)
    if not pending:
      return
    try:
      client = DLSPSClient()
    except ValueError:
      log.warning("DLSPS is not configured; instances of deleted cameras are not stopped yet")
      return
    with client:
      for entry in pending:
        _retry_pending_stop(client, entry, timeout_s)


def _retry_pending_stop(client: DLSPSClient, entry: PendingDLSPSStop, timeout_s: float) -> None:
  if _stop_pending_entry(client, entry, timeout_s):
    log.info(f"Resolved the pending DLSPS stop of a deleted camera ({entry})")
    entry.delete()
    return
  entry.attempts += 1
  if entry.attempts >= MAX_PENDING_STOP_ATTEMPTS:
    log.error(f"Giving up stopping the DLSPS pipeline of a deleted camera ({entry}) "
              f"after {entry.attempts} attempts; stop it manually")
    entry.delete()
    return
  entry.last_error = "stop not confirmed"
  entry.save(update_fields=['attempts', 'last_error'])


def _stop_pending_entry(client: DLSPSClient, entry: PendingDLSPSStop, timeout_s: float) -> bool:
  """Stop the entry's instance; True when nothing of it is left running.

  An entry known only by its launch attempt is first resolved to the instance carrying that
  launch marker. The resolved id is stored before stopping, so later retries check exactly that
  instance; an entry whose instance another entry already covers is redundant.
  """
  if entry.instance_id is None:
    try:
      instance_id = _find_launched_instance(client, entry.launch_id)
    except DLSPSError as e:
      log.warning(f"Failed to look up the DLSPS instance of launch {entry.launch_id}: {e}")
      return False
    if instance_id is None:
      return True
    if PendingDLSPSStop.objects.filter(instance_id=instance_id).exclude(pk=entry.pk).exists():
      return True
    entry.instance_id = instance_id
    entry.save(update_fields=['instance_id'])
  return _stop_and_confirm(client, entry.instance_id, timeout_s=timeout_s)


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
    running = Cam.objects.filter(Q(dlsps_instance_id__isnull=False) | Q(dlsps_launch_id__isnull=False))
    for cam_pk in running.values_list('pk', flat=True):
      with transaction.atomic():
        cam = Cam.objects.select_for_update().get(pk=cam_pk)
        if cam.dlsps_start_uncertain and not _resolve_uncertain_start(client, cam):
          continue
        if cam.dlsps_instance_id is not None \
            and _stop_and_confirm(client, cam.dlsps_instance_id):
          _set_runtime(cam, None, None)
  retry_pending_stops(timeout_s=settings.DLSPS_STOP_TIMEOUT_S)


def describe_camera_instance(cam: Cam) -> Optional[dict]:
  """Live DLSPS state of the camera's recorded instance for display, or None if none.

  Uses a short timeout and never raises: an unreachable DLSPS is reported as state "UNKNOWN".
  """
  if not mlops_flow_enabled() or cam.pk is None:
    return None
  if cam.dlsps_start_uncertain:
    return {'state': 'START UNCONFIRMED',
            'message': "DLSPS did not confirm the last start; save the camera to check whether "
                       "it is running."}
  if cam.dlsps_instance_id is None:
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
