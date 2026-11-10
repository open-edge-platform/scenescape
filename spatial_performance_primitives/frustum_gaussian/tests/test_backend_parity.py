# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The native batch implementation should agree with the NumPy reference."""

import numpy as np
import pytest

import frustum_gaussian as fg
from frustum_gaussian._pure import project_frustum_batch_numpy


def _projection_inputs():
  boxes = np.array([
    [120.0, 100.0, 260.0, 310.0],
    [0.0, 80.0, 100.0, 270.0],
    [210.0, 140.0, 340.0, 290.0],
  ], dtype=np.float32)
  priors = np.array([
    [0.55, 0.55, 1.70, 0.10, 0.10, 0.15],
    [2.00, 4.50, 1.50, 0.20, 0.50, 0.20],
    [0.30, 0.30, 0.20, 0.05, 0.05, 0.03],
  ], dtype=np.float32)
  intrinsics = np.array([500.0, 510.0, 200.0, 200.0], dtype=np.float32)
  img_size = np.array([400.0, 400.0], dtype=np.float32)
  clipped = np.array([fg.EDGE_ALL, fg.EDGE_LEFT, fg.EDGE_ALL], dtype=np.uint8)
  axis_aware = np.array([True, False, True], dtype=np.uint8)
  return boxes, priors, intrinsics, img_size, clipped, axis_aware


def _assert_matches_numpy(candidate, reference):
  assert candidate.keys() == reference.keys()
  for key in reference:
    if key == "edge_valid":
      np.testing.assert_array_equal(candidate[key], reference[key])
    else:
      np.testing.assert_allclose(candidate[key], reference[key], rtol=1e-3, atol=2e-5)


def _numpy_projection(boxes, priors, intrinsics, img_size, clipped, axis_aware):
  return project_frustum_batch_numpy(
    boxes=boxes, priors=priors, intrinsics=intrinsics, img_size=img_size,
    clipped=clipped, axis_aware=axis_aware,
  )


def test_native_extension_matches_numpy_reference():
  if fg._cpp is None:
    pytest.skip("frustum_gaussian native extension is not built")
  boxes, priors, intrinsics, img_size, clipped, axis_aware = _projection_inputs()
  reference = _numpy_projection(boxes, priors, intrinsics, img_size, clipped, axis_aware)
  candidate = fg._cpp.project_frustum_batch(
    {"boxes": boxes, "priors": priors, "clipped": clipped,
     "axis_aware": axis_aware},
    intrinsics, img_size, sigma_px=2.0, sensor=None,
  )
  _assert_matches_numpy(candidate, reference)


def test_numpy_centered_box_produces_finite_positive_semidefinite_observation():
  result = project_frustum_batch_numpy(
    boxes=np.array([[150.0, 100.0, 250.0, 300.0]], dtype=np.float32),
    intrinsics=np.array([500.0, 500.0, 200.0, 200.0], dtype=np.float32),
    img_size=np.array([400.0, 400.0], dtype=np.float32),
    priors=np.array([[0.55, 0.55, 1.70, 0.10, 0.10, 0.15]], dtype=np.float32),
  )
  covariance = result["Sigma"][0]

  np.testing.assert_allclose(result["ray"][0], [0.0, 0.0, 1.0], atol=1e-6)
  np.testing.assert_allclose(result["mu"][0], [0.0, 0.0, result["depth_est"][0]])
  assert np.isfinite(result["depth_est"][0])
  assert result["depth_est"][0] > 0.0
  assert result["edge_valid"][0] == fg.EDGE_ALL
  np.testing.assert_allclose(covariance, covariance.T, atol=1e-6)
  assert np.linalg.eigvalsh(covariance).min() >= -1e-5


def test_numpy_orientation_averaged_prior_changes_depth_estimate():
  boxes = np.array([[120.0, 100.0, 280.0, 300.0]], dtype=np.float32)
  priors = np.array([[4.0, 0.5, 0.5, 0.1, 0.1, 0.1]], dtype=np.float32)
  intrinsics = np.array([500.0, 500.0, 200.0, 200.0], dtype=np.float32)
  img_size = np.array([400.0, 400.0], dtype=np.float32)

  axis_aware = project_frustum_batch_numpy(
    boxes, intrinsics, img_size, priors, axis_aware=True,
  )
  orientation_averaged = project_frustum_batch_numpy(
    boxes, intrinsics, img_size, priors, axis_aware=False,
  )

  assert np.isfinite(axis_aware["depth_est"][0])
  assert np.isfinite(orientation_averaged["depth_est"][0])
  assert abs(axis_aware["depth_est"][0] - orientation_averaged["depth_est"][0]) > 0.1


def test_dictionary_and_keyword_inputs_match_numpy(monkeypatch):
  monkeypatch.setattr(fg, "_cpp", None)
  boxes, priors, intrinsics, img_size, clipped, axis_aware = _projection_inputs()
  boxes = boxes.astype(np.float64)
  priors = priors.astype(np.float64)
  intrinsics = intrinsics.astype(np.float64)
  img_size = img_size.astype(np.float64)
  reference = _numpy_projection(boxes, priors, intrinsics, img_size, clipped, axis_aware)

  dictionary_result = fg.project_frustum_batch(
    {"boxes": boxes, "priors": priors, "clipped": clipped,
     "axis_aware": axis_aware},
    intrinsics=intrinsics, img_size=img_size,
  )
  keyword_result = fg.project_frustum_batch(
    boxes=boxes, priors=priors, intrinsics=intrinsics, img_size=img_size,
    clipped=clipped, axis_aware=axis_aware,
  )

  _assert_matches_numpy(dictionary_result, reference)
  _assert_matches_numpy(keyword_result, reference)


@pytest.mark.parametrize("missing", ["boxes", "priors", "intrinsics", "img_size"])
def test_missing_required_input_raises_type_error(missing):
  boxes, priors, intrinsics, img_size, _, _ = _projection_inputs()
  arguments = {
    "boxes": boxes, "priors": priors, "intrinsics": intrinsics, "img_size": img_size,
  }
  arguments.pop(missing)

  with pytest.raises(TypeError, match="requires boxes, priors, intrinsics, and img_size"):
    fg.project_frustum_batch(**arguments)


@pytest.mark.parametrize("feature", ["ranges", "sensor"])
def test_numpy_backend_rejects_range_fusion(monkeypatch, feature):
  monkeypatch.setattr(fg, "_cpp", None)
  boxes, priors, intrinsics, img_size, _, _ = _projection_inputs()
  observations = {"boxes": boxes, "priors": priors}
  kwargs = {}
  if feature == "ranges":
    observations["ranges"] = np.full(len(boxes), 5.0, dtype=np.float32)
  else:
    kwargs["sensor"] = object()

  with pytest.raises(NotImplementedError, match="requires the native frustum kernel"):
    fg.project_frustum_batch(observations, intrinsics, img_size, **kwargs)