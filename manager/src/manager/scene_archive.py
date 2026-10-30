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


def validate_archive(scene, directory, restore_ids, credentials):
  """Validate the entire hierarchy before creating any scenes."""
  seen_ids, seen_names, remote_ids = set(), set(), set()
  for node in walk_scenes(scene):
    validate_scene_node(node, directory, restore_ids, seen_ids, seen_names)
    validate_remote_links(node, credentials, remote_ids)
  if seen_ids & remote_ids:
    raise ValueError("A remote child UUID cannot also belong to a local scene in this archive")


def validate_remote_links(node, credentials, remote_ids):
  links = node.get("remote_children", [])
  if not isinstance(links, list):
    raise ValueError("remote_children must be a list")
  for link in links:
    data = remote_link_data(link, credentials)
    uid = UUID(str(data["remote_child_id"]))
    if uid in remote_ids or ChildScene.objects.filter(remote_child_id=uid).exists():
      raise ValueError(f"Remote child UUID already linked: {uid}")
    remote_ids.add(uid)
    serializer = ChildSceneSerializer(data=data)
    serializer.fields.pop("parent")
    if not serializer.is_valid():
      # Do not echo submitted credentials in errors.
      raise ValueError(f"Invalid remote child configuration: {list(serializer.errors)}")


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


def validate_scene_node(node, directory, restore_ids, seen_ids, seen_names):
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
  if Scene.objects.filter(name=name).exists():
    raise ValueError(f"A scene named '{name}' already exists")
  if restore_ids:
    uid = UUID(str(node.get("uid", "")))
    if uid in seen_ids or Scene.objects.filter(pk=uid).exists():
      raise ValueError(f"Scene UUID collision: {uid}")
    seen_ids.add(uid)
