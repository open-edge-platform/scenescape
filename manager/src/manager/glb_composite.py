# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""! Hybrid scene view: the GLB top view composited over the flat base map.

A hybrid scene keeps the flat map it had before the GLB was applied (base_map, at
base_scale pixels per metre) and draws the posed GLB over it. The 2D thumbnail is
the composite, in the base map's pixel grid, so it starts at the frame origin.
"""

import numpy as np
from PIL import Image

from scene_common.earth_lla import llaToFrameLocalXY
from scene_common.glb_top_view import generateOrthoViewWithMask


def isHybridView(scene):
  """! True when the scene shows the GLB over its flat base map.
  @param  scene              Scene object (or any object with the same fields).

  @return bool               True if a GLB is applied on top of a base map.
  """
  return bool(scene.use_glb_map and scene.base_map and scene.base_scale
              and scene.base_map_corners_lla and scene.map_corners_lla)


def compositeGlbOverBaseMap(base_rgb, glb_rgb, glb_mask, glb_ppm, base_scale, offset_m):
  """! Paste the GLB top view onto the flat base map.
  @param  base_rgb           (H, W, 3) uint8 base map, origin at its bottom-left corner.
  @param  glb_rgb            (h, w, 3) uint8 GLB top view rendered at glb_ppm pixels per metre.
  @param  glb_mask           (h, w) bool array, True where the GLB is drawn.
  @param  glb_ppm            pixels per metre of glb_rgb.
  @param  base_scale         pixels per metre of base_rgb.
  @param  offset_m           (x, y) metres from the base origin to the GLB's bottom-left corner.

  @return out                (H, W, 3) uint8 composite; base pixels stay where the GLB is not drawn.
  """
  height, width = base_rgb.shape[:2]
  glb_rgb, glb_mask = _resizeToScale(glb_rgb, glb_mask, base_scale / glb_ppm)
  glb_h, glb_w = glb_rgb.shape[:2]
  left = int(round(offset_m[0] * base_scale))
  # Image rows grow downwards, the frame's y grows upwards.
  top = height - int(round(offset_m[1] * base_scale)) - glb_h

  out = np.array(base_rgb, dtype=np.uint8, copy=True)
  x0, y0 = max(0, left), max(0, top)
  x1, y1 = min(width, left + glb_w), min(height, top + glb_h)
  if x0 >= x1 or y0 >= y1:
    return out
  src_rgb = glb_rgb[y0 - top:y1 - top, x0 - left:x1 - left]
  src_mask = glb_mask[y0 - top:y1 - top, x0 - left:x1 - left]
  region = out[y0:y1, x0:x1]
  region[src_mask] = src_rgb[src_mask]
  return out


def _resizeToScale(glb_rgb, glb_mask, factor):
  """! Resize the GLB image and its mask by factor; the mask uses nearest neighbour."""
  new_h = max(1, round(glb_rgb.shape[0] * factor))
  new_w = max(1, round(glb_rgb.shape[1] * factor))
  rgb = Image.fromarray(np.uint8(glb_rgb)).resize((new_w, new_h), Image.Resampling.BILINEAR)
  mask = Image.fromarray(glb_mask.astype(np.uint8) * 255).resize(
    (new_w, new_h), Image.Resampling.NEAREST)
  return np.asarray(rgb), np.asarray(mask) > 0


def hybridThumbnail(scene):
  """! Render the composite thumbnail of a hybrid scene.
  @param  scene              Scene with use_glb_map, base_map, base_scale, map and corner fields.

  @return img                (H, W, 3) uint8 composite in the base map's grid.
  @return pixels_per_meter   the base map's scale, which the composite is drawn at.
  """
  glb_img, glb_ppm, glb_mask = generateOrthoViewWithMask(scene, scene.map.path)
  with scene.base_map.storage.open(scene.base_map.name, 'rb') as f:
    base_rgb = np.asarray(Image.open(f).convert('RGB'))
  lat, lng = scene.map_corners_lla[0][:2]
  offset_m = llaToFrameLocalXY(scene.base_map_corners_lla, lat, lng).tolist()
  img = compositeGlbOverBaseMap(base_rgb, glb_img, glb_mask, glb_ppm,
                                scene.base_scale, offset_m)
  return img, scene.base_scale
