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
  src_h, src_w = glb_rgb.shape[:2]
  factor = base_scale / glb_ppm
  glb_h = max(1, round(src_h * factor))
  glb_w = max(1, round(src_w * factor))
  left = int(round(offset_m[0] * base_scale))
  # Image rows grow downwards, the frame's y grows upwards.
  top = height - int(round(offset_m[1] * base_scale)) - glb_h

  out = np.array(base_rgb, dtype=np.uint8, copy=True)
  x0, y0 = max(0, left), max(0, top)
  x1, y1 = min(width, left + glb_w), min(height, top + glb_h)
  if x0 >= x1 or y0 >= y1:
    return out
  # Only the visible part is resampled, so memory follows the base image, not the footprint.
  sx, sy = src_w / glb_w, src_h / glb_h
  box = ((x0 - left) * sx, (y0 - top) * sy, (x1 - left) * sx, (y1 - top) * sy)
  cx0, cy0 = int(np.floor(box[0])), int(np.floor(box[1]))
  cx1, cy1 = min(src_w, int(np.ceil(box[2]))), min(src_h, int(np.ceil(box[3])))
  rel_box = (box[0] - cx0, box[1] - cy0, min(box[2], cx1) - cx0, min(box[3], cy1) - cy0)
  size = (x1 - x0, y1 - y0)
  rgb = Image.fromarray(np.uint8(glb_rgb[cy0:cy1, cx0:cx1])).resize(
    size, Image.Resampling.BILINEAR, box=rel_box)
  mask = Image.fromarray(glb_mask[cy0:cy1, cx0:cx1].astype(np.uint8) * 255).resize(
    size, Image.Resampling.NEAREST, box=rel_box)
  src_mask = np.asarray(mask) > 0
  region = out[y0:y1, x0:x1]
  region[src_mask] = np.asarray(rgb)[src_mask]
  return out


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
