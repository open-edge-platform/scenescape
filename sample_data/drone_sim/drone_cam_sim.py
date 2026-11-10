# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Simulated drone camera built from a fixed Scenescape camera recording.

Warping a fixed camera's video cannot create parallax, so the geometrically
consistent simulation is a drone hovering at the original camera's optical
center with a sweeping gimbal (yaw/pitch/roll) and a varying zoom. Each frame
is warped with the homography

  H(t) = K'(t) @ R(t).T @ K0^-1

where K0 is the original intrinsic matrix, K'(t) the virtual (zoomed)
intrinsics, and R(t) the gimbal rotation of the virtual camera relative to the
original camera, expressed in the OpenCV optical frame (x right, y down,
z forward).

The same R(t) and K'(t) drive the external_source `pose` and
`cameras[*].intrinsics` published to Scenescape, so pixel detections in the
warped view localize to stable scene positions while the camera view moves.
Contract reference:
docs/user-guide/microservices/controller/data_formats.md
(External Source Input Message Format, Drone Coordinate and Camera Contract).

This module depends only on numpy and cv2 so it can run both on the host and
inside the DL Streamer Pipeline Server container.
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np

# Optical (x right, y down, z forward) to body (x forward, y left, z up) for a
# forward-looking camera: z_opt -> x_body, x_opt -> -y_body, y_opt -> -z_body.
# Columns are the optical axes expressed in the body frame.
MOUNT_ROTATION = np.array([
  [0.0, 0.0, 1.0],
  [-1.0, 0.0, 0.0],
  [0.0, -1.0, 0.0],
])


def rotation_x(angle_rad: float) -> np.ndarray:
  """Rotation matrix about the x axis."""
  c, s = math.cos(angle_rad), math.sin(angle_rad)
  return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rotation_y(angle_rad: float) -> np.ndarray:
  """Rotation matrix about the y axis."""
  c, s = math.cos(angle_rad), math.sin(angle_rad)
  return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rotation_z(angle_rad: float) -> np.ndarray:
  """Rotation matrix about the z axis."""
  c, s = math.cos(angle_rad), math.sin(angle_rad)
  return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def euler_xyz_to_matrix(angles_deg) -> np.ndarray:
  """Intrinsic XYZ Euler angles in degrees to a rotation matrix.

  Matches scipy's Rotation.from_euler('XYZ', angles, degrees=True), the
  convention Scenescape uses for camera poses (scene_common.transform).
  """
  a, b, c = (math.radians(v) for v in angles_deg)
  return rotation_x(a) @ rotation_y(b) @ rotation_z(c)


def matrix_to_quaternion(rmat: np.ndarray) -> list:
  """Rotation matrix to a unit quaternion in (x, y, z, w) order."""
  m = np.asarray(rmat, dtype=float)
  trace = m[0, 0] + m[1, 1] + m[2, 2]
  if trace > 0.0:
    s = math.sqrt(trace + 1.0) * 2.0
    quat = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
            (m[1, 0] - m[0, 1]) / s, 0.25 * s]
  elif m[0, 0] >= m[1, 1] and m[0, 0] >= m[2, 2]:
    s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
    quat = [0.25 * s, (m[0, 1] + m[1, 0]) / s,
            (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
  elif m[1, 1] >= m[2, 2]:
    s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
    quat = [(m[0, 1] + m[1, 0]) / s, 0.25 * s,
            (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
  else:
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
    quat = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s,
            0.25 * s, (m[1, 0] - m[0, 1]) / s]
  norm = math.sqrt(sum(v * v for v in quat))
  return [v / norm for v in quat]


def intrinsic_matrix(intrinsics: dict) -> np.ndarray:
  """Build a 3x3 camera matrix from an fx/fy/cx/cy dictionary."""
  return np.array([
    [intrinsics["fx"], 0.0, intrinsics["cx"]],
    [0.0, intrinsics["fy"], intrinsics["cy"]],
    [0.0, 0.0, 1.0],
  ])


class DroneCamSimulator:
  """Deterministic flight profile, frame warp, and matching external pose.

  All time-dependent quantities are pure functions of the frame timestamp in
  seconds, so any consumer (warp element, publisher) derives identical
  geometry for the same instant.
  """

  def __init__(self, config: dict):
    base = config["base_camera"]
    self.camera_id = base["id"]
    self.source_id = config["source_id"]
    self.base_intrinsics = dict(base["intrinsics"])
    self.resolution = tuple(base["resolution"])
    self.k0 = intrinsic_matrix(self.base_intrinsics)
    self.k0_inv = np.linalg.inv(self.k0)
    self.r0 = euler_xyz_to_matrix(base["rotation_euler_xyz_deg"])
    self.t0 = np.array(base["translation"], dtype=float)
    flight = config["flight"]
    self.period_s = float(flight["period_s"])
    self.yaw_amp = math.radians(flight["yaw_amplitude_deg"])
    self.pitch_amp = math.radians(flight["pitch_amplitude_deg"])
    self.roll_amp = math.radians(flight["roll_amplitude_deg"])
    self.zoom_min = float(flight["zoom_min"])
    self.zoom_max = float(flight["zoom_max"])

  @classmethod
  def from_config_file(cls, path) -> "DroneCamSimulator":
    """Create a simulator from a JSON configuration file."""
    with open(Path(path), encoding="utf-8") as fd:
      return cls(json.load(fd))

  def state(self, time_s: float) -> dict:
    """Gimbal angles (radians) and zoom factor at a given time."""
    phase = 2.0 * math.pi * (time_s % self.period_s) / self.period_s
    zoom_mid = 0.5 * (self.zoom_min + self.zoom_max)
    zoom_amp = 0.5 * (self.zoom_max - self.zoom_min)
    return {
      "yaw": self.yaw_amp * math.sin(phase),
      "pitch": self.pitch_amp * math.sin(2.0 * phase + 0.7),
      "roll": self.roll_amp * math.sin(3.0 * phase + 1.3),
      "zoom": zoom_mid + zoom_amp * math.sin(phase + 2.1),
    }

  def gimbal_rotation(self, time_s: float) -> np.ndarray:
    """Virtual-camera orientation relative to the base camera (optical frame).

    Yaw pans about the optical y (down) axis, pitch tilts about optical x,
    roll spins about the optical z (forward) axis.
    """
    s = self.state(time_s)
    return rotation_y(s["yaw"]) @ rotation_x(s["pitch"]) @ rotation_z(s["roll"])

  def virtual_intrinsics(self, time_s: float) -> dict:
    """Intrinsics of the zoomed virtual camera at a given time."""
    zoom = self.state(time_s)["zoom"]
    return {
      "fx": self.base_intrinsics["fx"] * zoom,
      "fy": self.base_intrinsics["fy"] * zoom,
      "cx": self.base_intrinsics["cx"],
      "cy": self.base_intrinsics["cy"],
    }

  def homography(self, time_s: float) -> np.ndarray:
    """Homography mapping base-image pixels to virtual-view pixels."""
    k1 = intrinsic_matrix(self.virtual_intrinsics(time_s))
    return k1 @ self.gimbal_rotation(time_s).T @ self.k0_inv

  def warp_frame(self, frame: np.ndarray, time_s: float) -> np.ndarray:
    """Warp one base-camera frame into the simulated drone view."""
    return cv2.warpPerspective(
      frame, self.homography(time_s), self.resolution, flags=cv2.INTER_LINEAR)

  def camera_rotation_in_scene(self, time_s: float) -> np.ndarray:
    """Scene-from-optical rotation of the virtual camera."""
    return self.r0 @ self.gimbal_rotation(time_s)

  def body_pose(self, time_s: float) -> dict:
    """external_source scene-frame pose of the drone body origin.

    The body origin coincides with the camera optical center; the fixed mount
    (see camera_mount) makes T_scene_camera = T_scene_body @ T_body_camera
    reproduce camera_rotation_in_scene exactly.
    """
    r_scene_body = self.camera_rotation_in_scene(time_s) @ MOUNT_ROTATION.T
    return {
      "reference_frame": "scene",
      "translation": self.t0.tolist(),
      "rotation": matrix_to_quaternion(r_scene_body),
    }

  def camera_mount(self) -> dict:
    """Fixed optical-to-body mount for the external_source camera entry."""
    return {
      "translation": [0.0, 0.0, 0.0],
      "rotation": matrix_to_quaternion(MOUNT_ROTATION),
    }

