# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene hierarchy rules: one root parent with leaf children, attached in batches or derived as placed shells."""

from dataclasses import dataclass
import math
from typing import Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from manager import placement
from manager.models import ChildScene, Scene
from manager.validators import validate_map_corners_lla, validate_scene_name

MAX_BATCH_CHILDREN = 200
RECT_TOLERANCE_M = 1e-6
RETRY_MESSAGE = "The hierarchy changed while the request was running; retry it"
CREATED = "created"
RECOMPUTED = "recomputed"
UNCHANGED = "unchanged"


class HierarchyError(ValueError):
  """A rule violation the caller can fix; the message is safe to show."""
  status = 400


class HierarchyConflict(HierarchyError):
  status = 409


@dataclass(frozen=True)
class _Plan:
  child: Scene
  action: str
  link: Optional[ChildScene]
  result: Optional[placement.Placement]


def descendant_uids(scene_uid):
  """UIDs of every scene below scene_uid, loading one level of links per query."""
  seen = set()
  frontier = {scene_uid}
  while frontier:
    rows = ChildScene.objects.filter(parent_id__in=frontier, child_id__isnull=False)
    frontier = set(rows.values_list("child_id", flat=True)) - seen
    seen |= frontier
  return seen


def ensure_no_cycle(parent_scene, child_scene):
  if parent_scene.pk in descendant_uids(child_scene.pk):
    raise HierarchyError(f'Cannot link "{parent_scene}" with "{child_scene}" due to circular dependency')


def ensure_root(scene):
  if ChildScene.objects.filter(child=scene).exists():
    raise HierarchyError(f'"{scene}" is already a child; only one level of children is supported')


def ensure_two_level(parent, child):
  ensure_root(parent)
  if ChildScene.objects.filter(parent=child).exists():
    raise HierarchyError(f'"{child}" already has children; only one level of children is supported')


def _frame_or_error(scene):
  try:
    return placement.frame_corners(scene)
  except placement.PlacementError as error:
    raise HierarchyError(str(error)) from error


def placement_status(parent):
  links = ChildScene.objects.filter(parent=parent, child__isnull=False).select_related("parent", "child")
  return [
    {
      "child": str(link.child_id),
      "source": (link.placement or {}).get("source"),
      "stale": placement.is_stale(link),
      "residual_m": (link.placement or {}).get("residual_m"),
    }
    for link in links
  ]


def _plan_child(parent, uid, seen):
  if uid in seen:
    raise HierarchyError("Listed more than once in this request")
  seen.add(uid)
  if uid == parent.pk:
    raise HierarchyError("A scene cannot be its own child")
  child = Scene.objects.filter(pk=uid).first()
  if child is None:
    raise HierarchyError("Scene not found")
  link = ChildScene.objects.filter(child=child).first()
  if link is not None and link.parent_id != parent.pk:
    raise HierarchyError(f'Already linked to parent "{link.parent}"')
  if link is not None and not link.placement:
    raise HierarchyError("Already linked with a manual transform; edit it through the link form")
  if link is not None and not placement.is_stale(link):
    return _Plan(child, UNCHANGED, link, None)
  ensure_two_level(parent, child)
  try:
    result = placement.compute_placement(parent, child, placement.SOURCE_GEOREFERENCE)
  except placement.PlacementError as error:
    raise HierarchyError(str(error)) from error
  return _Plan(child, RECOMPUTED if link is not None else CREATED, link, result)


def _plan_attach(parent, child_uids):
  plans, errors, seen = [], [], set()
  for uid in child_uids:
    try:
      plans.append(_plan_child(parent, uid, seen))
    except HierarchyError as error:
      errors.append({"child": str(uid), "error": str(error)})
  return plans, errors


def _lock_scene(scene):
  """Serialise hierarchy writes on one scene; call inside transaction.atomic()."""
  list(Scene.objects.select_for_update().filter(pk=scene.pk).values_list("pk", flat=True))


def _apply_attach(parent, plans):
  for plan in plans:
    if plan.action == UNCHANGED:
      continue
    link = plan.link if plan.link is not None else ChildScene(parent=parent, child=plan.child)
    placement.apply_placement(link, plan.result)
    link.save()
  return [_result_entry(plan) for plan in plans]


def _result_entry(plan):
  entry = {"child": str(plan.child.pk), "status": plan.action}
  if plan.result is not None:
    entry["heading_deg"] = plan.result.heading_deg
    entry["residual_m"] = plan.result.provenance["residual_m"]
  return entry


def attach_children(parent, child_uids):
  """Attach georeference-placed children to a root parent. Returns (results, errors).

  Planning and writing share one locked transaction, and nothing is written when any item is rejected.
  """
  ensure_root(parent)
  _frame_or_error(parent)
  try:
    with transaction.atomic():
      _lock_scene(parent)
      plans, errors = _plan_attach(parent, child_uids)
      if errors:
        return [], errors
      return _apply_attach(parent, plans), []
  except IntegrityError as error:
    raise HierarchyConflict(RETRY_MESSAGE) from error


def create_placed_child(parent, name, x, y, width, height):
  """Create a scene shell inside the parent's frame and link it with a placed transform."""
  ensure_root(parent)
  frame = _frame_or_error(parent)
  if not all(math.isfinite(value) for value in (x, y, width, height)):
    raise HierarchyError("Rectangle coordinates must be finite numbers")
  if width <= 0 or height <= 0:
    raise HierarchyError("Width and height must be positive")
  parent_width, parent_height = placement.frame_extent(frame)
  if x < 0 or y < 0 or x + width > parent_width + RECT_TOLERANCE_M or y + height > parent_height + RECT_TOLERANCE_M:
    raise HierarchyError("Rectangle must lie inside the parent frame")
  try:
    validate_scene_name(name)
  except DjangoValidationError as error:
    raise HierarchyError(" ".join(error.messages)) from error
  if Scene.objects.filter(name=name).exists():
    raise HierarchyError(f"A scene named '{name}' already exists")
  corners = placement.footprint_corners_lla(frame, x, y, width, height)
  try:
    validate_map_corners_lla(corners)
  except DjangoValidationError as error:
    raise HierarchyError(" ".join(error.messages)) from error

  try:
    with transaction.atomic():
      _lock_scene(parent)
      shell = Scene.objects.create(name=name, map_type="geospatial_map", map_corners_lla=corners)
      result = placement.compute_placement(parent, shell, placement.SOURCE_PLACED)
      link = ChildScene(parent=parent, child=shell)
      placement.apply_placement(link, result)
      link.save()
  except placement.PlacementError as error:
    raise HierarchyError(str(error)) from error
  except IntegrityError as error:
    raise HierarchyConflict(RETRY_MESSAGE) from error
  return shell, link, result
