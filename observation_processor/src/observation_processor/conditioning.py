# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Frame projection and assembly of the v1 tracker measurement contract."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import frustum_gaussian as fg
import numpy as np

from observation_processor.grpc_api import observation_processor_pb2 as pb
from observation_processor.scene_provider import (
  CameraInfo, CameraNotCalibratedError, SceneMeshMissingError, SceneProvider,
)

if TYPE_CHECKING:
  from observation_conditioning import AmodalReasoner

PRIOR_KEYS = ("mu_x", "mu_y", "mu_z", "sigma_x", "sigma_y", "sigma_z")
MIN_DEPTH_VARIANCE = 1e-4
MESH_FOOT_VARIANCE = 0.05 ** 2
UNOBSERVABLE_SIGMA = 1e8
DEFAULT_MAX_DETECTIONS = 512


class InvalidRequestError(ValueError):
  """The frame does not satisfy the published request contract."""


def max_detections() -> int:
  """Maximum detections accepted in one ProcessDetections request."""
  raw = os.getenv("OBSERVATION_PROCESSOR_MAX_DETECTIONS")
  if raw is None or not raw.strip():
    return DEFAULT_MAX_DETECTIONS
  try:
    value = int(raw)
  except ValueError as exc:
    raise ValueError("OBSERVATION_PROCESSOR_MAX_DETECTIONS must be an integer") from exc
  if value <= 0:
    raise ValueError("OBSERVATION_PROCESSOR_MAX_DETECTIONS must be positive")
  return value


@dataclass
class DetectionBatch:
  """Parallel arrays passed to the projection kernels in request order."""

  boxes: np.ndarray
  feet: np.ndarray
  priors: np.ndarray
  axis_aware: np.ndarray
  project_to_map: np.ndarray
  clipped: np.ndarray


def validate_request(request: pb.ProcessDetectionsRequest) -> None:
  """Validate the entire frame before resolving configuration or computing."""
  if not request.scene_id.strip() or not request.camera_id.strip():
    raise InvalidRequestError("scene_id and camera_id are required")
  if not request.HasField("timestamp"):
    raise InvalidRequestError("timestamp is required")
  timestamp = request.timestamp
  if not -62135596800 <= timestamp.seconds <= 253402300799 \
      or not 0 <= timestamp.nanos < 1000000000:
    raise InvalidRequestError("timestamp is outside the protobuf Timestamp range")
  if request.mode not in (pb.CONDITIONING_MODE_AUTO, pb.CONDITIONING_MODE_FULL,
                          pb.CONDITIONING_MODE_FRUSTUM_ONLY):
    raise InvalidRequestError("unknown conditioning mode")
  limit = max_detections()
  if len(request.detections) > limit:
    raise InvalidRequestError(
      f"at most {limit} detections are allowed per request")
  for index, detection in enumerate(request.detections):
    _validate_detection(detection, index)


def _validate_detection(detection: pb.CameraDetection, index: int) -> None:
  if not detection.category.strip() or not detection.HasField("bounding_box_px"):
    raise InvalidRequestError(f"detection {index}: category and bounding_box_px are required")
  box = detection.bounding_box_px
  values = np.array([box.x, box.y, box.width, box.height,
                     box.x + box.width, box.y + box.height], dtype=np.float64)
  if not np.all(np.isfinite(values)) or np.any(values < 0):
    raise InvalidRequestError(f"detection {index}: box values must be finite and nonnegative")
  if np.any(values > np.finfo(np.float32).max):
    raise InvalidRequestError(f"detection {index}: box exceeds the projection kernel range")


def _undistort(points: np.ndarray, camera: CameraInfo, coefficients: np.ndarray) -> np.ndarray:
  if not np.any(coefficients):
    return points.copy()
  result = cv2.undistortPointsIter(
    points.reshape(-1, 1, 2), camera.k_matrix, coefficients, None, camera.k_matrix,
    (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-10),
  ).reshape(points.shape)
  if not np.all(np.isfinite(result)):
    raise CameraNotCalibratedError("undistortion produced non-finite pixels")
  return result


def _clip_masks(boxes: np.ndarray, camera: CameraInfo) -> np.ndarray:
  return ((boxes[:, 0] < 3).astype(np.uint8) * fg.EDGE_LEFT
          | (boxes[:, 2] > camera.width - 3).astype(np.uint8) * fg.EDGE_RIGHT
          | (boxes[:, 1] < 3).astype(np.uint8) * fg.EDGE_TOP
          | (boxes[:, 3] > camera.height - 3).astype(np.uint8) * fg.EDGE_BOTTOM)


def prepare_batch(request: pb.ProcessDetectionsRequest, provider: SceneProvider,
                  camera: CameraInfo, coefficients: np.ndarray) -> DetectionBatch:
  """Resolve per-category priors and rectify raw box corners and foot pixels."""
  boxes, priors, axis_aware, project_to_map = [], [], [], []
  for detection in request.detections:
    box = detection.bounding_box_px
    boxes.append([box.x, box.y, box.x + box.width, box.y + box.height])
    asset = provider.get_asset_prior(detection.category)
    priors.append([asset.prior[key] for key in PRIOR_KEYS])
    axis_aware.append(detection.axis_aware_sizing if detection.HasField("axis_aware_sizing")
                      else False)
    project_to_map.append(detection.project_to_map if detection.HasField("project_to_map")
                          else asset.project_to_map)
  raw = np.asarray(boxes, dtype=np.float64)
  prior_array = np.asarray(priors, dtype=np.float64)
  if not np.all(np.isfinite(prior_array)) or np.any(prior_array[:, :3] <= 0) \
      or np.any(prior_array[:, 3:] < 0):
    raise ValueError("asset size prior is invalid")
  corners = raw[:, [0, 1, 2, 1, 2, 3, 0, 3]].reshape(-1, 4, 2)
  corrected = _undistort(corners, camera, coefficients)
  rectified = np.concatenate((corrected.min(axis=1), corrected.max(axis=1)), axis=1)
  feet = np.stack(((raw[:, 0] + raw[:, 2]) / 2, raw[:, 3]), axis=1)
  return DetectionBatch(rectified, _undistort(feet, camera, coefficients),
                        prior_array, np.asarray(axis_aware), np.asarray(project_to_map),
                        _clip_masks(raw, camera))


def project_batch(batch: DetectionBatch, camera: CameraInfo) -> dict[str, np.ndarray]:
  """Run the native frustum kernel and transform its result to the scene frame."""
  intrinsics = np.array([camera.intrinsics[key] for key in ("fx", "fy", "cx", "cy")])
  with np.errstate(over="raise", invalid="raise", divide="raise"):
    observations = fg.project_frustum_batch(
      boxes=batch.boxes, priors=batch.priors, intrinsics=intrinsics,
      img_size=np.array([camera.width, camera.height]), axis_aware=batch.axis_aware,
      clipped=batch.clipped,
    )
    observations = fg.transform_to_world_batch(observations, camera.pose_mat)
  for value in observations.values():
    if not np.all(np.isfinite(value)):
      raise ValueError("frustum projection produced non-finite output")
  return observations


def condition_depths(observations: dict[str, np.ndarray], reasoner: AmodalReasoner | None,
                     full: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
  """Condition only observable detections, keeping unobservable ones out of amodal."""
  depth = observations["depth_est"].astype(np.float64).copy()
  sigma = observations["depth_sigma"].astype(np.float64)
  observable = sigma < UNOBSERVABLE_SIGMA
  measured_depth = depth[observable]
  measured_sigma = sigma[observable]
  if not np.all(np.isfinite(measured_depth)) \
      or not np.all(np.isfinite(measured_sigma)) \
      or np.any(measured_depth < 0) or np.any(measured_sigma < 0):
    raise ValueError("frustum projection produced invalid measurable depth or sigma")
  variance = np.zeros_like(sigma)
  variance[observable] = np.square(measured_sigma)
  if full and np.any(observable):
    if reasoner is None:
      raise SceneMeshMissingError("FULL conditioning requires a prepared reasoner")
    rays = {key: value[observable] for key, value in observations.items() if key != "origin"}
    rays["mu"] = np.broadcast_to(observations["origin"], (observable.sum(), 3)).copy()
    updated_depth, updated_variance = reasoner.generate(rays)
    depth[observable] = updated_depth
    variance[observable] = updated_variance
  measured_depth = depth[observable]
  measured_variance = variance[observable]
  if not np.all(np.isfinite(measured_depth)) or not np.all(np.isfinite(measured_variance)) \
      or np.any(measured_depth < 0) or np.any(measured_variance < 0):
    raise ValueError("conditioning produced invalid depth or variance")
  return depth, variance, observable


def mesh_foot_points(batch: DetectionBatch, camera: CameraInfo, reasoner: AmodalReasoner | None,
                     observable: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
  """Intersect undistorted bottom-centre rays with the preloaded world mesh."""
  count = len(batch.boxes)
  points = np.zeros((count, 3), dtype=np.float64)
  hits = np.zeros(count, dtype=bool)
  selected = batch.project_to_map & observable
  if reasoner is None or not np.any(selected):
    return points, hits
  pixels = np.column_stack((batch.feet[selected], np.ones(selected.sum())))
  rays = pixels @ np.linalg.inv(camera.k_matrix).T @ camera.pose_mat[:3, :3].T
  rays /= np.linalg.norm(rays, axis=1, keepdims=True)
  origin = camera.pose_mat[:3, 3]
  _, distances = reasoner.depth_map.cast_np(rays, origin)
  valid = np.isfinite(distances) & (distances >= 0)
  indices = np.flatnonzero(selected)[valid]
  points[indices] = origin + rays[valid] * distances[valid, None]
  points[indices, 2] += batch.priors[indices, 2] / 2
  hits[indices] = True
  return points, hits


def measurement_covariance(covariance: np.ndarray, ray: np.ndarray,
                           variance: float) -> np.ndarray:
  """Preserve lateral noise while replacing the along-ray variance; guarantee SPD."""
  ray = np.asarray(ray, dtype=np.float64)
  ray /= np.linalg.norm(ray)
  tangent = np.cross(ray, np.eye(3)[np.argmin(np.abs(ray))])
  tangent /= np.linalg.norm(tangent)
  basis = np.column_stack((tangent, np.cross(ray, tangent)))
  lateral = basis.T @ covariance @ basis
  eigenvalues, eigenvectors = np.linalg.eigh((lateral + lateral.T) / 2)
  if np.min(eigenvalues) < -1e-6:
    raise ValueError("frustum covariance is not positive semidefinite")
  lateral = (eigenvectors * np.maximum(eigenvalues, 1e-10)) @ eigenvectors.T
  result = np.eye(7) * 0.2
  result[:3, :3] = basis @ lateral @ basis.T \
      + max(variance, MIN_DEPTH_VARIANCE) * np.outer(ray, ray)
  return result


def _vector(value: np.ndarray) -> pb.Vector3:
  return pb.Vector3(x=float(value[0]), y=float(value[1]), z=float(value[2]))


def _frustum(observations: dict[str, np.ndarray], index: int) -> pb.FrustumGaussian:
  return pb.FrustumGaussian(
    ray_origin=_vector(observations["origin"]), ray=_vector(observations["ray"][index]),
    mean=_vector(observations["mu"][index]),
    covariance=observations["Sigma"][index].reshape(-1).tolist(),
    depth_est=float(observations["depth_est"][index]),
    depth_sigma=float(observations["depth_sigma"][index]),
    depth_lo=float(observations["depth_lo"][index]),
    depth_hi=float(observations["depth_hi"][index]),
    score=float(observations["score"][index]),
    edge_valid_mask=int(observations["edge_valid"][index]),
  )


def assemble_measurements(request: pb.ProcessDetectionsRequest, response: pb.ProcessDetectionsResponse,
                          batch: DetectionBatch, observations: dict[str, np.ndarray],
                          reasoner: AmodalReasoner | None, camera: CameraInfo) -> None:
  """Populate ordered diagnostics and 7D measurements with source-specific noise."""
  full = response.mode == pb.CONDITIONING_MODE_FULL
  depth, variance, observable = condition_depths(observations, reasoner, full)
  foot_points, foot_hits = mesh_foot_points(batch, camera, reasoner, observable)
  for index, detection in enumerate(request.detections):
    entry = response.measurements.add(detection_id=detection.detection_id)
    if request.include_diagnostics:
      entry.frustum.CopyFrom(_frustum(observations, index))
    if not observable[index]:
      entry.status = pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
      continue
    entry.status = pb.MEASUREMENT_STATUS_OK
    entry.depth_source = pb.DEPTH_SOURCE_AMODAL if full else pb.DEPTH_SOURCE_FRUSTUM
    point = observations["origin"] + observations["ray"][index] * depth[index]
    selected_variance = variance[index]
    if full and request.include_diagnostics:
      entry.amodal.CopyFrom(pb.AmodalConditioning(
        depth=float(depth[index]), depth_variance=float(variance[index])))
    if foot_hits[index]:
      point = foot_points[index]
      selected_variance = min(selected_variance, MESH_FOOT_VARIANCE)
      entry.depth_source = pb.DEPTH_SOURCE_MESH_FOOT
    covariance = measurement_covariance(observations["Sigma"][index],
                                        observations["ray"][index], selected_variance)
    entry.measurement.CopyFrom(pb.Measurement(
      mean=[*point.tolist(), *batch.priors[index, :3].tolist(), 0.0],
      noise_covariance=covariance.reshape(-1).tolist(),
      z_measured=True, has_orientation=False,
    ))


def process_detections(request: pb.ProcessDetectionsRequest,
                       provider: SceneProvider) -> pb.ProcessDetectionsResponse:
  """Resolve one configuration snapshot and execute the complete projection pipeline."""
  validate_request(request)
  snapshot = provider.snapshot()
  scene = snapshot.get_scene(request.scene_id)
  camera = snapshot.get_camera(request.scene_id, request.camera_id)
  coefficients = camera.distortion_coefficients
  has_mesh = snapshot.scene_has_mesh(scene)
  mode = request.mode
  if mode == pb.CONDITIONING_MODE_AUTO:
    mode = pb.CONDITIONING_MODE_FULL if has_mesh else pb.CONDITIONING_MODE_FRUSTUM_ONLY
  if mode == pb.CONDITIONING_MODE_FULL and not has_mesh:
    raise SceneMeshMissingError("FULL conditioning requires a GLB scene mesh")
  response = pb.ProcessDetectionsResponse(
    scene_id=request.scene_id, camera_id=request.camera_id, timestamp=request.timestamp, mode=mode)
  if not request.detections:
    return response
  batch = prepare_batch(request, snapshot, camera, coefficients)
  observations = project_batch(batch, camera)
  observations["origin"] = camera.pose_mat[:3, 3].copy()
  reasoner = None
  if has_mesh and (mode == pb.CONDITIONING_MODE_FULL or np.any(batch.project_to_map)):
    reasoner = snapshot.get_reasoner(request.scene_id, request.camera_id)
  assemble_measurements(request, response, batch, observations, reasoner, camera)
  return response
