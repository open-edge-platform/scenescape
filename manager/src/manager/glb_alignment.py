# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Geospatial GLB alignment API.

The code lives in glb_staging (staged uploads and previews) and glb_state (stored GLB and scene
writes); this module keeps the original import path. Patch a name on the module that owns it.
"""

from .glb_staging import (
  ALIGN_ROTATION_X, MAX_GLB_BYTES, STAGING_SUBDIR, STAGING_TTL_SECONDS, GlbAlignmentError,
  build_preview, ensure_glb_preview, glb_preview_path, purge_stale_files, remove_staged_files,
  stage_glb, staged_glb_path, staging_dir
)
from .glb_state import (
  EARTH_RADIUS_KM, GLB_STORED_FILES, MAX_ANCHOR_DISTANCE_KM, SCENE_FORM_GLB_FIELDS,
  STATE_TOKEN_FIELDS, apply_glb_map, check_anchor_near_map_center, commit_glb,
  compute_glb_pose_and_corners, discard_files_on_failure, existing_content, get_geospatial_scene,
  lock_scene_row, locked_scene_write, move_glb_anchor, parse_anchor, reject_stale_form,
  remove_glb_map, remove_stored_file, saved_alignment, scene_form_fields, scene_state_token,
  set_glb_applied, stored_file_names, unapply_glb_map, write_response
)

__all__ = [
  'ALIGN_ROTATION_X', 'EARTH_RADIUS_KM', 'GLB_STORED_FILES', 'GlbAlignmentError', 'MAX_ANCHOR_DISTANCE_KM',
  'MAX_GLB_BYTES', 'SCENE_FORM_GLB_FIELDS', 'STAGING_SUBDIR', 'STAGING_TTL_SECONDS', 'STATE_TOKEN_FIELDS',
  'apply_glb_map', 'build_preview', 'check_anchor_near_map_center', 'commit_glb',
  'compute_glb_pose_and_corners', 'discard_files_on_failure', 'ensure_glb_preview', 'existing_content',
  'get_geospatial_scene', 'glb_preview_path', 'lock_scene_row', 'locked_scene_write', 'move_glb_anchor',
  'parse_anchor', 'purge_stale_files', 'reject_stale_form', 'remove_glb_map', 'remove_staged_files',
  'remove_stored_file', 'saved_alignment', 'scene_form_fields', 'scene_state_token', 'set_glb_applied',
  'stage_glb', 'staged_glb_path', 'staging_dir', 'stored_file_names', 'unapply_glb_map', 'write_response',
]
