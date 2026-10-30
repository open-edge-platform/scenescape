# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Portable scene hierarchy metadata and import validation."""

import os
from uuid import UUID

from rest_framework.exceptions import ValidationError

from manager.models import ChildScene, Scene
from manager.serializers import ChildSceneSerializer, SceneSerializer


LINK_FIELDS = (
  "child_type", "retrack", "transform_type",
  *(f"transform{index}" for index in range(1, 17)),
)
REMOTE_FIELDS = ("remote_child_id", "child_name", "host_name")


class SceneArchiveSerializer(SceneSerializer):
  def get_children(self, obj):
    children = []
    for link in obj.children.select_related("child"):
      if link.child is not None:
        child = dict(SceneArchiveSerializer(link.child).data)
        child["link"] = {key: getattr(link, key) for key in LINK_FIELDS}
        children.append(child)
    return children

  def to_representation(self, instance):
    data = super().to_representation(instance)
    data["archive_version"] = 2
    data["remote_children"] = [
      {key: getattr(link, key) for key in (*LINK_FIELDS, *REMOTE_FIELDS)}
      for link in instance.children.filter(child_type="remote")
    ]
    return data


def walk_scenes(scene):
  """Yield embedded local scenes, never remote references."""
  if not isinstance(scene, dict) or not isinstance(scene.get("children", []), list):
    raise ValueError("Invalid scene hierarchy")
  yield scene
  for child in scene.get("children", []):
    yield from walk_scenes(child)


def scene_map_path(scene, directory):
  """Resolve new explicit map filenames or legacy name-based archive maps."""
  if scene.get("map_file"):
    filename = scene["map_file"]
    if not isinstance(filename, str) or os.path.basename(filename) != filename:
      raise ValueError("Invalid map_file in archive")
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
      raise ValueError(f"Missing map file for scene '{scene.get('name')}'")
    return path
  name = scene.get("name", "")
  matches = [
    entry.path for entry in os.scandir(directory)
    if entry.is_file() and not entry.name.lower().endswith(".json")
    and os.path.splitext(entry.name)[0] in (name, name.replace(" ", "_"))
  ]
  if len(matches) != 1:
    raise ValueError(f"Expected one map file for scene '{name}'")
  return matches[0]


def remote_link_data(link, credentials):
  """Merge an allowlisted remote reference with separately supplied credentials."""
  if not isinstance(link, dict):
    raise ValueError("Invalid remote child reference")
  remote_id = str(UUID(str(link.get("remote_child_id", ""))))
  auth = credentials.get(remote_id)
  if not isinstance(auth, dict) or not all(auth.get(key) for key in ("mqtt_username", "mqtt_password")):
    raise ValueError(f"Missing MQTT credentials for remote child {remote_id}")
  data = {key: link[key] for key in (*LINK_FIELDS, *REMOTE_FIELDS) if key in link}
  data.update({key: auth[key] for key in ("mqtt_username", "mqtt_password")})
  data["child_type"] = "remote"
  return data


def validate_archive(scene, directory, restore_ids, credentials, reuse_existing=False):
  """Validate the entire hierarchy before creating any scenes."""
  seen_ids, seen_names, remote_ids = set(), set(), set()
  existing_scenes = {}
  for node in walk_scenes(scene):
    existing = validate_scene_node(node, directory, restore_ids, seen_ids, seen_names, reuse_existing)
    if existing is not None:
      existing_scenes[node["name"]] = str(existing.pk)
    validate_remote_links(node, credentials, remote_ids, existing, reuse_existing)
  if seen_ids & remote_ids:
    raise ValueError("A remote child UUID cannot also belong to a local scene in this archive")
  if reuse_existing:
    validate_reused_local_links(scene, existing_scenes)
  return existing_scenes


def validate_remote_links(node, credentials, remote_ids, parent=None, reuse_existing=False):
  links = node.get("remote_children", [])
  if not isinstance(links, list):
    raise ValueError("remote_children must be a list")
  for link in links:
    data = remote_link_data(link, credentials)
    uid = UUID(str(data["remote_child_id"]))
    if uid in remote_ids:
      raise ValueError(f"Remote child UUID already linked: {uid}")
    remote_ids.add(uid)
    existing = reusable_remote_link(uid, data, parent, reuse_existing)
    serializer = ChildSceneSerializer(instance=existing, data=data)
    serializer.fields.pop("parent")
    if not serializer.is_valid():
      # Do not echo submitted credentials in errors.
      raise ValueError(f"Invalid remote child configuration: {list(serializer.errors)}")


def reusable_remote_link(uid, data, parent, reuse_existing):
  if not reuse_existing:
    if ChildScene.objects.filter(remote_child_id=uid).exists():
      raise ValueError(f"Remote child UUID already linked: {uid}")
    return None
  existing = ChildScene.objects.filter(remote_child_id=uid).first()
  if existing is not None:
    validate_existing_link(existing, data, parent.pk if parent is not None else None)
  return existing


def validate_local_link(link):
  if not isinstance(link, dict) or link.get("child_type", "local") != "local":
    raise ValueError("Invalid local child link")
  fields = ChildSceneSerializer().fields
  for key in LINK_FIELDS:
    if key in link:
      try:
        fields[key].run_validation(link[key])
      except ValidationError as error:
        raise ValueError(f"Invalid local child link field: {key}") from error


def matching_scene(node, restore_ids):
  """Resolve explicit name-based reuse without accepting conflicting UUIDs."""
  existing = Scene.objects.filter(name=node["name"]).first()
  uid = UUID(str(node["uid"])) if node.get("uid") else None
  by_uid = Scene.objects.filter(pk=uid).first() if uid else None
  if by_uid is not None and (existing is None or existing.pk != by_uid.pk):
    raise ValueError(f"Scene UUID belongs to a different scene: {uid}")
  if restore_ids and existing is not None and existing.pk != uid:
    raise ValueError(f"Scene UUID does not match existing scene '{node['name']}'")
  return existing


def validate_existing_link(existing, data, parent_id):
  """Accept an identical link, never silently reparent or overwrite it."""
  if parent_id is None or str(existing.parent_id) != str(parent_id):
    raise ValueError("Child scene is already linked to a different parent")
  fields = LINK_FIELDS
  if data["child_type"] == "remote":
    fields = (*fields, *REMOTE_FIELDS, "mqtt_username", "mqtt_password")
  expected = ChildScene(**{key: data[key] for key in fields if key in data})
  for key in fields:
    field = ChildScene._meta.get_field(key)
    if field.to_python(getattr(existing, key)) != field.to_python(getattr(expected, key)):
      raise ValueError(f"Existing child link has conflicting configuration: {key}")


def validate_reused_local_links(node, existing_scenes):
  parent_id = existing_scenes.get(node["name"])
  for child in node.get("children", []):
    child_id = existing_scenes.get(child["name"])
    if child_id is not None:
      validate_local_relationship(child, child_id, parent_id)
    validate_reused_local_links(child, existing_scenes)


def validate_local_relationship(child, child_id, parent_id):
  existing = ChildScene.objects.filter(child_id=child_id).first()
  if existing is not None:
    data = {key: value for key, value in child.get("link", {}).items() if key in LINK_FIELDS}
    data["child_type"] = "local"
    validate_existing_link(existing, data, parent_id)
  if parent_id is not None:
    try:
      SceneSerializer.check_circular_dependency(
        Scene.objects.get(pk=parent_id), Scene.objects.get(pk=child_id))
    except ValidationError as error:
      raise ValueError("Reusing this child would create a circular hierarchy") from error


def validate_scene_node(node, directory, restore_ids, seen_ids, seen_names, reuse_existing=False):
  name = node.get("name")
  if not isinstance(name, str) or not name or name in seen_names:
    raise ValueError("Scene names must be nonempty and unique within an archive")
  seen_names.add(name)
  if node.get("archive_version", 1) not in (1, 2):
    raise ValueError("Unsupported scene archive version")
  if set(node) == {"name"}:
    raise ValueError("Legacy remote child metadata is incomplete; re-export from the source deployment")
  scene_map_path(node, directory)
  validate_local_link(node.get("link", {}))
  existing = matching_scene(node, restore_ids) if reuse_existing else None
  if not reuse_existing and Scene.objects.filter(name=name).exists():
    raise ValueError(f"A scene named '{name}' already exists")
  if restore_ids:
    uid = UUID(str(node.get("uid", "")))
    if uid in seen_ids or (existing is None and Scene.objects.filter(pk=uid).exists()):
      raise ValueError(f"Scene UUID collision: {uid}")
    seen_ids.add(uid)
  return existing
