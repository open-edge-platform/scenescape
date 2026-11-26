# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic scenario corpus for observation_conditioning.

Each scenario is a world-frame mesh, a pinhole camera and a batch of frustum observations
in the dtype mix the Observation Processor passes to the library (float64 camera origin as
`mu`, everything else float32). Scenarios are designed so that between them every branch of
`AmodalReasoner.generate` is reached; `expect` names the decision flags that at least one
object of the scenario must raise (checked against the original MVP, see capture.py).

World frame is Z-up, the camera frame is OpenCV (x right, y down, z forward).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

UP = np.array([0.0, 0.0, 1.0])
REPO_ROOT = Path(__file__).resolve().parents[4]
TERRAIN_DIR = REPO_ROOT / "tests" / "system" / "metric" / "rolling_terrain_dataset"

# Bits of the per-object decision mask, identical to the C++ DecisionFlags (design §5.3).
FLAGS = {
  "FREE_3D": 1 << 0, "OCCLUDED": 1 << 1, "WALL_VERTICAL": 1 << 2, "WALL_SPECTRUM": 1 << 3,
  "TOTAL_OCCLUSION": 1 << 4, "WALL_DROPPED": 1 << 5, "EMPTY_INTERVAL": 1 << 6,
  "UPDATED": 1 << 7,
}


@dataclass
class Scenario:
  name: str
  description: str
  vertices: np.ndarray          # (V, 3) float32, world frame
  indices: np.ndarray           # (T, 3) uint32
  K: np.ndarray                 # (3, 3) or (3, 4) float64
  pose: np.ndarray              # (4, 4) float64 camera -> world
  width: int
  height: int
  observations: dict            # MVP gaus_rays dict
  num_layers: int = 1
  map_stride: int = 2
  expect: tuple = ()
  seed: int = 0
  extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------- geometry helpers

def _unit(v):
  v = np.asarray(v, dtype=np.float64)
  return v / np.linalg.norm(v, axis=-1, keepdims=True)


class MeshBuilder:
  """Accumulates triangles. Every face is oriented so Embree's Ng equals `normal`."""

  def __init__(self):
    self.vertices, self.triangles = [], []

  def _add(self, corners, normal):
    corners = np.asarray(corners, dtype=np.float64)
    base = len(self.vertices)
    self.vertices.extend(corners.tolist())
    quad = [(0, 1, 2), (0, 2, 3)]
    # Embree's Ng is the *negated* CCW normal: flip a triangle whose Ng disagrees.
    ccw = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    flip = np.dot(-ccw, normal) < 0
    for a, b, c in quad:
      self.triangles.append((base + a, base + (c if flip else b), base + (b if flip else c)))

  def quad(self, center, normal, u, half_u, half_v):
    """Rectangle around `center`, spanned by unit `u` and normal x u, facing Ng = normal."""
    normal, u = _unit(normal), _unit(u)
    v = np.cross(normal, u)
    c = np.asarray(center, dtype=np.float64)
    corners = [c - half_u * u - half_v * v, c + half_u * u - half_v * v,
               c + half_u * u + half_v * v, c - half_u * u + half_v * v]
    self._add(corners, normal)

  def box(self, lo, hi, flipped=False):
    """Axis-aligned box. Outward Ng (flipped=True: inward) like a solid or a room."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    c, h = (lo + hi) / 2, (hi - lo) / 2
    sign = -1.0 if flipped else 1.0
    for axis in range(3):
      u_axis, v_axis = [a for a in range(3) if a != axis]
      for s in (-1.0, 1.0):
        normal = np.zeros(3)
        normal[axis] = s * sign
        center = c.copy()
        center[axis] += s * h[axis]
        u = np.zeros(3)
        u[u_axis] = 1.0
        self.quad(center, normal, u, h[u_axis], h[v_axis])

  def floor(self, z=0.0, half=20.0, normal_up=True):
    self.quad([0, 0, z], [0, 0, 1.0 if normal_up else -1.0], [1, 0, 0], half, half)

  def result(self):
    return (np.asarray(self.vertices, dtype=np.float32),
            np.asarray(self.triangles, dtype=np.uint32))


def look_at(eye, target):
  """Camera -> world pose (OpenCV camera axes) looking from `eye` to `target`."""
  eye, target = np.asarray(eye, float), np.asarray(target, float)
  forward = _unit(target - eye)
  right = _unit(np.cross(forward, UP))
  down = np.cross(forward, right)
  pose = np.eye(4)
  pose[:3, :3] = np.column_stack((right, down, forward))
  pose[:3, 3] = eye
  return pose


def pinhole(width, height, focal):
  return np.array([[focal, 0.0, width / 2], [0.0, focal, height / 2], [0.0, 0.0, 1.0]])


def observations(origin, centroids, sigma_d=0.3, sigma_h=0.15, sigma_v=0.45, band=1.0,
                 rotate=None, rng=None):
  """MVP `gaus_rays` for `centroids`: float64 camera-origin `mu`, float32 everything else.

  Sigma is built in the ray frame [r, e_h, e_v] (optionally rotated by a random angle about
  r, so Lambda gets off-diagonal terms); per-object sigmas may be scalars or arrays.
  """
  origin = np.asarray(origin, dtype=np.float64)
  centroids = np.asarray(centroids, dtype=np.float64)
  n = len(centroids)
  rays = centroids - origin
  depth = np.linalg.norm(rays, axis=1)
  r = rays / depth[:, None]
  e_h = np.cross(r, UP)
  e_h = e_h / np.maximum(np.linalg.norm(e_h, axis=1, keepdims=True), 1e-12)
  e_v = np.cross(r, e_h)
  if rotate is not None:
    angle = rng.uniform(0, np.pi, n)
    e_h, e_v = (np.cos(angle)[:, None] * e_h + np.sin(angle)[:, None] * e_v,
                -np.sin(angle)[:, None] * e_h + np.cos(angle)[:, None] * e_v)
  sd, sh, sv = (np.broadcast_to(np.asarray(s, float), (n,)) for s in (sigma_d, sigma_h, sigma_v))
  sigma = (sd[:, None, None] ** 2 * r[:, :, None] * r[:, None, :]
           + sh[:, None, None] ** 2 * e_h[:, :, None] * e_h[:, None, :]
           + sv[:, None, None] ** 2 * e_v[:, :, None] * e_v[:, None, :])
  band = np.broadcast_to(np.asarray(band, float), (n,))
  return {
    "mu": np.tile(origin, (n, 1)),
    "Sigma": sigma.astype(np.float32),
    "ray": r.astype(np.float32),
    "depth_est": depth.astype(np.float32),
    "depth_sigma": sd.astype(np.float32),
    "depth_lo": np.maximum(depth - band, 0.0).astype(np.float32),
    "depth_hi": (depth + band).astype(np.float32),
    "score": np.full(n, 0.8, dtype=np.float32),
    "edge_valid": np.full(n, 15, dtype=np.uint8),
  }


# ---------------------------------------------------------------- scenarios

EYE = np.array([-6.0, 0.0, 4.0])
TARGET = np.array([2.0, 0.0, 0.5])
W, H, FOCAL = 96, 72, 80.0


def _scene(name, description, build, centroids, expect, num_layers=1, k34=False, seed=0,
           eye=EYE, target=TARGET, pose=None, **obs_kwargs):
  mesh = MeshBuilder()
  build(mesh)
  vertices, indices = mesh.result()
  pose = look_at(eye, target) if pose is None else pose
  k = pinhole(W, H, FOCAL)
  if k34:
    k = np.hstack((k, np.zeros((3, 1))))
  obs = observations(pose[:3, 3], centroids, rng=np.random.default_rng(seed), **obs_kwargs)
  return Scenario(name, description, vertices, indices, k, pose, W, H, obs,
                  num_layers=num_layers, expect=tuple(expect), seed=seed)


def _grid(xs, ys, z):
  return np.array([[x, y, z] for x in xs for y in ys], dtype=np.float64)


def _floor_only():
  def build(m):
    m.floor()
  on_floor = _grid([-1.0, 1.0, 3.0, 5.0], [-1.5, 1.5], 0.9)
  floating = np.array([[2.0, 0.0, 3.0], [3.0, 1.0, 4.0]])
  return _scene("floor_only", "flat floor: on-floor objects and floating (FREE_3D) objects",
                build, np.vstack((on_floor, floating)), ["FREE_3D"], seed=1)


def _occluder_box():
  def build(m):
    m.floor()
    m.box([0.5, -2.5, 0.0], [1.5, 2.5, 1.2])
  return _scene("occluder_box", "low box in front of objects: partial occlusion",
                build, _grid([2.5, 3.5, 4.5], [-1.5, 0.0, 1.5], 0.9), ["OCCLUDED"], seed=2)


def _wall_vertical():
  def build(m):
    m.floor()
    m.box([6.0, -8.0, 0.0], [6.2, 8.0, 3.0])
  return _scene("wall_vertical", "wall behind objects, normal reads as vertical",
                build, _grid([4.5, 5.0, 5.5], [-1.5, 0.0, 1.5], 0.9), ["WALL_VERTICAL"], seed=3)


def _wall_flipped():
  def build(m):
    m.floor()
    m.box([6.0, -8.0, 0.0], [6.2, 8.0, 3.0], flipped=True)
  return _scene("wall_flipped", "same wall with inverted winding: signed test fails (I5)",
                build, _grid([4.5, 5.0, 5.5], [-1.5, 0.0, 1.5], 0.9), ["WALL_SPECTRUM"], seed=4)


def _occluder_face():
  def build(m):
    m.floor()
    m.box([2.0, -3.0, 0.0], [2.4, 3.0, 1.4])
  return _scene("occluder_face", "occluder face doubles as wall: wall dropped (eps rule)",
                build, _grid([3.2, 4.0], [-1.5, 0.0, 1.5], 0.9),
                ["OCCLUDED", "WALL_DROPPED"], seed=5)


def _total_occlusion():
  def build(m):
    m.floor()
    m.box([1.0, -6.0, 0.0], [1.2, 6.0, 4.5])
  return _scene("total_occlusion", "tall wall hides objects completely",
                build, _grid([3.0, 4.0, 5.0], [-1.5, 0.0, 1.5], 0.9), ["TOTAL_OCCLUSION"], seed=6)


def _slope_spectrum():
  def build(m):
    m.floor()
    # ramp rising away from the camera; normal tilted 14 degrees from up
    m.quad([5.0, 0.0, 0.9], [-0.25, 0.0, 1.0], [0.0, 1.0, 0.0], 6.0, 6.0)
  return _scene("slope_spectrum", "rising ramp behind objects: spectrum finds rising supports",
                build, _grid([2.0, 3.0, 4.0, 5.0], [-1.5, 0.0, 1.5], 1.3), ["WALL_SPECTRUM"], seed=7)


def _degenerate_up_ray():
  eye = np.array([2.0, 0.0, 6.0])
  pose = np.eye(4)
  pose[:3, :3] = np.column_stack(([1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]))  # looks straight down
  pose[:3, 3] = eye

  def build(m):
    m.floor()
    m.box([2.6, -0.6, 0.0], [3.4, 0.6, 0.7])
  cents = np.array([[2.0, 0.0, 0.9], [2.0, 0.0, 2.5], [2.0000001, 0.0, 1.2],
                    [3.0, 0.0, 0.9], [1.0, 0.5, 0.9], [2.0, -0.4, 1.5]])
  scene = _scene("degenerate_up_ray", "camera straight above: ray parallel to world-up",
                 build, cents, [], seed=8, eye=eye, pose=pose)
  return scene


def _intrinsics_3x4():
  s = _occluder_box()
  scene = _scene("intrinsics_3x4", "occluder_box with a 3x4 K (trailing zero column)",
                 lambda m: (m.floor(), m.box([0.5, -2.5, 0.0], [1.5, 2.5, 1.2])),
                 _grid([2.5, 3.5, 4.5], [-1.5, 0.0, 1.5], 0.9), ["OCCLUDED"], k34=True, seed=2)
  assert np.array_equal(s.indices, scene.indices)
  return scene


def _behind_out_of_frame():
  def build(m):
    m.floor()
  cents = np.array([[-9.0, 0.0, 0.9], [-8.0, 2.0, 1.0],      # behind the camera
                    [3.0, 15.0, 0.9], [3.0, -15.0, 0.9],      # far outside the image
                    [3.0, 4.2, 0.9], [3.0, -4.2, 0.9],        # near the image edge
                    [2.0, 0.0, 0.9]])                          # in frame
  return _scene("behind_out_of_frame", "objects behind the camera and outside the image",
                build, cents, ["FREE_3D"], seed=9)


def _peeled_layers():
  def build(m):
    m.floor()
    m.floor(z=-1.0)
    m.floor(z=-2.0)
    m.box([0.5, -2.5, 0.0], [1.5, 2.5, 1.2])
  return _scene("peeled_layers", "stacked surfaces, 4 depth-peeling layers",
                build, _grid([2.5, 3.5, 4.5], [-1.5, 0.0, 1.5], 0.9), ["OCCLUDED"],
                num_layers=4, seed=11)


def _wall_angle_sweep():
  """Slab normals at signed angles around the 75 and 115 degree band edges."""
  angles = [60.0, 74.99, 74.9999, 75.0001, 75.01, 90.0, 114.99, 114.9999, 115.0001, 115.01, 130.0]
  ys = np.linspace(-4.5, 4.5, len(angles))
  cents = np.array([[4.0, y, 0.9] for y in ys])
  origin = look_at(EYE, TARGET)[:3, 3]

  def build(m):
    m.floor()
    for angle, cent in zip(angles, cents):
      r = _unit(cent - origin)
      e_h = _unit(np.cross(r, UP))
      horizontal = np.cross(e_h, UP)               # e_h x z
      theta = np.radians(angle)
      normal = np.cos(theta) * UP + np.sin(theta) * horizontal
      point = origin + r * (np.linalg.norm(cent - origin) + 0.8)
      u = np.cross(normal, UP) if abs(angle - 0.0) > 1e-9 else e_h
      m.quad(point, normal, _unit(u), 0.42, 0.42)
  return _scene("wall_angle_sweep", "slab normals straddling the 75/115 degree band edges",
                build, cents, ["WALL_VERTICAL"], seed=12, band=1.5)


def _total_occlusion_sweep():
  """Walls whose top edge blocks 5..9 of the 9 column targets."""
  blocked_counts = [4, 5, 6, 7, 8, 9]
  ys = np.linspace(-4.0, 4.0, len(blocked_counts))
  cents = np.array([[4.0, y, 0.9] for y in ys])
  origin = look_at(EYE, TARGET)[:3, 3]
  sigma_v, wall_x = 0.45, 1.5

  def build(m):
    m.floor()
    for count, cent in zip(blocked_counts, cents):
      r = _unit(cent - origin)
      e_h = _unit(np.cross(r, UP))
      e_v = np.cross(r, e_h)
      e_v = e_v if e_v @ UP > 0 else -e_v
      lo, top = cent - 2 * sigma_v * e_v, cent + 2 * sigma_v * e_v
      targets = [lo + (top - lo) * s for s in np.linspace(0, 1, 9)]
      heights = [origin[2] + (t[2] - origin[2]) * (wall_x - origin[0]) / (t[0] - origin[0])
                 for t in targets]
      wall_top = heights[-1] + 1.0 if count == 9 else 0.5 * (heights[count - 1] + heights[count])
      cross_y = origin[1] + (cent[1] - origin[1]) * (wall_x - origin[0]) / (cent[0] - origin[0])
      m.box([wall_x, cross_y - 0.5, 0.0], [wall_x + 0.1, cross_y + 0.5, wall_top])
  return _scene("total_occlusion_sweep", "wall tops that block 4..9 of 9 column targets",
                build, cents, ["TOTAL_OCCLUSION"], seed=13, sigma_v=sigma_v)


def _random_fuzz():
  rng = np.random.default_rng(14)
  n = 384

  def build(m):
    m.floor()
    m.box([0.5, -2.5, 0.0], [1.5, 2.5, 1.2])
    m.box([6.0, -8.0, 0.0], [6.2, 8.0, 3.0])
    m.box([3.0, 3.0, 0.0], [4.0, 4.5, 2.0])
    m.quad([4.0, -3.5, 0.7], [-0.3, 0.0, 1.0], [0, 1.0, 0], 1.5, 1.5)
  cents = np.column_stack((rng.uniform(-1.0, 7.5, n), rng.uniform(-5.0, 5.0, n),
                           np.where(rng.random(n) < 0.15, rng.uniform(2.5, 5.0, n),
                                    rng.uniform(0.3, 2.2, n))))
  return _scene("random_fuzz", "seeded random observations over a mixed scene", build, cents,
                ["FREE_3D", "OCCLUDED", "WALL_VERTICAL", "TOTAL_OCCLUSION"], seed=14,
                sigma_d=rng.uniform(0.1, 0.8, n), sigma_h=rng.uniform(0.03, 0.2, n),
                sigma_v=rng.uniform(0.03, 0.25, n), band=rng.uniform(0.3, 2.0, n),
                rotate=True)


# ---------------------------------------------------------------- terrain (real GLB)

def _pose_from_extrinsics(translation, rotation):
  from scipy.spatial.transform import Rotation
  pose = np.eye(4)
  pose[:3, :3] = Rotation.from_euler("XYZ", rotation, degrees=True).as_matrix()
  pose[:3, 3] = translation
  return pose


def _terrain(camera_name, frame_step=5):
  """Rolling-terrain dataset: real scene.glb and real detections through frustum_gaussian."""
  import open3d as o3d
  import frustum_gaussian as fg

  config = json.loads((TERRAIN_DIR / "scene_config.json").read_text())
  sensor = config["sensors"][camera_name]
  fx, fy, cx, cy = sensor["intrinsics"]
  width, height = int(sensor["width"]), int(sensor["height"])
  pose = _pose_from_extrinsics(sensor["extrinsics"]["translation"],
                               sensor["extrinsics"]["rotation"])
  legacy = o3d.io.read_triangle_mesh(str(TERRAIN_DIR / config["map"]))
  vertices = np.asarray(legacy.vertices).astype(np.float32)   # service: from_legacy -> float32
  indices = np.asarray(legacy.triangles).astype(np.uint32)

  boxes = []
  for index, line in enumerate((TERRAIN_DIR / f"{camera_name}.json").read_text().splitlines()):
    if index % frame_step or not line.strip():
      continue
    for person in json.loads(line)["objects"].get("person", []):
      b = person["bounding_box_px"]
      boxes.append([b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]])
  boxes = np.asarray(boxes, dtype=np.float64)
  priors = np.tile([fg.PERSON_SHAPE_PRIOR[k] for k in
                    ("mu_x", "mu_y", "mu_z", "sigma_x", "sigma_y", "sigma_z")], (len(boxes), 1))
  projected = fg.project_frustum_batch(
    boxes=boxes, priors=priors, intrinsics=np.array([fx, fy, cx, cy]),
    img_size=np.array([width, height]))
  world = fg.transform_to_world_batch(projected, pose)
  world = dict(world)
  world["mu"] = np.tile(pose[:3, 3], (len(boxes), 1))          # service: camera origin
  keep = world["depth_sigma"] < 1e8                             # service: only observable
  world = {k: np.ascontiguousarray(v[keep]) for k, v in world.items()}
  k = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
  return Scenario(f"terrain_{camera_name}", f"rolling-terrain GLB, {camera_name} detections",
                  vertices, indices, k, pose, width, height, world, map_stride=8,
                  expect=("UPDATED",), seed=15, extra={"mesh_id": "terrain"})


def build_corpus(include_terrain=True):
  builders = [_floor_only, _occluder_box, _wall_vertical, _wall_flipped, _occluder_face,
              _total_occlusion, _slope_spectrum, _degenerate_up_ray, _intrinsics_3x4,
              _behind_out_of_frame, _peeled_layers, _wall_angle_sweep, _total_occlusion_sweep,
              _random_fuzz]
  corpus = {s.name: s for s in (b() for b in builders)}
  if include_terrain:
    for camera in ("cam_front_left", "cam_back_right"):
      scenario = _terrain(camera)
      corpus[scenario.name] = scenario
  return corpus


def sample_queries(scenario, count=256):
  """Seeded world points and rays for DepthMap.query / cast_np (hits, misses, behind)."""
  rng = np.random.default_rng(1000 + scenario.seed)
  verts = scenario.vertices.astype(np.float64)
  lo, hi = np.percentile(verts, 2, axis=0), np.percentile(verts, 98, axis=0)
  origin = scenario.pose[:3, 3]
  points = np.vstack((
    rng.uniform(lo, hi, (count // 2, 3)),
    origin + rng.normal(0, 8.0, (count // 4, 3)),
    scenario.observations["mu"][:1] + scenario.observations["ray"][:1].astype(np.float64)
    * rng.uniform(0.5, 30.0, (count // 4, 1)),
  ))
  dirs = _unit(rng.normal(size=(count, 3)) + np.array([0.0, 0.0, -0.4]))
  origins = rng.uniform(lo, hi, (count, 3))
  return points.astype(np.float64), origins.astype(np.float32), dirs.astype(np.float32)
