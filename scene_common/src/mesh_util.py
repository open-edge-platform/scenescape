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

def getMeshAxisAlignedProjectionToXY(mesh):
  """! Extract the projection of a mesh to Z=0 plane.
  @param mesh: Open3D triangle mesh
  @return: list of the projection corners in Z=0 plane, starting from (min_x, min_y, 0) along x-axis.
  """
  if not isinstance(mesh, o3d.t.geometry.TriangleMesh):
    raise TypeError("Input must be an Open3D TriangleMesh.")

  # Assume 'mesh' is your TriangleMesh object
  bbox = mesh.get_axis_aligned_bounding_box()
  # Get min and max bounds
  min_bound = bbox.min_bound.numpy()  # numpy array [min_x, min_y, min_z]
  max_bound = bbox.max_bound.numpy()  # numpy array [max_x, max_y, max_z]
  corners = np.array([ [min_bound[0], min_bound[1], 0.0],
              [max_bound[0], min_bound[1], 0.0],
              [max_bound[0], max_bound[1], 0.0],
              [min_bound[0], max_bound[1], 0.0] ])
  return corners

def createRegionMesh(region):
  """
  Create an extruded polygon mesh from region of interest polygon vertices
  """
  import mapbox_earcut as earcut
  roi_pts = createBasePolygon(region.points, region.buffer_size)
  # Create base polygon points
  base_pts = np.array(roi_pts)
  n_points = len(base_pts)

  # 1. Triangulate the 2D polygon using Ear Clipping 👂
  # This algorithm correctly handles concave shapes by "clipping" triangular "ears".
  # The result is a list of vertex indices.
  triangle_indices = earcut.triangulate_float32(base_pts, np.array([n_points]))

  # Reshape the flat list of indices into a (n, 3) array of triangles.
  triangles = np.array(triangle_indices).reshape(-1, 3)

  # 2. Create vertices for the 3D mesh 🧊
  # Bottom vertices (z=0)
  bottom_vertices = np.hstack([base_pts, np.zeros((base_pts.shape[0], 1))])
  # Top vertices (z=height)
  top_vertices = np.hstack([base_pts, np.full((base_pts.shape[0], 1), region.height)])

  # Combine all vertices.
  vertices = np.vstack([bottom_vertices, top_vertices])

  # 3. Create triangular faces for the 3D mesh ✅
  num_vertices_2d = base_pts.shape[0]

  # Faces for the bottom and top caps come from our ear clipping result.
  bottom_triangles = triangles
  top_triangles = triangles + num_vertices_2d

  # Faces for the sides connect corresponding top and bottom vertices.
  side_triangles = []
  for i in range(num_vertices_2d):
      j = (i + 1) % num_vertices_2d  # Get the next vertex, wrapping around.
      side_triangles.append([i, j, i + num_vertices_2d])
      side_triangles.append([j, j + num_vertices_2d, i + num_vertices_2d])

  # Combine all the triangle sets.
  all_triangles = np.vstack([bottom_triangles, top_triangles, np.array(side_triangles)])

  # 4. Create the Open3D TriangleMesh
  mesh = o3d.geometry.TriangleMesh(
      o3d.utility.Vector3dVector(vertices),
      o3d.utility.Vector3iVector(all_triangles)
  )

  # Compute normals for correct shading and lighting.
  mesh.compute_vertex_normals()
  region.mesh = mesh
  return

def createBasePolygon(points, buffer_size):
  from shapely import geometry
  mitre_inflated = None
  base_polygon = geometry.Polygon([(pt.x, pt.y) for pt in points])
  mitre_inflated = base_polygon.buffer(buffer_size, join_style=2)

  roi_pts = None
# Extract coordinates from inflated polygon
# Handle both simple and complex polygons during inflation
  if mitre_inflated is not None:
  # For complex polygons with holes
    if hasattr(mitre_inflated, 'geom_type') and mitre_inflated.geom_type == 'MultiPolygon':
    # Take the largest polygon from the multipolygon result
      largest_poly = max(mitre_inflated.geoms, key=lambda g: g.area)
      inflated_coords = list(largest_poly.exterior.coords)
      roi_pts = [[x, y] for x, y in inflated_coords]
    elif hasattr(mitre_inflated, 'exterior'):
    # Single polygon result
      inflated_coords = list(mitre_inflated.exterior.coords)
      roi_pts = [[x, y] for x, y in inflated_coords]
  else:
    roi_pts = [[pt.x, pt.y] for pt in points]
  return roi_pts

def isarray(a):
  return isinstance(a, (list, tuple, np.ndarray))

def createObjectMesh(obj):
  from scipy.spatial.transform import Rotation
  if not (hasattr(obj, 'sceneLoc') and hasattr(obj.sceneLoc, 'asNumpyCartesian')):
    raise ValueError("Object must have a valid 'sceneLoc' attribute with 'asNumpyCartesian' method")
  
  if not (hasattr(obj, 'size') and isarray(obj.size) and all(isinstance(s, (int, float)) for s in obj.size)):
    raise ValueError("Object must have a valid 'size' attribute (list or array of numbers)")

  if not (hasattr(obj, 'rotation') and isarray(obj.rotation) and len(obj.rotation) == 4):
    raise ValueError("Object must have a valid 'rotation' attribute (quaternion)")

  # Create a basic box mesh
  mesh = o3d.geometry.TriangleMesh.create_box(
    obj.size[0],
    obj.size[1],
    obj.size[2]
  )

  # Center the box at origin
  mesh = mesh.translate(np.array([
    -obj.size[0]/2.0,
    -obj.size[1]/2.0,
    0
  ]))

  # Rotate the box based on quaternion
  try:
    rotation_matrix = Rotation.from_quat(np.array(obj.rotation)).as_matrix()
    mesh = mesh.rotate(
      rotation_matrix,
      center=np.zeros(3)
    )
  except Exception as e:
    raise ValueError(f"Failed to apply rotation: {e}")

  # Translate to final position
  try:
    mesh = mesh.translate(obj.sceneLoc.asNumpyCartesian)
  except Exception as e:
    raise ValueError(f"Failed to translate mesh to sceneLoc: {e}")
  obj.mesh = mesh.compute_vertex_normals()
  return
