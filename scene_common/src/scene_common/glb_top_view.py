# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
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

def materialToMaterialRecord(mat):
  mat_record = o3d.visualization.rendering.MaterialRecord()
  for key in VECTOR_PROPERTIES:
    setattr(mat_record, key, mat.vector_properties[key])
  for key in SCALAR_PROPERTIES:
    if key in mat.scalar_properties:
      setattr(mat_record, key, mat.scalar_properties[key])

  # Convert texture maps
  if "albedo" in mat.texture_maps:
    mat_record.albedo_img = mat.texture_maps["albedo"].to_legacy()
  if "normal" in mat.texture_maps:
    mat_record.normal_img = mat.texture_maps["normal"].to_legacy()
  if "ao_rough_metal" in mat.texture_maps:
    mat_record.ao_rough_metal_img = mat.texture_maps["ao_rough_metal"].to_legacy()
  return mat_record

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
  """
  renderer = rendering.OffscreenRenderer(res_x, res_y)

  # Add tensor meshes with materials (convert Material -> MaterialRecord)
  mat_record = rendering.MaterialRecord()
  mat_record.shader = "defaultLit"
  if not tensor_mesh:
    raise ValueError("tensor_mesh is empty; cannot access its first element.")
  tmesh = tensor_mesh[0]
  if hasattr(tmesh, 'material') and tmesh.material is not None:
    if hasattr(tmesh.material, 'vector_properties'):
      for key, value in tmesh.material.vector_properties.items():
        setattr(mat_record, key, value)
    if hasattr(tmesh.material, 'scalar_properties'):
      for key, value in tmesh.material.scalar_properties.items():
        setattr(mat_record, key, value)
    if hasattr(tmesh.material, 'texture_maps'):
      for key, value in tmesh.material.texture_maps.items():
        if key == "albedo":
          mat_record.albedo_img = value.to_legacy()
        elif key == "normal":
          mat_record.normal_img = value.to_legacy()
        elif key == "ao_rough_metal":
          mat_record.ao_rough_metal_img = value.to_legacy()

    if mat_record is None or not hasattr(mat_record, 'shader'):
      raise ValueError("mat_record is empty or not properly initialized.")

    renderer.scene.add_geometry(f"mesh", triangle_mesh, mat_record)


  renderer.scene.scene.set_sun_light(SUNLIGHT_DIRECTION,
                                     SUNLIGHT_COLOR,
                                     SUNLIGHT_INTENSITY)
  renderer.scene.scene.enable_sun_light(True)
  renderer.scene.show_axes(False)

  floor_width = glb_size[0]
  floor_height = glb_size[1]
  aspect_ratio = res_x / res_y

  if floor_width / floor_height > aspect_ratio:
    right = floor_width
    top = (floor_width) / aspect_ratio
  else:
    right = (floor_height) * aspect_ratio
    top = floor_height

  renderer.scene.camera.look_at(
    [0.0, 0.0, 0.0],
    [0.0, 0.0, glb_size.max()],
    [0.0, 1.0, 0.0]
  )

  renderer.scene.camera.set_projection(renderer.scene.camera.Projection.Ortho,
                                       0.0, right, 0.0, top, 0.0, glb_size.max()*2)
  # We use the vertical resolution as the base for all computations
  pixels_per_meter = res_y / top
  img = renderer.render_to_image()
  return img, pixels_per_meter

def getMeshSize(mesh):
  """! Returns the mesh size as [width, height, depth].
  @param  mesh               Triangle mesh geometry.

  @return size               dimensions.
  """
  size = (mesh.get_axis_aligned_bounding_box().get_extent()).numpy()
  return size

def generateOrthoView(scene_obj, glb_file):
  """! generates the orthographic perspective of 3d glb.
  @param  scene_obj          Scene object.
  @param  glb_file           path to glb file.

  @return img                captured image as numpy array.
  @return pixels_per_meter   determined pixels per meter.
  """
  rotation_vector = np.float64([scene_obj.rotation_x,
                                scene_obj.rotation_y,
                                scene_obj.rotation_z])
  triangle_mesh, tensor_mesh = extractMeshFromGLB(glb_file, rotation_vector)
  triangle_mesh.translate((scene_obj.translation_x, scene_obj.translation_y, 0.0))

  glb_size = getMeshSize(triangle_mesh)
  img, pixels_per_meter = renderTopView(triangle_mesh,
                                        tensor_mesh,
                                        glb_size,
                                        THUMBNAIL_RESOLUTION['x'],
                                        THUMBNAIL_RESOLUTION['y'])
  return np.array(img), pixels_per_meter
