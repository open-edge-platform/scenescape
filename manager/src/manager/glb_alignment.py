# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stage an uploaded GLB and render a top-down preview for geospatial alignment."""

import math
import os
import time
import uuid
from functools import partial

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Q
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.earth_lla import (
  footprintAnchorFromCornersLLA,
  convertLLAToECEF, convertECEFToLLA, calculateTRSLocal2LLAFromSurfacePoints
)
from scene_common.glb_top_view import generateOrthoView
from scene_common.mesh_util import extractMeshFromGLB, getPosedMeshFootprint

from .models import Cam, Scene, SingletonSensor
from .validators import validate_glb

STAGING_SUBDIR = 'glb_staging'
STAGING_TTL_SECONDS = 24 * 3600
MAX_GLB_BYTES = settings.GLB_UPLOAD_MAX_BYTES
# Scene-edit form fields written by apply, unapply and move.
SCENE_FORM_GLB_FIELDS = (
  'scale', 'rotation_x', 'rotation_y', 'rotation_z',
  'translation_x', 'translation_y', 'translation_z', 'map_corners_lla',
)
# Pose and corner fields a scene-edit form posts; a mismatch with the stored row means a stale form.
POSE_CHECK_FIELDS = (
  'rotation_x', 'rotation_y', 'rotation_z',
  'translation_x', 'translation_y', 'translation_z', 'map_corners_lla',
)
# Staged GLBs are z-up (generated meshes and most exports), so no X rotation is applied
ALIGN_ROTATION_X = 0.0


def staging_dir():
  return os.path.join(settings.MEDIA_ROOT, STAGING_SUBDIR)


class GlbAlignmentError(Exception):
  """Failure with an HTTP status and a client-safe message."""

  def __init__(self, status, message):
    super().__init__(message)
    self.status = status
    self.message = message


def purge_stale_files():
  """Delete staged files older than STAGING_TTL_SECONDS."""
  if not os.path.isdir(staging_dir()):
    return
  cutoff = time.time() - STAGING_TTL_SECONDS
  for entry in os.scandir(staging_dir()):
    try:
      if entry.is_file() and entry.stat().st_mtime < cutoff:
        os.remove(entry.path)
    except FileNotFoundError:
      # Another request removed the file between scandir and stat/remove
      pass


def remove_staged_files(token):
  """Delete the staged GLB and preview PNG of a token, if present."""
  for ext in ('glb', 'png'):
    try:
      os.remove(os.path.join(staging_dir(), f'{token}.{ext}'))
    except FileNotFoundError:
      pass


def stage_glb(upload):
  """Validate an uploaded GLB and store it under a server-generated token.

  @return  token (UUID string)
  """
  purge_stale_files()
  if upload.size > MAX_GLB_BYTES:
    raise GlbAlignmentError(413, 'GLB file is too large')
  try:
    validate_glb(upload)
  except ValidationError as e:
    log.error(f'Rejected GLB upload: {e}')
    raise GlbAlignmentError(400, e.messages[0])
  token = str(uuid.uuid4())
  os.makedirs(staging_dir(), exist_ok=True)
  try:
    with open(os.path.join(staging_dir(), f'{token}.glb'), 'wb') as f:
      for chunk in upload.chunks():
        f.write(chunk)
  except OSError:
    # The token is never returned, so nothing else would clean up the partial file
    remove_staged_files(token)
    raise
  return token


def build_preview(token):
  """Render the staged GLB top-down (default alignment) and save it as <token>.png.

  @return  (footprint_m, px_per_m) with footprint_m = {"width": W, "height": H} in metres
  """
  scene = Scene(map=f'{STAGING_SUBDIR}/{token}.glb')
  width, height, _ = scene.autoAlignSceneMap(rotation_x=ALIGN_ROTATION_X)
  img_data, px_per_m = generateOrthoView(scene, scene.map.path)
  Image.fromarray(np.uint8(img_data)).save(os.path.join(staging_dir(), f'{token}.png'), format='PNG')
  return {'width': float(width), 'height': float(height)}, float(px_per_m)


def existing_content(scene):
  """Counts of content whose local frame a new GLB map would change."""
  return {
    'cameras': Cam.objects.filter(scene=scene).count(),
    'regions': scene.regions.count(),
    'sensors': SingletonSensor.objects.filter(scene=scene).count(),
  }


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


def staged_glb_path(token):
  """Get the file path for a staged GLB, validating the token format.

  Token must be a valid UUID string; build path only from canonical form.
  Raises GlbAlignmentError(400, 'Invalid token') if token is malformed.
  Raises GlbAlignmentError(404, 'Staged GLB not found or expired') if file does not exist.
  """
  if not isinstance(token, str):
    raise GlbAlignmentError(400, 'Invalid token')
  try:
    canonical = str(uuid.UUID(token))
  except (ValueError, AttributeError):
    raise GlbAlignmentError(400, 'Invalid token')
  path = os.path.join(staging_dir(), f'{canonical}.glb')
  if not os.path.isfile(path):
    raise GlbAlignmentError(404, 'Staged GLB not found or expired')
  return path


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


def _get_mesh_footprint_corners_from_glb(glb_path):
  """Load raw GLB mesh, apply axis conversion, and get z=0 AABB dimensions.

  Loads raw (unadjusted) mesh vertices, applies Rx(ALIGN_ROTATION_X) axis conversion,
  and computes the bounding rectangle at z=0.

  Returns (width_m, height_m) in the axis-converted frame.
  """
  # Load raw mesh (no rotation applied by extractMeshFromGLB)
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)

  # Get raw vertices
  vertices_raw = mesh.vertex.positions.numpy()  # (N, 3)

  # Apply axis conversion: Rx(ALIGN_ROTATION_X)
  R_x = Rotation.from_euler('x', [ALIGN_ROTATION_X], degrees=True)
  vertices_aligned = (R_x.as_matrix() @ vertices_raw.T).T

  # Get z=0 AABB of aligned vertices
  min_x = np.min(vertices_aligned[:, 0])
  max_x = np.max(vertices_aligned[:, 0])
  min_y = np.min(vertices_aligned[:, 1])
  max_y = np.max(vertices_aligned[:, 1])

  width_m = max_x - min_x
  height_m = max_y - min_y

  return width_m, height_m


def compute_glb_pose_and_corners(frame_corners_lla, anchor_lat, anchor_lng, anchor_heading,
                                  glb_width_m, glb_height_m, glb_path=None):
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

  # Get frame centre, heading, and dimensions
  frame_lat, frame_lng, frame_heading, frame_width, frame_height = \
    footprintAnchorFromCornersLLA(frame_corners_lla)

  # Frame local origin at SW corner (0, 0)
  frame_corners_local = np.array([
    [0.0, 0.0, 0.0],           # SW
    [frame_width, 0.0, 0.0],   # SE
    [frame_width, frame_height, 0.0],   # NE
    [0.0, frame_height, 0.0]   # NW
  ])
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(frame_corners_local, frame_corners_lla)

  # Convert anchor (global LLA) to frame-local metres
  anchor_ecef = convertLLAToECEF([anchor_lat, anchor_lng, 0.0])
  anchor_local = np.linalg.inv(frame_trs[:3, :3]) @ (anchor_ecef - frame_trs[:3, 3])

  # Load raw mesh and apply axis conversion
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  vertices_raw = mesh.vertex.positions.numpy()  # (N, 3)

  # Known bug: a legacy 90 deg X rotation is not preserved through move or reapply;
  # ALIGN_ROTATION_X is always used. Supposed to be resolved by ITEP-97904 PR.
  # Apply axis conversion: A = Rx(ALIGN_ROTATION_X)
  R_x = Rotation.from_euler('x', [ALIGN_ROTATION_X], degrees=True)
  vertices_aligned = (R_x.as_matrix() @ vertices_raw.T).T

  # Get aligned bounding box
  min_x_a = np.min(vertices_aligned[:, 0])
  max_x_a = np.max(vertices_aligned[:, 0])
  min_y_a = np.min(vertices_aligned[:, 1])
  max_y_a = np.max(vertices_aligned[:, 1])
  min_z_a = np.min(vertices_aligned[:, 2])

  # Rectangle centre in aligned frame
  p0 = np.array([(min_x_a + max_x_a) / 2.0, (min_y_a + max_y_a) / 2.0, 0.0])

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

  # Convert posed footprint to LLA
  posed_ecef = (frame_trs[:3, :3] @ mesh_footprint.T).T + frame_trs[:3, 3]
  map_corners_lla = np.array([convertECEFToLLA(corner) for corner in posed_ecef]).tolist()

  return rotation, translation, map_corners_lla



def remove_stored_file(storage, name):
  """Best-effort delete of a file from map storage; failures are ignored."""
  try:
    storage.delete(name)
  except Exception:
    pass


def _delete_map_if_unreferenced(storage, name):
  """Delete a replaced map file unless a scene row still references it."""
  if Scene.objects.filter(Q(map=name) | Q(base_map=name) | Q(glb_map=name)).exists():
    return
  remove_stored_file(storage, name)


def _delete_replaced_map_after_commit(scene, name):
  """Schedule deletion of a map file that scene.map no longer points to.

  Runs on commit only: a rollback restores the row, which still needs the file.
  """
  if name:
    transaction.on_commit(partial(_delete_map_if_unreferenced, scene.map.storage, name))


def stored_file_names(scene, fields):
  """Names of the stored files in fields, to restore them if a write rolls back."""
  return {field: getattr(scene, field).name or '' for field in fields}


def discard_failed_apply_files(scene, before):
  """Delete files written by a rolled-back apply, unapply or mesh save; restore the names.

  @param before  names from stored_file_names() taken before the write
  """
  for field, name_before in before.items():
    stored_file = getattr(scene, field)
    if stored_file.name and stored_file.name != name_before:
      remove_stored_file(stored_file.storage, stored_file.name)
    setattr(scene, field, name_before)


def _remove_replaced_glb(storage, glb_name):
  """Delete a replaced GLB and its cached preview; runs on commit."""
  remove_stored_file(storage, glb_name)
  remove_stored_file(storage, f'{os.path.splitext(glb_name)[0]}_preview.png')


def _same_value(posted, stored):
  """True when a posted form value equals the stored value; floats compare with a tiny tolerance."""
  if isinstance(posted, (list, tuple)) or isinstance(stored, (list, tuple)):
    return (isinstance(posted, (list, tuple)) and isinstance(stored, (list, tuple))
            and len(posted) == len(stored)
            and all(_same_value(p, s) for p, s in zip(posted, stored)))
  if posted is None or stored is None:
    return posted is None and stored is None
  try:
    return math.isclose(float(posted), float(stored), rel_tol=1e-9, abs_tol=1e-9)
  except (TypeError, ValueError):
    return posted == stored


def reject_stale_form_pose(stored, posted):
  """Raise 409 when a posted pose or corner value differs from the locked scene row.

  A form loaded before a GLB apply, unapply or move would otherwise write the old pose back.
  @param stored  scene row locked by the caller
  @param posted  form.cleaned_data
  """
  if not all(_same_value(posted.get(name), getattr(stored, name)) for name in POSE_CHECK_FIELDS):
    raise GlbAlignmentError(409, 'Scene pose changed since the form was loaded; reload and try again')


def _apply_pose_and_map(scene, glb_path=None):
  """Internal helper: copy glb_map into scene.map and set pose/corners/thumbnail.

  Does NOT change use_glb_map. Used by apply and _reapply_applied_glb.
  If glb_path is provided, it's used for map_corners_lla computation;
  otherwise the rectangle is used.
  """
  if not scene.glb_map or not scene.glb_anchor:
    raise GlbAlignmentError(400, 'No stored GLB or anchor')

  # Always copy: the map may be a GLB (e.g. a generated mesh) that is not the stored GLB
  previous_map = scene.map.name
  with scene.glb_map.storage.open(scene.glb_map.name, 'rb') as f:
    scene.map.save(f'{scene.name}.glb', File(f), save=False)
  _delete_replaced_map_after_commit(scene, previous_map)

  # Compute pose from glb_anchor and frame_corners_lla
  frame_corners = scene.base_map_corners_lla or scene.map_corners_lla
  if not frame_corners or not scene.glb_anchor:
    raise GlbAlignmentError(400, 'Cannot compute pose: missing frame or anchor')

  anchor_lat = scene.glb_anchor['lat']
  anchor_lng = scene.glb_anchor['lng']
  anchor_heading = scene.glb_anchor['heading_deg']
  glb_width = scene.glb_anchor['footprint_m']['width']
  glb_height = scene.glb_anchor['footprint_m']['height']

  # Use real mesh for map_corners_lla if glb_path provided
  glb_path_for_corners = glb_path or scene.glb_map.path

  rotation, translation, map_corners = compute_glb_pose_and_corners(
    frame_corners, anchor_lat, anchor_lng, anchor_heading, glb_width, glb_height,
    glb_path=glb_path_for_corners
  )
  scene.rotation_x = rotation[0]
  scene.rotation_y = rotation[1]
  scene.rotation_z = rotation[2]
  scene.translation_x = translation[0]
  scene.translation_y = translation[1]
  scene.translation_z = translation[2]
  scene.map_corners_lla = map_corners

  scene.saveThumbnail()


def apply_glb_map(scene):
  """Apply a stored GLB (use_glb_map False->True).

  Moves snapshot to base_map/base_scale, sets scene.map = glb_map content,
  computes pose from glb_anchor, sets map_corners_lla, saves thumbnail.
  Keeps trs_matrix untouched. Returns saved_alignment dict.
  """
  if not scene.glb_map or not scene.glb_anchor:
    raise GlbAlignmentError(400, 'No stored GLB or anchor')
  if scene.use_glb_map:
    raise GlbAlignmentError(400, 'GLB is already applied')

  before = stored_file_names(scene, ('map', 'base_map'))
  try:
    with transaction.atomic():
      lock_scene_row(scene)
      # Save current snapshot as base if not already saved
      if scene.map:
        base_ext = os.path.splitext(scene.map.name)[1].lower()
        previous_base = scene.base_map.name
        with scene.map.storage.open(scene.map.name, 'rb') as f:
          scene.base_map.save(f'base_{scene.name}{base_ext}', File(f), save=False)
        _delete_replaced_map_after_commit(scene, previous_base)
        scene.base_scale = scene.scale
        if not scene.base_map_corners_lla:
          scene.base_map_corners_lla = scene.map_corners_lla

      _apply_pose_and_map(scene)

      scene.use_glb_map = True
      scene.save()
  except GlbAlignmentError:
    discard_failed_apply_files(scene, before)
    raise
  except Exception as e:
    discard_failed_apply_files(scene, before)
    log.error(f'Failed to apply GLB: {e}')
    raise GlbAlignmentError(500, 'Failed to apply GLB')

  return saved_alignment(scene)


def unapply_glb_map(scene):
  """Unapply a GLB (use_glb_map True->False).

  Restores scene.map = base_map content, scale = base_scale,
  map_corners_lla = base_map_corners_lla, resets rotation/translation,
  clears base_map/base_scale. Keeps trs_matrix and glb_map/glb_anchor.
  """
  if not scene.use_glb_map:
    raise GlbAlignmentError(400, 'GLB is not currently applied')

  before = stored_file_names(scene, ('map', 'base_map'))
  try:
    with transaction.atomic():
      lock_scene_row(scene)
      previous_map = scene.map.name
      if scene.base_map and scene.base_map.storage.exists(scene.base_map.name):
        base_ext = os.path.splitext(scene.base_map.name)[1]
        with scene.base_map.storage.open(scene.base_map.name, 'rb') as f:
          scene.map.save(f'{scene.name}{base_ext}', File(f), save=False)
      else:
        scene.map = ''  # None crashes Scene.save() on the map-name check
      _delete_replaced_map_after_commit(scene, previous_map)

      scene.scale = scene.base_scale
      scene.map_corners_lla = scene.base_map_corners_lla
      scene.resetRotation()
      scene.resetTranslation()
      scene.thumbnail = None
      scene.use_glb_map = False

      # The base file is removed on commit only: a rollback restores base_map, which still needs it
      _delete_replaced_map_after_commit(scene, scene.base_map.name)
      scene.base_map = None
      scene.base_scale = None

      scene.save()
  except GlbAlignmentError:
    discard_failed_apply_files(scene, before)
    raise
  except Exception as e:
    discard_failed_apply_files(scene, before)
    log.error(f'Failed to unapply GLB: {e}')
    raise GlbAlignmentError(500, 'Failed to unapply GLB')

  return _write_response(scene)


def move_glb_anchor(scene, new_anchor, save=True):
  """Move an already-stored GLB to a new anchor (changes glb_anchor only).

  If use_glb_map is True, recomputes pose and map_corners_lla + thumbnail.
  If False, just stores the new anchor.
  save=False leaves the row unsaved for the caller to save in the same transaction.
  """
  lat, lng, heading = parse_anchor(new_anchor)

  try:
    with transaction.atomic():
      lock_scene_row(scene)
      # Update anchor with footprint from existing
      footprint_m = scene.glb_anchor.get('footprint_m') if scene.glb_anchor else {}
      scene.glb_anchor = {
        'lat': float(lat),
        'lng': float(lng),
        'heading_deg': float(heading),
        'footprint_m': footprint_m,
      }

      if scene.use_glb_map:
        # Recompute pose
        frame_corners = scene.base_map_corners_lla or scene.map_corners_lla
        if not frame_corners:
          raise GlbAlignmentError(400, 'Cannot compute pose: missing frame')

        glb_width = footprint_m.get('width', 0)
        glb_height = footprint_m.get('height', 0)
        if glb_width <= 0 or glb_height <= 0:
          raise GlbAlignmentError(400, 'Invalid GLB footprint')

        rotation, translation, map_corners = compute_glb_pose_and_corners(
          frame_corners, lat, lng, heading, glb_width, glb_height,
          glb_path=scene.glb_map.path
        )
        scene.rotation_x = rotation[0]
        scene.rotation_y = rotation[1]
        scene.rotation_z = rotation[2]
        scene.translation_x = translation[0]
        scene.translation_y = translation[1]
        scene.translation_z = translation[2]
        scene.map_corners_lla = map_corners

        scene.saveThumbnail()

      if save:
        scene.save()
  except GlbAlignmentError:
    raise
  except Exception as e:
    log.error(f'Failed to move GLB anchor: {e}')
    raise GlbAlignmentError(500, 'Failed to move GLB anchor')

  return _write_response(scene)


def set_glb_applied(scene, use_glb):
  """Apply or unapply the stored GLB to reach the requested state; no-op if already there."""
  if use_glb and not scene.use_glb_map:
    apply_glb_map(scene)
  elif not use_glb and scene.use_glb_map:
    unapply_glb_map(scene)


def remove_glb_map(scene):
  """Remove a stored GLB (delete glb_map and clear glb_anchor).

  If use_glb_map was True, first unapply it (legacy: map becomes empty, frame kept).
  Deletes cached preview file if present.
  """
  try:
    with transaction.atomic():
      # Delete cached preview if present
      if scene.glb_map:
        remove_stored_file(scene.glb_map.storage, f'{os.path.splitext(scene.glb_map.name)[0]}_preview.png')

      # If applied, unapply first
      if scene.use_glb_map:
        unapply_glb_map(scene)

      # Remove glb_map file
      if scene.glb_map and scene.glb_map.storage.exists(scene.glb_map.name):
        remove_stored_file(scene.glb_map.storage, scene.glb_map.name)
      scene.glb_map = None
      scene.glb_anchor = None

      scene.save()
  except Exception as e:
    log.error(f'Failed to remove GLB: {e}')
    raise GlbAlignmentError(500, 'Failed to remove GLB')


def _reapply_applied_glb(scene):
  """Re-copy the newly stored GLB into the applied map, keeping base_map/base_scale."""
  try:
    _apply_pose_and_map(scene, glb_path=scene.glb_map.path)
  except GlbAlignmentError:
    raise
  except Exception as e:
    log.error(f'Failed to update GLB pose: {e}')
    raise GlbAlignmentError(500, 'Failed to update GLB pose')


def commit_glb(scene, token, anchor, save=True):
  """Store a staged GLB with its anchor; does not apply it.

  This is the POST endpoint: stages the GLB as glb_map with the anchor.
  Computes footprint from the real mesh file (not touching scene.map/pose).
  If use_glb_map was already True, re-applies the new GLB to the scene map.
  Otherwise, applying is a separate PUT with use_glb_map=true.
  save=False leaves the row unsaved for the caller to save in the same transaction.
  Returns saved_alignment dict.
  """
  path = staged_glb_path(token)
  lat, lng, heading = parse_anchor(anchor)

  old_glb = scene.glb_map.name if scene.glb_map else ''
  try:
    with transaction.atomic():
      lock_scene_row(scene)
      # Save the staged GLB as glb_map
      with open(path, 'rb') as f:
        scene.glb_map.save(f'{scene.name}.glb', File(f), save=False)

      # Get footprint from the real mesh (extract and measure, not autoAlignSceneMap)
      width, height = _get_mesh_footprint_corners_from_glb(scene.glb_map.path)

      scene.glb_anchor = {
        'lat': float(lat),
        'lng': float(lng),
        'heading_deg': float(heading),
        'footprint_m': {'width': float(width), 'height': float(height)},
      }

      # Initialize base_map_corners_lla if not set (from current frame)
      if not scene.base_map_corners_lla:
        scene.base_map_corners_lla = scene.map_corners_lla

      # If already applied, re-apply with new GLB; otherwise just store
      if scene.use_glb_map:
        _reapply_applied_glb(scene)
      if save:
        scene.save()

      # Staged and replaced files are removed on commit only: a rollback keeps the old GLB row
      if old_glb and old_glb != scene.glb_map.name:
        transaction.on_commit(partial(_remove_replaced_glb, scene.glb_map.storage, old_glb))
      transaction.on_commit(partial(remove_staged_files, str(uuid.UUID(token))))

  except Exception:
    if scene.glb_map.name != old_glb:
      remove_stored_file(scene.glb_map.storage, scene.glb_map.name)
    raise

  purge_stale_files()

  return _write_response(scene)


def scene_form_fields(scene):
  """Values of scene-edit form fields that the GLB apply, unapply and move paths write.

  The scene-edit form posts these fields as values, so the page must mirror them
  after a GLB change; otherwise Save Scene Updates restores the previous values.
  """
  return {name: getattr(scene, name) for name in SCENE_FORM_GLB_FIELDS}


def unapplied_preview_path(glb_path):
  """Cache path of the unapplied top-view preview, stored next to the GLB file."""
  glb_base = os.path.splitext(os.path.basename(glb_path))[0]
  return os.path.join(os.path.dirname(glb_path), f'{glb_base}_preview.png')


def ensure_unapplied_preview(scene):
  """Render the unapplied preview of the stored GLB if it is not cached yet.

  Called from write paths only, never from the GET read path. The preview depends
  only on the GLB file. A failed render is logged and retried on the next write.
  """
  if scene.use_glb_map or not scene.glb_map:
    return
  preview_path = unapplied_preview_path(scene.glb_map.path)
  if os.path.exists(preview_path):
    return
  try:
    # Alignment rotation only; generateOrthoView does not use translation
    temp_scene = Scene(map=scene.glb_map.path)
    temp_scene.rotation_x = ALIGN_ROTATION_X
    temp_scene.rotation_y = 0.0
    temp_scene.rotation_z = 0.0
    img_data, _ = generateOrthoView(temp_scene, scene.glb_map.path)
    Image.fromarray(np.uint8(img_data)).save(preview_path, format='PNG')
  except Exception as e:
    log.warning(f'Failed to generate GLB preview: {e}')


def _write_response(scene):
  """Response for write paths: make sure the unapplied preview exists, then read it."""
  if not scene.glb_map:
    return None
  ensure_unapplied_preview(scene)
  return saved_alignment(scene)


def saved_alignment(scene):
  """Build alignment response from a scene with a stored GLB.

  Returns dict with exists, filename, download_url, anchor, footprint_m, use_glb_map, preview_url.
  Returns exists=false if no GLB stored.

  Read-only. For applied GLB: uses cached scene.thumbnail. For unapplied GLB: uses the
  cached preview file if it exists (rendered by ensure_unapplied_preview on write paths).
  """
  if not scene.glb_map or not scene.glb_anchor:
    return {
      'exists': False,
    }

  anchor_data = scene.glb_anchor
  footprint_data = anchor_data.get('footprint_m', {})

  preview_url = None
  if scene.use_glb_map and scene.thumbnail:
    # Use the thumbnail cached when GLB was applied
    preview_url = scene.thumbnail.url
  else:
    preview_path = unapplied_preview_path(scene.glb_map.path)
    if os.path.exists(preview_path):
      preview_name = os.path.join(os.path.dirname(scene.glb_map.name), os.path.basename(preview_path))
      preview_url = scene.glb_map.storage.url(preview_name)

  return {
    'exists': True,
    'filename': os.path.basename(scene.glb_map.name),
    'download_url': scene.glb_map.url,
    'anchor': {
      'lat': float(anchor_data.get('lat', 0.0)),
      'lng': float(anchor_data.get('lng', 0.0)),
      'heading_deg': float(anchor_data.get('heading_deg', 0.0)),
    },
    'footprint_m': {
      'width': float(footprint_data.get('width', 0.0)),
      'height': float(footprint_data.get('height', 0.0)),
    },
    'use_glb_map': scene.use_glb_map,
    'preview_url': preview_url,
  }
