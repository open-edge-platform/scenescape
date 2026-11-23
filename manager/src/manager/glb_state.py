# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Store, apply, move and remove the GLB of a geospatial scene, and place it on the map."""

import hashlib
import json
import math
import os
import uuid
from contextlib import contextmanager
from functools import partial

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
import numpy as np
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.earth_lla import (
  footprintAnchorFromCornersLLA, llaToFrameLocalXY,
  convertECEFToLLA, calculateTRSLocal2LLAFromSurfacePoints
)
from scene_common.mesh_util import extractMeshFromGLB, getPosedMeshFootprint

from . import glb_staging
from .glb_bake import bake_layers
from .glb_staging import (
  GlbAlignmentError, adopt_staged_preview, ensure_glb_preview,
  purge_stale_files, remove_staged_files, staged_glb_path
)
from .models import (
  GlbLayer, Scene, delete_unreferenced_mapping_file, glb_preview_name, remove_stored_file
)

# Scene-edit form fields written by apply, unapply and move.
SCENE_FORM_GLB_FIELDS = (
  'scale', 'rotation_x', 'rotation_y', 'rotation_z',
  'translation_x', 'translation_y', 'translation_z', 'map_corners_lla',
)
# Stored scene files that the layer writes change; a failed write discards the new ones.
GLB_STORED_FILES = ('map', 'base_map', 'thumbnail')
# State a GLB write changes; the scene-edit form carries its token to detect an out-of-date page.
STATE_TOKEN_FIELDS = SCENE_FORM_GLB_FIELDS + ('use_glb_map',)
# Keep equal to FAR_ANCHOR_KM in static/js/geospatial/glb-alignment.js.
MAX_ANCHOR_DISTANCE_KM = 50.0
EARTH_RADIUS_KM = 6371.0


def lock_scene_row(scene):
  """Lock the scene row until the enclosing transaction ends; call inside transaction.atomic().

  Only locks: in-memory field values are kept, so unsaved form values survive.
  Uses values_list: Scene.__init__ reads the map field, so a deferred model load would recurse.
  """
  Scene.objects.select_for_update().filter(pk=scene.pk).values_list('pk', flat=True).get()


def get_geospatial_scene(scene_uid, lock=False):
  """Get a scene by UUID, validating it is a geospatial_map.

  With lock=True the row is locked until the enclosing transaction ends; call inside transaction.atomic().
  Raises GlbAlignmentError(404, 'Scene not found') if scene does not exist.
  Raises GlbAlignmentError(400, 'Scene map type must be geospatial_map') if map type is wrong.
  """
  queryset = Scene.objects.select_for_update() if lock else Scene.objects
  try:
    scene = queryset.get(pk=scene_uid)
  except (Scene.DoesNotExist, ValueError):
    raise GlbAlignmentError(404, 'Scene not found')
  if scene.map_type != 'geospatial_map':
    raise GlbAlignmentError(400, 'Scene map type must be geospatial_map')
  return scene


def parse_anchor(anchor):
  """Validate an anchor dict; returns (lat, lng, heading_deg normalised to [0, 360))."""
  try:
    lat, lng, heading = (anchor[key] for key in ('lat', 'lng', 'heading_deg'))
  except (TypeError, KeyError):
    raise GlbAlignmentError(400, 'Invalid anchor')
  numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (lat, lng, heading))
  if not numeric or abs(lat) > 90.0 or abs(lng) > 180.0:
    raise GlbAlignmentError(400, 'Invalid anchor')
  return lat, lng, heading % 360.0


def _distance_km(lat1, lng1, lat2, lng2):
  """Great-circle distance in km between two lat/lng points in degrees."""
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  a = (math.sin((phi2 - phi1) / 2) ** 2 +
       math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
  return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def check_anchor_near_map_center(scene, lat, lng):
  """Raise 400 when the anchor is more than MAX_ANCHOR_DISTANCE_KM from the scene map center."""
  if scene.map_center_lat is None or scene.map_center_lng is None:
    return
  if _distance_km(lat, lng, scene.map_center_lat, scene.map_center_lng) > MAX_ANCHOR_DISTANCE_KM:
    raise GlbAlignmentError(400, f'Anchor must be within {MAX_ANCHOR_DISTANCE_KM:g} km of the map center')


def _aligned_footprint(mesh):
  """Footprint corners [SW, SE, NE, NW] at z=0 of a raw mesh after the Rx(ALIGN_ROTATION_X) axis conversion."""
  return getPosedMeshFootprint(mesh, [glb_staging.ALIGN_ROTATION_X, 0.0, 0.0], [0.0, 0.0, 0.0])


def _get_aligned_footprint_size_m(glb_path):
  """Load a raw GLB mesh and return the (width_m, height_m) of its axis-converted footprint."""
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  sw, se, _, nw = _aligned_footprint(mesh)
  return se[0] - sw[0], nw[1] - sw[1]


def compute_glb_pose_and_corners(frame_corners_lla, anchor_lat, anchor_lng, anchor_heading,
                                  glb_path=None):
  """Compute GLB mesh pose and map_corners_lla to place it at the anchor in the frame.

  Frame local origin is at the SW corner (0, 0), with local corners:
    SW=(0,0), SE=(W,0), NE=(W,H), NW=(0,H)
  These are converted to LLA via frame_corners_lla.

  The GLB footprint (measured from real mesh vertices) is positioned such that:
  - Its centre (after alignment rotation and yaw) lands at anchor in frame-local
  - Its aligned bounding rectangle's z=0 is maintained (floor at z=0)
  - The frame's local->LLA transform is preserved

  glb_path must be provided to load the actual mesh and extract vertex data.

  Returns (rotation, translation, map_corners_lla):
    rotation: [rotation_x, rotation_y, rotation_z] in degrees (Euler XYZ intrinsic)
    translation: [tx, ty, tz] in metres (frame-local)
    map_corners_lla: [SW, SE, NE, NW] in LLA for the posed GLB footprint
  """
  if not glb_path:
    raise GlbAlignmentError(400, 'glb_path is required for pose computation')

  # Frame heading (the frame origin is at its SW corner)
  _, _, frame_heading, _, _ = footprintAnchorFromCornersLLA(frame_corners_lla)

  # Convert anchor (global LLA) to frame-local metres
  anchor_local = llaToFrameLocalXY(frame_corners_lla, anchor_lat, anchor_lng)

  # Load raw mesh and apply axis conversion
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  vertices_raw = mesh.vertex.positions.numpy()  # (N, 3)

  # Apply axis conversion: A = Rx(ALIGN_ROTATION_X)
  R_x = Rotation.from_euler('x', [glb_staging.ALIGN_ROTATION_X], degrees=True)
  min_z_a = np.min(vertices_raw @ R_x.as_matrix()[2])

  # Rectangle centre in aligned frame (SW and NE are opposite corners, z=0)
  aligned = _aligned_footprint(mesh)
  p0 = (aligned[0] + aligned[2]) / 2.0

  # Relative yaw: rotate from frame heading to anchor heading
  # Both frame and anchor are defined with +Y pointing at their heading (azimuth)
  # A clockwise rotation (in geographic terms) by theta is a counter-clockwise
  # rotation (in scipy/standard math) by -theta
  # So theta_scipy = -(anchor_heading - frame_heading) = frame_heading - anchor_heading
  theta_deg = (frame_heading - anchor_heading) % 360.0

  # R_total = Rz(theta) @ Rx(ALIGN_ROTATION_X)
  R_rz = Rotation.from_euler('z', [theta_deg], degrees=True)
  R_total = R_rz * R_x  # scipy: multiply in order of application (A first, then Rz)
  euler_xyz = R_total.as_euler('XYZ', degrees=True)
  rotation = euler_xyz.tolist()

  # Compute translation: t = c - Rz(theta) @ p0 for xy; t_z = -zmin
  # Where c = anchor_local (the frame-local position where the rectangle centre should be)
  p0_rotated_xy = R_rz.apply(p0)[:2]  # Apply only Rz to p0
  translation = [
    anchor_local[0] - p0_rotated_xy[0],
    anchor_local[1] - p0_rotated_xy[1],
    -min_z_a
  ]

  # Compute map_corners_lla using controller's path:
  # getPosedMeshFootprint(RAW mesh, rotation, translation) -> calculateTRSLocal2LLAFromSurfacePoints
  mesh_footprint = getPosedMeshFootprint(mesh, rotation, translation)
  return rotation, translation, footprint_to_lla(frame_corners_lla, mesh_footprint)


def footprint_to_lla(frame_corners_lla, footprint):
  """Convert a frame-local footprint (4x3, corners SW, SE, NE, NW at z=0) to LLA corners."""
  _, _, _, frame_width, frame_height = footprintAnchorFromCornersLLA(frame_corners_lla)
  frame_corners_local = np.array([
    [0.0, 0.0, 0.0],
    [frame_width, 0.0, 0.0],
    [frame_width, frame_height, 0.0],
    [0.0, frame_height, 0.0]
  ])
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(frame_corners_local, frame_corners_lla)
  posed_ecef = (frame_trs[:3, :3] @ footprint.T).T + frame_trs[:3, 3]
  return np.array([convertECEFToLLA(corner) for corner in posed_ecef]).tolist()


def _delete_replaced_file_after_commit(scene, name):
  """Schedule deletion of a stored file that a scene field no longer points to.

  Runs on commit only: a rollback restores the row, which still needs the file.
  """
  if name:
    transaction.on_commit(partial(
      delete_unreferenced_mapping_file, scene.map.storage, name, scene._state.db or 'default'))


def stored_file_names(scene, fields):
  """Names of the stored files in fields, to restore them if a write rolls back."""
  return {field: getattr(scene, field).name or '' for field in fields}


@contextmanager
def discard_files_on_failure(scene):
  """Delete the files a failed write stored and restore the stored scene names.

  Take it after the row is locked and the scene is current: the names seen on entry are
  the ones that stay valid. Yields the list of layer file names the write stores; a failed
  write deletes them with their previews, since the rolled-back rows never reference them.
  """
  before = stored_file_names(scene, GLB_STORED_FILES)
  created = []
  try:
    yield created
  except Exception:
    layer_storage = GlbLayer._meta.get_field('file').storage
    for name in created:
      remove_stored_file(layer_storage, name)
      remove_stored_file(layer_storage, glb_preview_name(name))
    for field, name_before in before.items():
      stored_file = getattr(scene, field)
      if stored_file.name and stored_file.name != name_before:
        remove_stored_file(stored_file.storage, stored_file.name)
      setattr(scene, field, name_before)
    raise


@contextmanager
def locked_scene_write(scene):
  """Atomic scene write: the row is locked and the files a failed write stored are discarded.

  The write sets the map pose itself, so the upload auto-align must not run on its save.
  """
  scene._explicit_mesh_transform = True
  with transaction.atomic():
    lock_scene_row(scene)
    with discard_files_on_failure(scene) as created:
      yield created


@contextmanager
def _failing_as(message):
  """Turn an unexpected error in a GLB write into a 500 with a client-safe message."""
  try:
    yield
  except GlbAlignmentError:
    raise
  except Exception as e:
    log.error(f'{message}: {e}')
    raise GlbAlignmentError(500, message)


def _remove_replaced_glb(storage, glb_name):
  """Delete a replaced GLB and its cached preview; runs on commit."""
  remove_stored_file(storage, glb_name)
  remove_stored_file(storage, glb_preview_name(glb_name))


def scene_state_token(scene):
  """Digest of the scene map, pose, corners and GLB layer state that a GLB write changes."""
  state = [getattr(scene, name) for name in STATE_TOKEN_FIELDS]
  state += [scene.map.name]
  state += [[str(layer.id), layer.order, layer.enabled, layer.anchor, layer.file.name]
            for layer in scene.glb_layers.all()]
  return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def reject_stale_form(stored, posted_token):
  """Raise 409 when the form was rendered before the locked scene row changed.

  A form loaded before a GLB apply, unapply or move would otherwise write the old pose back.
  A form without a token is not checked.
  @param stored        scene row locked by the caller
  @param posted_token  scene_state_token() the form carried
  """
  if posted_token and posted_token != scene_state_token(stored):
    raise GlbAlignmentError(409, 'Scene map or pose changed since the form was loaded; the form now shows the current values')


def require_base_map(scene):
  """Raise 400 unless the scene has a flat (non-GLB) base map to place the GLB over.

  The base is base_map while a GLB is applied, otherwise the scene map itself.
  A GLB-only map has no flat image for the hybrid view, so it is rejected.
  """
  base = scene.base_map if scene.use_glb_map else scene.map
  if not base or os.path.splitext(base.name)[1].lower() == '.glb':
    raise GlbAlignmentError(400, 'Scene needs a flat base map (image) before a GLB can be placed')


def _frame_corners(scene):
  """Frame corners the GLB pose is measured from: the base map while a GLB is placed."""
  frame_corners = scene.base_map_corners_lla or scene.map_corners_lla
  if not frame_corners:
    raise GlbAlignmentError(400, 'Cannot compute pose: missing frame')
  return frame_corners


def _set_pose(scene, rotation, translation, map_corners):
  """Set the scene map pose and its corners from compute_glb_pose_and_corners output."""
  scene.rotation_x, scene.rotation_y, scene.rotation_z = rotation
  scene.translation_x, scene.translation_y, scene.translation_z = translation
  scene.map_corners_lla = map_corners


def _snapshot_base_map(scene):
  """Keep the flat map as base_map before a GLB is placed over it; unapply restores it."""
  base_ext = os.path.splitext(scene.map.name)[1].lower()
  previous_base = scene.base_map.name
  with scene.map.storage.open(scene.map.name, 'rb') as f:
    scene.base_map.save(f'base_{scene.name}{base_ext}', File(f), save=False)
  _delete_replaced_file_after_commit(scene, previous_base)
  scene.base_scale = scene.scale
  if not scene.base_map_corners_lla:
    scene.base_map_corners_lla = scene.map_corners_lla


def _restore_base_map(scene):
  """Put base_map back as the scene map, reset the pose and drop the base. Caller saves."""
  previous_map = scene.map.name
  if scene.base_map and scene.base_map.storage.exists(scene.base_map.name):
    base_ext = os.path.splitext(scene.base_map.name)[1]
    with scene.base_map.storage.open(scene.base_map.name, 'rb') as f:
      scene.map.save(f'{scene.name}{base_ext}', File(f), save=False)
  else:
    scene.map = ''  # None crashes Scene.save() on the map-name check
  _delete_replaced_file_after_commit(scene, previous_map)

  scene.scale = scene.base_scale
  scene.map_corners_lla = scene.base_map_corners_lla
  scene.resetRotation()
  scene.resetTranslation()
  _delete_replaced_file_after_commit(scene, scene.thumbnail.name)
  scene.thumbnail = None
  scene.use_glb_map = False

  # The base file is removed on commit only: a rollback restores base_map, which still needs it
  _delete_replaced_file_after_commit(scene, scene.base_map.name)
  scene.base_map = None
  scene.base_scale = None


def _place_single_layer(scene, layer):
  """Place one layer as the scene map: copy its GLB and set the pose from its anchor."""
  previous_map = scene.map.name
  with layer.file.storage.open(layer.file.name, 'rb') as f:
    scene.map.save(f'{scene.name}.glb', File(f), save=False)
  _delete_replaced_file_after_commit(scene, previous_map)

  anchor = layer.anchor
  rotation, translation, map_corners = compute_glb_pose_and_corners(
    _frame_corners(scene), anchor['lat'], anchor['lng'], anchor['heading_deg'],
    glb_path=layer.file.path
  )
  _set_pose(scene, rotation, translation, map_corners)


def _place_baked_layers(scene, layers):
  """Place several layers as one baked GLB, so the scene map keeps an identity pose."""
  frame_corners = _frame_corners(scene)
  parts = []
  footprints = []
  for layer in layers:
    anchor = layer.anchor
    rotation, translation, _ = compute_glb_pose_and_corners(
      frame_corners, anchor['lat'], anchor['lng'], anchor['heading_deg'],
      glb_path=layer.file.path
    )
    parts.append((layer.file.path, rotation, translation))
    raw_mesh, _ = extractMeshFromGLB(layer.file.path, rotation=None)
    footprints.append(getPosedMeshFootprint(raw_mesh, rotation, translation))

  # Union of the posed footprints: the baked mesh is posed at identity, so its corners are this box
  union = np.vstack(footprints)
  low = union[:, :2].min(axis=0)
  high = union[:, :2].max(axis=0)
  baked_corners = np.array([
    [low[0], low[1], 0.0],
    [high[0], low[1], 0.0],
    [high[0], high[1], 0.0],
    [low[0], high[1], 0.0],
  ])

  previous_map = scene.map.name
  scene.map.save(f'{scene.name}.glb', ContentFile(bake_layers(parts)), save=False)
  _delete_replaced_file_after_commit(scene, previous_map)
  scene.resetRotation()
  scene.resetTranslation()
  scene.map_corners_lla = footprint_to_lla(frame_corners, baked_corners)


def build_scene_map(scene):
  """Place the enabled layers as the scene map: one layer directly, several baked into one GLB.

  The only writer of the scene map pose. Callers hold the scene row lock and save the scene.
  """
  layers = list(scene.glb_layers.filter(enabled=True))
  if not layers:
    if scene.use_glb_map:
      _restore_base_map(scene)
    return
  if not scene.use_glb_map:
    _snapshot_base_map(scene)
  if len(layers) == 1:
    _place_single_layer(scene, layers[0])
  else:
    _place_baked_layers(scene, layers)
  scene.use_glb_map = True
  scene.saveThumbnail()


def disable_all_layers(scene):
  """Disable every layer and restore the base map; the rows and files are kept. Caller saves."""
  scene.glb_layers.update(enabled=False)
  if scene.use_glb_map:
    _restore_base_map(scene)


def _has_flat_base(scene):
  """True when a GLB can be placed over the scene's flat base map."""
  try:
    require_base_map(scene)
  except GlbAlignmentError:
    return False
  return True


def _next_order(scene):
  """Next draw order for a new layer; the (scene, order) constraint keeps it unique."""
  highest = scene.glb_layers.aggregate(highest=Max('order'))['highest']
  return 0 if highest is None else highest + 1


def _new_layer_for_commit(scene, enable):
  """An unsaved layer for a new upload; 409 when the scene already holds GLB_MAX_LAYERS layers."""
  if scene.glb_layers.count() >= settings.GLB_MAX_LAYERS:
    raise GlbAlignmentError(409, f'A scene holds at most {settings.GLB_MAX_LAYERS} GLB layers')
  layer = GlbLayer(scene=scene, order=_next_order(scene))
  layer.enabled = enable and _has_flat_base(scene)
  return layer


def commit_layer(scene, token, anchor, layer=None, enable=False, save=True, stored_names=None):
  """Store a staged GLB as a layer: a new one (layer None) or a new file for an existing layer.

  A new layer is placed when enable is set and the scene has a flat base map; otherwise it is
  stored disabled. An existing layer keeps its enabled state. Caller holds nothing; this locks.
  stored_names, when given, is the enclosing write's list of stored files: the new layer file is
  added so that a later failure in that write discards it. Returns the layer; the caller builds the
  response with write_response after its transaction, so the preview render stays out of the write.
  """
  if scene.use_glb_map:
    # Re-placing the GLB needs the flat base map; storing alone does not
    require_base_map(scene)
  path = staged_glb_path(token)
  token = str(uuid.UUID(token))
  lat, lng, heading = parse_anchor(anchor)
  check_anchor_near_map_center(scene, lat, lng)

  with _failing_as('Failed to store GLB'), locked_scene_write(scene) as created:
    if layer is None:
      layer = _new_layer_for_commit(scene, enable)
    else:
      layer.refresh_from_db()
    old_file = layer.file.name or ''

    with open(path, 'rb') as f:
      layer.file.save(f'{scene.name}.glb', File(f), save=False)
    created.append(layer.file.name)
    if stored_names is not None:
      stored_names.append(layer.file.name)
    adopt_staged_preview(layer, token)

    width, height = _get_aligned_footprint_size_m(layer.file.path)
    layer.anchor = {
      'lat': float(lat),
      'lng': float(lng),
      'heading_deg': float(heading),
      'footprint_m': {'width': float(width), 'height': float(height)},
    }
    if not scene.base_map_corners_lla:
      scene.base_map_corners_lla = scene.map_corners_lla

    layer.save()
    if layer.enabled:
      build_scene_map(scene)
    if save:
      scene.save()

    # Replaced files are removed on commit only: a rollback keeps the old file referenced
    if old_file and old_file != layer.file.name:
      transaction.on_commit(partial(_remove_replaced_glb, layer.file.storage, old_file))
    transaction.on_commit(partial(remove_staged_files, token))

  purge_stale_files()
  return layer


def get_layer(scene, layer_id):
  """The stored layer of this scene with layer_id; 404 when it is not a UUID or belongs to another scene."""
  try:
    layer = scene.glb_layers.filter(pk=layer_id).first()
  except ValidationError:
    layer = None
  if layer is None:
    raise GlbAlignmentError(404, 'No such GLB layer')
  return layer


def set_layer_enabled(scene, layer, enabled, save=True):
  """Place a stored layer on the map, or take it off; the other layers stay as they are."""
  with _failing_as('Failed to update GLB'), locked_scene_write(scene):
    layer.refresh_from_db()
    if layer.enabled == enabled:
      raise GlbAlignmentError(400, 'GLB is already applied' if enabled else 'GLB is not currently applied')
    if enabled:
      require_base_map(scene)
    layer.enabled = enabled
    layer.save(update_fields=['enabled'])
    build_scene_map(scene)
    if save:
      scene.save()


def move_layer(scene, layer, anchor, save=True):
  """Move a stored layer to a new anchor; a placed layer re-places the scene map."""
  lat, lng, heading = parse_anchor(anchor)
  check_anchor_near_map_center(scene, lat, lng)

  with _failing_as('Failed to move GLB anchor'), locked_scene_write(scene):
    layer.refresh_from_db()
    footprint_m = layer.anchor.get('footprint_m') or {}
    if layer.enabled and (footprint_m.get('width', 0) <= 0 or footprint_m.get('height', 0) <= 0):
      raise GlbAlignmentError(400, 'Invalid GLB footprint')
    layer.anchor = {
      'lat': float(lat),
      'lng': float(lng),
      'heading_deg': float(heading),
      'footprint_m': footprint_m,
    }
    layer.save(update_fields=['anchor'])
    if layer.enabled:
      build_scene_map(scene)
    if save:
      scene.save()


def remove_layer(scene, layer):
  """Delete a stored layer; its file and preview go on commit and the scene map is re-placed."""
  with _failing_as('Failed to remove GLB'), locked_scene_write(scene):
    layer.refresh_from_db()
    was_enabled = layer.enabled
    layer.delete()
    if was_enabled:
      build_scene_map(scene)
    scene.save()


def scene_form_fields(scene):
  """Values of scene-edit form fields that the GLB apply, unapply and move paths write.

  The scene-edit form posts these fields as values, so the page must mirror them
  after a GLB change; otherwise Save Scene Updates restores the previous values.
  """
  return {name: getattr(scene, name) for name in SCENE_FORM_GLB_FIELDS}


def write_response(layer):
  """Alignment after a write: make sure the preview exists, then read it."""
  ensure_glb_preview(layer)
  return saved_alignment(layer)


def saved_alignment(layer):
  """Build the alignment response of one stored layer. Read-only.

  preview_url is the cached top view of the GLB file, enabled or not: the map overlay stretches
  it onto the footprint at the anchor heading, while scene.thumbnail is the posed render of the
  applied map and already carries the heading.
  """
  anchor_data = layer.anchor or {}
  footprint_data = anchor_data.get('footprint_m', {})

  preview_url = None
  if os.path.exists(glb_preview_name(layer.file.path)):
    preview_url = layer.file.storage.url(glb_preview_name(layer.file.name))

  return {
    'id': str(layer.id),
    'order': layer.order,
    'enabled': layer.enabled,
    'filename': os.path.basename(layer.file.name),
    'download_url': layer.file.url,
    'anchor': {
      'lat': float(anchor_data.get('lat', 0.0)),
      'lng': float(anchor_data.get('lng', 0.0)),
      'heading_deg': float(anchor_data.get('heading_deg', 0.0)),
    },
    'footprint_m': {
      'width': float(footprint_data.get('width', 0.0)),
      'height': float(footprint_data.get('height', 0.0)),
    },
    'preview_url': preview_url,
  }


def list_layers(scene):
  """Alignment of every stored layer of the scene, in draw order."""
  return [saved_alignment(layer) for layer in scene.glb_layers.all()]
