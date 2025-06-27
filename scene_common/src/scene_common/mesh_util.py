# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import math
import numpy as np
import open3d as o3d
import trimesh

MESH_FLATTEN_Z_SCALE = 1000 # This is a calibrated value, used to make mesh look like a flat map.
VECTOR_PROPERTIES = ['base_color', 'emissive_color']
SCALAR_PROPERTIES = ['metallic', 'roughness', 'reflectance']

def materialRecordToMaterial(mat_record):
  mat = o3d.visualization.Material('defaultLit')
  for key in VECTOR_PROPERTIES:
    value = getattr(mat_record, key)
    mat.vector_properties[key] = value

  for key in SCALAR_PROPERTIES:
    if hasattr(mat_record, key):
      value = getattr(mat_record, key)
      mat.scalar_properties[key] = value

  # Convert texture maps
  if mat_record.albedo_img is not None:
    mat.texture_maps['albedo'] = o3d.t.geometry.Image.from_legacy(
        mat_record.albedo_img)
  if mat_record.normal_img is not None:
    mat.texture_maps['normal'] = o3d.t.geometry.Image.from_legacy(
        mat_record.normal_img)
  if mat_record.ao_rough_metal_img is not None:
    mat.texture_maps['ao_rough_metal'] = o3d.t.geometry.Image.from_legacy(
        mat_record.ao_rough_metal_img)
  return mat

def getCumulativeTransform(graph, node_name, visited_nodes):
  transform = trimesh.transformations.identity_matrix()
  current_node = node_name

  if current_node not in visited_nodes:
    if current_node not in graph.nodes:
      raise ValueError(f"Node {current_node} not found in graph.")

    node_data = graph[current_node]
    if not isinstance(node_data, tuple) or len(node_data) != 2:
      raise ValueError(f"Node data for {current_node} is invalid: {node_data}")

    matrix, parent = node_data
    transform = matrix @ transform
    visited_nodes.add(current_node)
    current_node = parent

  return transform

def getAlbedoTexture(mesh):
  albedo_texture = None
  if 'materials' in mesh.metadata:
    for material in mesh.metadata['materials']:
      if 'baseColorTexture' in material:
        albedo_texture = material['baseColorTexture']
        break
  return albedo_texture

def mergeMesh(glb_file):
  scene = trimesh.load(glb_file)
  # Create a list to store transformed meshes
  transformed_meshes = []
  visited_nodes = set()

  # Apply transformations and collect meshes
  for geometry_name, mesh in scene.geometry.items():
    for node_name in scene.graph.nodes:
      node_data = scene.graph[node_name]
      if not isinstance(node_data, tuple) or len(node_data) != 2:
        continue

      for item in scene.graph.nodes_geometry:
        if item == node_name:
          if node_name == scene.graph.geometry_nodes[geometry_name][0]:
            transform = getCumulativeTransform(scene.graph, node_name, visited_nodes)
            transformed_mesh = mesh.copy()
            transformed_mesh.apply_transform(transform)

            if hasattr(transformed_mesh.visual, "uv") and transformed_mesh.visual.uv is not None:
              transformed_mesh.visual.uv = transformed_mesh.visual.uv.copy()

            if 'materials' in mesh.metadata:
              transformed_mesh.metadata['materials'] = mesh.metadata['materials']

            albedo_texture = getAlbedoTexture(mesh)
            if albedo_texture:
              transformed_mesh.metadata['albedo_texture'] = albedo_texture
            transformed_meshes.append(transformed_mesh)

  merged_mesh = trimesh.util.concatenate(transformed_meshes)
  merged_mesh.fix_normals()
  merged_mesh.metadata['name'] = 'mesh_0'
  return merged_mesh

def getTensorMeshesFromModel(model):
  tensor_tmeshes = []
  for m in model.meshes:
    t_mesh = o3d.t.geometry.TriangleMesh.from_legacy(m.mesh)
    t_mesh.material = materialRecordToMaterial(model.materials[m.material_idx])
    tensor_tmeshes.append(t_mesh)
  return tensor_tmeshes

def extractMeshFromGLB(glb_file, rotation=None):
  """! Generate a triangular mesh from the .glb transformed with rotation
  @param  glb_file  GLB file path
  @param  rotation  rotation in degrees

  @return
  """
  if (not os.path.isfile(glb_file)
      or glb_file.split('/')[-1].split('.')[-1] != "glb"):
    raise FileNotFoundError("Glb file not found.")

  mesh = o3d.io.read_triangle_model(glb_file)
  if len(mesh.meshes) == 0:
    raise ValueError("Loaded mesh is empty or invalid.")

  if len(mesh.meshes) > 1:
    merged_mesh = mergeMesh(glb_file)
    merged_mesh.export(glb_file)
    mesh =  o3d.io.read_triangle_model(glb_file)

  tensor_mesh = getTensorMeshesFromModel(mesh)

  triangle_mesh = o3d.t.geometry.TriangleMesh.from_legacy(
                                              mesh.meshes[0].mesh)
  # reorient the model so z is up (this will need to be adjusted for different models)
  if rotation is not None:
    m_rot = o3d.geometry.get_rotation_matrix_from_xyz(np.float64([math.radians(rot) for rot in rotation]))
    triangle_mesh.rotate(m_rot, np.array([0, 0, 0]))

  triangle_mesh.material.material_name = mesh.materials[0].shader
  return triangle_mesh, tensor_mesh

def extractMeshFromImage(map_info):
  """! Generate a triangular mesh from Image of the scene.

  @return
  """
  map_image_path = map_info[0]
  scale = map_info[1]
  map_image = o3d.t.io.read_image(map_image_path)
  map_resx = map_image.columns
  map_resy = map_image.rows
  xdim = map_resx / scale
  ydim = map_resy / scale
  zdim = min(xdim, ydim) / MESH_FLATTEN_Z_SCALE
  triangle_mesh = o3d.geometry.TriangleMesh.create_box(xdim,
                                                       ydim,
                                                       zdim,
                                                       create_uv_map=True,
                                                       map_texture_to_each_face=True)
  triangle_mesh.compute_triangle_normals()
  # Adjust position (not needed if cropping fixed).
  triangle_mesh.translate((0, 0, -zdim))
  # Apply texture map.
  triangle_mesh = o3d.t.geometry.TriangleMesh.from_legacy(triangle_mesh)
  triangle_mesh.material.material_name = "defaultLit"
  triangle_mesh.material.texture_maps['albedo'] = map_image
  return triangle_mesh


def extractTriangleMesh(map_info, rotation=None):
  """Generate a triangular mesh from the .glb or Image file and scale
     of the scene.
  """
  if len(map_info) == 1:
    return extractMeshFromGLB(map_info[0], rotation)
  return extractMeshFromImage(map_info), None
