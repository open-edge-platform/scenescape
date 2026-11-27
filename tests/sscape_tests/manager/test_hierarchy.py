# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Two-level hierarchy rules: cycles, level limits, all-or-nothing batch attach, and placed shells."""

import uuid

import numpy as np
import pytest

from manager import hierarchy, placement
from manager.models import ChildScene, Scene
from tests.utils.geo_footprint import localFootprintCornersLLA

PARENT_CORNERS = localFootprintCornersLLA(
  center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0, width_m=100.0, height_m=80.0,
).tolist()


def _scene(name, corners=None):
  return Scene.objects.create(name=name, map_type="geospatial_map", map_corners_lla=corners)


def _footprint_scene(name, x, y, width=10.0, height=10.0):
  corners = placement.footprint_corners_lla(np.array(PARENT_CORNERS), x, y, width, height)
  return _scene(name, corners)


@pytest.fixture
def parent(db):
  return _scene("city", PARENT_CORNERS)


@pytest.mark.django_db
def test_linking_an_ancestor_under_its_descendant_is_a_cycle():
  a, b, c = _scene("a"), _scene("b"), _scene("c")
  ChildScene.objects.create(parent=a, child=b)
  ChildScene.objects.create(parent=b, child=c)

  with pytest.raises(hierarchy.HierarchyError, match="circular dependency"):
    hierarchy.ensure_no_cycle(parent_scene=c, child_scene=a)
  hierarchy.ensure_no_cycle(parent_scene=a, child_scene=c)


@pytest.mark.django_db
def test_only_one_level_of_children_is_allowed(parent):
  child = _footprint_scene("c1", 0.0, 0.0)
  ChildScene.objects.create(parent=parent, child=child)
  grandchild = _footprint_scene("g1", 30.0, 30.0)
  ChildScene.objects.create(parent=child, child=grandchild)

  with pytest.raises(hierarchy.HierarchyError, match="already a child"):
    hierarchy.ensure_two_level(parent=child, child=_footprint_scene("x", 50.0, 50.0))
  with pytest.raises(hierarchy.HierarchyError, match="already has children"):
    hierarchy.ensure_two_level(parent=parent, child=child)


@pytest.mark.django_db
def test_attach_creates_links_then_reports_unchanged(parent):
  children = [_footprint_scene("c1", 0.0, 0.0), _footprint_scene("c2", 20.0, 0.0)]
  uids = [child.pk for child in children]

  results, errors = hierarchy.attach_children(parent, uids)

  assert errors == []
  assert [entry["status"] for entry in results] == ["created", "created"]
  assert ChildScene.objects.filter(parent=parent).count() == 2
  assert all(ChildScene.objects.get(child=child).placement for child in children)

  results, errors = hierarchy.attach_children(parent, uids)

  assert errors == []
  assert [entry["status"] for entry in results] == ["unchanged", "unchanged"]


@pytest.mark.django_db
def test_batch_with_one_rejected_item_writes_nothing(parent):
  good = _footprint_scene("good", 0.0, 0.0)

  results, errors = hierarchy.attach_children(parent, [good.pk, uuid.uuid4()])

  assert results == []
  assert errors[0]["error"] == "Scene not found"
  assert not ChildScene.objects.exists()


@pytest.mark.django_db
def test_manual_link_is_never_overwritten(parent):
  manual = _footprint_scene("manual", 0.0, 0.0)
  ChildScene.objects.create(parent=parent, child=manual)

  results, errors = hierarchy.attach_children(parent, [manual.pk])

  assert results == []
  assert "manual transform" in errors[0]["error"]
  assert ChildScene.objects.get(child=manual).placement is None


@pytest.mark.django_db
def test_child_of_another_parent_is_rejected(parent):
  owned = _footprint_scene("owned", 0.0, 0.0)
  ChildScene.objects.create(parent=_scene("other", PARENT_CORNERS), child=owned)

  results, errors = hierarchy.attach_children(parent, [owned.pk])

  assert results == []
  assert "Already linked to parent" in errors[0]["error"]


@pytest.mark.django_db
def test_child_cannot_take_children(parent):
  child = _footprint_scene("c1", 0.0, 0.0)
  ChildScene.objects.create(parent=parent, child=child)

  with pytest.raises(hierarchy.HierarchyError, match="already a child"):
    hierarchy.attach_children(child, [_footprint_scene("leaf", 30.0, 30.0).pk])


@pytest.mark.django_db
def test_parent_without_frame_cannot_attach(db):
  with pytest.raises(hierarchy.HierarchyError, match="no geospatial frame"):
    hierarchy.attach_children(_scene("bare"), [_footprint_scene("c1", 0.0, 0.0).pk])


@pytest.mark.django_db
def test_stale_placement_is_recomputed_after_parent_frame_moves(parent):
  child = _footprint_scene("c1", 10.0, 10.0)
  hierarchy.attach_children(parent, [child.pk])
  parent.map_corners_lla = (np.array(PARENT_CORNERS) + [0.0, 1e-6, 0.0]).tolist()
  parent.save()
  parent = Scene.objects.get(pk=parent.pk)

  assert hierarchy.placement_status(parent)[0]["stale"] is True

  results, errors = hierarchy.attach_children(parent, [child.pk])

  assert errors == []
  assert results[0]["status"] == "recomputed"
  assert hierarchy.placement_status(parent)[0]["stale"] is False


@pytest.mark.django_db
def test_placed_child_is_a_shell_inside_the_parent_frame(parent):
  shell, link, result = hierarchy.create_placed_child(parent, "Block A", 10.0, 20.0, 30.0, 40.0)

  assert shell.map_type == "geospatial_map"
  assert not shell.map
  assert link.parent == parent
  assert link.child == shell
  assert link.placement["source"] == "placed"
  assert link.transform_type == "euler"
  assert link.transform1 == pytest.approx(result.translation[0])
  assert result.translation == pytest.approx((10.0, 20.0), abs=0.05)


@pytest.mark.django_db
@pytest.mark.parametrize("rectangle, message", [
  ((0.0, 0.0, 0.0, 10.0), "positive"),
  ((90.0, 0.0, 30.0, 10.0), "inside the parent frame"),
  ((-1.0, 0.0, 10.0, 10.0), "inside the parent frame"),
  ((float("nan"), 0.0, 10.0, 10.0), "finite"),
])
def test_placed_child_rejects_rectangles_outside_the_frame(parent, rectangle, message):
  with pytest.raises(hierarchy.HierarchyError, match=message):
    hierarchy.create_placed_child(parent, "Block", *rectangle)


@pytest.mark.django_db
def test_placed_child_name_must_be_unique(parent):
  hierarchy.create_placed_child(parent, "Block", 0.0, 0.0, 10.0, 10.0)

  with pytest.raises(hierarchy.HierarchyError, match="already exists"):
    hierarchy.create_placed_child(parent, "Block", 20.0, 20.0, 10.0, 10.0)


@pytest.mark.django_db
def test_placed_child_cannot_take_children(parent):
  shell, _, _ = hierarchy.create_placed_child(parent, "Block", 0.0, 0.0, 10.0, 10.0)

  with pytest.raises(hierarchy.HierarchyError, match="already a child"):
    hierarchy.create_placed_child(shell, "Sub", 0.0, 0.0, 5.0, 5.0)
