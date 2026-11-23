# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import open3d as o3d
import numpy as np
import open3d.visualization.rendering as rendering
from scene_common.mesh_util import extractMeshFromGLB, VECTOR_PROPERTIES, SCALAR_PROPERTIES

from scene_common import log

SUNLIGHT_INTENSITY = 100000
SUNLIGHT_DIRECTION = [0.0, 0.0, -1.0]
SUNLIGHT_COLOR = [1.0, 1.0, 1.0]

VERTICAL_FOV = 40
THUMBNAIL_RESOLUTION = {'x': 1024, 'y': 768}
MAX_THUMBNAIL_TEXTURE_SIZE = 4096
_THUMBNAIL_TEXTURE_ATTRS = {
  "albedo": "albedo_img",
  "normal": "normal_img",
  "ao_rough_metal": "ao_rough_metal_img",
}

def _legacyTextureForRender(texture):
  """! Cap oversized textures before Open3D offscreen upload, then convert.
  Resize is in-memory only; the caller's texture_maps entry is unchanged.
  """
  longest_side = max(texture.columns, texture.rows)
  if longest_side > MAX_THUMBNAIL_TEXTURE_SIZE:
    texture = texture.resize(MAX_THUMBNAIL_TEXTURE_SIZE / longest_side,
                             o3d.t.geometry.InterpType.Linear)
  return texture.to_legacy()

def materialToMaterialRecord(mat):
  mat_record = o3d.visualization.rendering.MaterialRecord()
  for key in VECTOR_PROPERTIES:
    setattr(mat_record, key, mat.vector_properties[key])
  for key in SCALAR_PROPERTIES:
    if key in mat.scalar_properties:
      setattr(mat_record, key, mat.scalar_properties[key])

  # Convert texture maps (same upload cap as thumbnail rendering)
  if "albedo" in mat.texture_maps:
    mat_record.albedo_img = _legacyTextureForRender(mat.texture_maps["albedo"])
  if "normal" in mat.texture_maps:
    mat_record.normal_img = _legacyTextureForRender(mat.texture_maps["normal"])
  if "ao_rough_metal" in mat.texture_maps:
    mat_record.ao_rough_metal_img = _legacyTextureForRender(
      mat.texture_maps["ao_rough_metal"])
  return mat_record

def _thumbnailMaterialRecord(material):
  """! Builds the MaterialRecord for the thumbnail from a tensor material.
  Only albedo / normal / ao_rough_metal are used for the thumbnail; other maps are
  skipped so large atlases are not resized for no benefit.
  @param  material           tensor material with vector/scalar properties and texture maps.

  @return mat_record         MaterialRecord ready for rendering.
  """
  mat_record = rendering.MaterialRecord()
  mat_record.shader = "defaultLit"
  for key, value in (getattr(material, 'vector_properties', None) or {}).items():
    setattr(mat_record, key, value)
  for key, value in (getattr(material, 'scalar_properties', None) or {}).items():
    setattr(mat_record, key, value)
  for key, value in (getattr(material, 'texture_maps', None) or {}).items():
    if key in _THUMBNAIL_TEXTURE_ATTRS:
      setattr(mat_record, _THUMBNAIL_TEXTURE_ATTRS[key], _legacyTextureForRender(value))
  return mat_record

def _addTensorMesh(renderer, triangle_mesh, tensor_mesh):
  """! Adds the first tensor mesh's geometry with its material; skipped without a material.
  @param  renderer           offscreen renderer receiving the geometry.
  @param  triangle_mesh      Triangle mesh geometry.
  @param  tensor_mesh        List of tensor meshes with materials.
  """
  material = getattr(tensor_mesh[0], 'material', None)
  if material is None:
    return
  renderer.scene.add_geometry("mesh", triangle_mesh, _thumbnailMaterialRecord(material))

def _orthoFrame(glb_size, res_x, res_y):
  """! Visible width and height in metres of the ortho camera, keeping the mesh aspect ratio.
  @param  glb_size           mesh dimensions.
  @param  res_x              width of capture.
  @param  res_y              height of capture.

  @return right              visible width in metres.
  @return top                visible height in metres.
  """
  floor_width = glb_size[0]
  floor_height = glb_size[1]
  aspect_ratio = res_x / res_y
  if floor_width / floor_height > aspect_ratio:
    return floor_width, floor_width / aspect_ratio
  return floor_height * aspect_ratio, floor_height

def _setOrthoCamera(renderer, triangle_mesh, glb_size, res_x, res_y):
  """! Points an orthographic camera down at the mesh.
  @param  renderer           offscreen renderer whose camera is set.
  @param  triangle_mesh      Triangle mesh geometry.
  @param  glb_size           mesh dimensions.
  @param  res_x              width of capture.
  @param  res_y              height of capture.

  @return pixels_per_meter   determined pixels per meter.
  @return origin             mesh-frame [x, y] of the image's bottom-left corner.
  """
  bounds = triangle_mesh.get_axis_aligned_bounding_box()
  min_bound = bounds.min_bound.numpy()
  max_bound = bounds.max_bound.numpy()
  right, top = _orthoFrame(glb_size, res_x, res_y)

  min_z = float(min_bound[2])
  max_z = float(max_bound[2])
  center_x = float((min_bound[0] + max_bound[0]) / 2)
  center_y = float((min_bound[1] + max_bound[1]) / 2)
  margin = max(float(glb_size.max()), 1e-3)
  camera = renderer.scene.camera
  camera.look_at(
    [center_x, center_y, min_z],
    [center_x, center_y, max_z + margin],
    [0.0, 1.0, 0.0]
  )
  camera.set_projection(camera.Projection.Ortho,
                        -right / 2, right / 2, -top / 2, top / 2,
                        0.0, max_z - min_z + 2 * margin)
  # We use the vertical resolution as the base for all computations
  return res_y / top, [center_x - right / 2, center_y - top / 2]

def _setupTopView(triangle_mesh, tensor_mesh, glb_size, res_x, res_y):
  """! Builds the offscreen top-view renderer for the mesh without capturing it.
  @param  triangle_mesh      Triangle mesh geometry.
  @param  tensor_mesh        List of tensor meshes with materials.
  @param  glb_size           mesh dimensions.
  @param  res_x              width of capture.
  @param  res_y              height of capture.

  @return renderer           renderer ready to capture.
  @return pixels_per_meter   determined pixels per meter.
  @return origin             mesh-frame [x, y] of the image's bottom-left corner.
  """
  if not tensor_mesh:
    raise ValueError("tensor_mesh is empty; cannot access its first element.")

  renderer = rendering.OffscreenRenderer(res_x, res_y)
  _addTensorMesh(renderer, triangle_mesh, tensor_mesh)
  renderer.scene.scene.set_sun_light(SUNLIGHT_DIRECTION,
                                     SUNLIGHT_COLOR,
                                     SUNLIGHT_INTENSITY)
  renderer.scene.scene.enable_sun_light(True)
  renderer.scene.show_axes(False)
  pixels_per_meter, origin = _setOrthoCamera(renderer, triangle_mesh, glb_size, res_x, res_y)
  return renderer, pixels_per_meter, origin

def renderTopView(triangle_mesh, tensor_mesh, glb_size, res_x, res_y):
  """! Renders the top view of the mesh and returns the capture
    with specified resolution.
  @param  triangle_mesh      Triangle mesh geometry.
  @param  tensor_mesh        List of tensor meshes with materials.
  @param  glb_size           mesh dimensions.
  @param  res_x              width of capture.
  @param  res_y              height of capture.

  @return img                captured image as array.
  @return pixels_per_meter   determined pixels per meter.
  @return origin             mesh-frame [x, y] of the image's bottom-left corner.
  """
  renderer, pixels_per_meter, origin = _setupTopView(triangle_mesh, tensor_mesh, glb_size, res_x, res_y)
  img = renderer.render_to_image()
  return img, pixels_per_meter, origin

def renderTopViewWithMask(triangle_mesh, tensor_mesh, glb_size, res_x, res_y):
  """! Renders the top view and a mask of the pixels covered by the mesh.
  The orthographic depth buffer holds 1.0 where nothing was drawn, so the mask is depth < 1.0.
  @param  triangle_mesh      Triangle mesh geometry.
  @param  tensor_mesh        List of tensor meshes with materials.
  @param  glb_size           mesh dimensions.
  @param  res_x              width of capture.
  @param  res_y              height of capture.

  @return img                captured image as array.
  @return pixels_per_meter   determined pixels per meter.
  @return mask               boolean array, True where the mesh is drawn.
  """
  renderer, pixels_per_meter, _ = _setupTopView(triangle_mesh, tensor_mesh, glb_size, res_x, res_y)
  img = renderer.render_to_image()
  depth = np.asarray(renderer.render_to_depth_image(z_in_view_space=False))
  return img, pixels_per_meter, depth < 1.0

def getMeshSize(mesh):
  """! Returns the mesh size as [width, height, depth].
  @param  mesh               Triangle mesh geometry.

  @return size               dimensions.
  """
  size = (mesh.get_axis_aligned_bounding_box().get_extent()).numpy()
  return size

def thumbnailResolution(glb_size):
  """! Largest resolution within THUMBNAIL_RESOLUTION that keeps the mesh aspect ratio.
  The overlay stretches the image onto the footprint, so the aspect must match.
  @param  glb_size           mesh dimensions [width, height, depth].

  @return (res_x, res_y)     pixel resolution.
  """
  scale = min(THUMBNAIL_RESOLUTION['x'] / glb_size[0], THUMBNAIL_RESOLUTION['y'] / glb_size[1])
  return max(1, int(round(glb_size[0] * scale))), max(1, int(round(glb_size[1] * scale)))

def generateOrthoView(scene_obj, glb_file):
  """! generates the orthographic perspective of 3d glb.
  @param  scene_obj          Scene object.
  @param  glb_file           path to glb file.

  @return img                captured image as numpy array.
  @return pixels_per_meter   determined pixels per meter.
  @return origin             mesh-frame [x, y] of the image's bottom-left corner.
  """
  triangle_mesh, tensor_mesh, glb_size, res_x, res_y = _prepareOrthoMesh(scene_obj, glb_file)
  img, pixels_per_meter, origin = renderTopView(triangle_mesh,
                                                tensor_mesh,
                                                glb_size,
                                                res_x,
                                                res_y)
  return np.array(img), pixels_per_meter, origin

def generateOrthoViewWithMask(scene_obj, glb_file):
  """! generates the orthographic perspective of 3d glb and the mask of its footprint.
  @param  scene_obj          Scene object.
  @param  glb_file           path to glb file.

  @return img                captured numpy array.
  @return pixels_per_meter   determined pixels per meter.
  @return mask               boolean numpy array, True where the glb is drawn.
  """
  triangle_mesh, tensor_mesh, glb_size, res_x, res_y = _prepareOrthoMesh(scene_obj, glb_file)
  img, pixels_per_meter, mask = renderTopViewWithMask(triangle_mesh,
                                                      tensor_mesh,
                                                      glb_size,
                                                      res_x,
                                                      res_y)
  return np.array(img), pixels_per_meter, mask

def _prepareOrthoMesh(scene_obj, glb_file):
  """! Loads, transforms and frames the glb for an orthographic render.
  @param  scene_obj          Scene object.
  @param  glb_file           path to glb file.

  @return triangle_mesh      transformed triangle mesh.
  @return tensor_mesh        tensor meshes with materials.
  @return glb_size           mesh dimensions.
  @return res_x, res_y       thumbnail resolution.
  """
  rotation_vector = np.float64([scene_obj.rotation_x,
                                scene_obj.rotation_y,
                                scene_obj.rotation_z])
  triangle_mesh, tensor_mesh = extractMeshFromGLB(glb_file)
  scale = np.float64([
    getattr(scene_obj, f"scale_{axis}", 1.0) if getattr(scene_obj, f"scale_{axis}", 1.0) is not None else 1.0
    for axis in "xyz"])
  transform = np.eye(4)
  transform[:3, :3] = o3d.geometry.get_rotation_matrix_from_xyz(
    np.deg2rad(rotation_vector)) @ np.diag(scale)
  triangle_mesh.transform(transform)
  # The image starts at the model's min corner; the 2D views offset it by Scene.mapOrigin().
  triangle_mesh.translate(-triangle_mesh.get_axis_aligned_bounding_box().min_bound.numpy())

  glb_size = getMeshSize(triangle_mesh)
  res_x, res_y = thumbnailResolution(glb_size)
  return triangle_mesh, tensor_mesh, glb_size, res_x, res_y
