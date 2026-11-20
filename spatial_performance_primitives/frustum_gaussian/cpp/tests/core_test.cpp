// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "frustum_gaussian/frustum.hpp"

#include <Eigen/Eigenvalues>
#include <gtest/gtest.h>

#include <array>
#include <cmath>
#include <limits>

namespace {

fg::Intrinsics test_intrinsics() {
  return fg::Intrinsics(500.0f, 500.0f, 200.0f, 200.0f, 400.0f, 400.0f);
}

fg::ShapePrior test_prior() {
  return fg::ShapePrior(0.55f, 0.55f, 1.70f, 0.10f, 0.10f, 0.15f);
}

void expect_observations_near(const fg::FrustumObservation &left,
                              const fg::FrustumObservation &right,
                              float tolerance = 1e-5f) {
  for (size_t axis = 0; axis < 3; ++axis) {
    EXPECT_NEAR(left.mu[axis], right.mu[axis], tolerance);
    EXPECT_NEAR(left.ray[axis], right.ray[axis], tolerance);
  }
  for (size_t value = 0; value < 9; ++value) {
    EXPECT_NEAR(left.Sigma[value], right.Sigma[value], tolerance);
  }
  EXPECT_NEAR(left.depth_est, right.depth_est, tolerance);
  EXPECT_NEAR(left.depth_sigma, right.depth_sigma, tolerance);
  EXPECT_NEAR(left.depth_lo, right.depth_lo, tolerance);
  EXPECT_NEAR(left.depth_hi, right.depth_hi, tolerance);
  EXPECT_NEAR(left.score, right.score, tolerance);
  EXPECT_EQ(left.edge_valid, right.edge_valid);
}

TEST(FrustumProjectionTest,
     CenteredBoxProducesFinitePositiveSemidefiniteObservation) {
  const auto observation =
      fg::project_frustum(fg::BoundingBox(150.0f, 100.0f, 250.0f, 300.0f),
                          test_intrinsics(), test_prior());

  EXPECT_NEAR(observation.ray[0], 0.0f, 1e-6f);
  EXPECT_NEAR(observation.ray[1], 0.0f, 1e-6f);
  EXPECT_NEAR(observation.ray[2], 1.0f, 1e-6f);
  EXPECT_GT(observation.depth_est, 0.0f);
  EXPECT_GT(observation.depth_sigma, 0.0f);
  EXPECT_EQ(observation.edge_valid, fg::EDGE_ALL);

  using RowMajorMatrix3f = Eigen::Matrix<float, 3, 3, Eigen::RowMajor>;
  const Eigen::Map<const RowMajorMatrix3f> covariance(observation.Sigma);
  EXPECT_TRUE(covariance.isApprox(covariance.transpose(), 1e-6f));
  const Eigen::SelfAdjointEigenSolver<Eigen::Matrix3f> eigenvalues(covariance);
  ASSERT_EQ(eigenvalues.info(), Eigen::Success);
  EXPECT_GE(eigenvalues.eigenvalues().minCoeff(), -1e-5f);
}

TEST(FrustumProjectionTest, ClippedEdgeClearsNearDepthBoundAndValidityBit) {
  const auto observation =
      fg::project_frustum(fg::BoundingBox(0.0f, 0.0f, 100.0f, 300.0f),
                          test_intrinsics(), test_prior());

  EXPECT_EQ(observation.edge_valid, fg::EDGE_RIGHT | fg::EDGE_BOTTOM);
  EXPECT_FLOAT_EQ(observation.depth_lo, 0.0f);
  EXPECT_GT(observation.depth_hi, 0.0f);
  EXPECT_NEAR(observation.depth_est,
              std::max(observation.depth_hi * 0.5f, 0.1f), 1e-5f);
  EXPECT_NEAR(observation.depth_sigma, observation.depth_hi / std::sqrt(12.0f),
              1e-5f);
}

TEST(FrustumProjectionTest, DegenerateBoxAxisFallsBackToOtherVisibleAxis) {
  const auto horizontal =
      fg::project_frustum(fg::BoundingBox(200.0f, 100.0f, 200.0f, 300.0f),
                          test_intrinsics(), test_prior());
  const auto vertical =
      fg::project_frustum(fg::BoundingBox(100.0f, 200.0f, 300.0f, 200.0f),
                          test_intrinsics(), test_prior());

  EXPECT_TRUE(std::isfinite(horizontal.depth_est));
  EXPECT_TRUE(std::isfinite(horizontal.depth_sigma));
  EXPECT_TRUE(std::isfinite(vertical.depth_est));
  EXPECT_TRUE(std::isfinite(vertical.depth_sigma));
}

TEST(FrustumProjectionTest, OrientationAveragedPriorChangesDepthEstimate) {
  const fg::BoundingBox box(120.0f, 100.0f, 280.0f, 300.0f);
  const fg::ShapePrior axis_aware(4.0f, 0.5f, 0.5f, 0.1f, 0.1f, 0.1f, true);
  const fg::ShapePrior orientation_averaged(4.0f, 0.5f, 0.5f, 0.1f, 0.1f, 0.1f,
                                            false);

  const auto aware = fg::project_frustum(box, test_intrinsics(), axis_aware);
  const auto averaged =
      fg::project_frustum(box, test_intrinsics(), orientation_averaged);

  EXPECT_TRUE(std::isfinite(aware.depth_est));
  EXPECT_TRUE(std::isfinite(averaged.depth_est));
  EXPECT_GT(std::abs(aware.depth_est - averaged.depth_est), 0.1f);
}

TEST(FrustumProjectionTest, BatchMatchesScalarProjection) {
  const fg::Intrinsics intrinsics = test_intrinsics();
  const std::array<fg::BoundingBox, 2> boxes = {
      fg::BoundingBox(150.0f, 100.0f, 250.0f, 300.0f),
      fg::BoundingBox(80.0f, 110.0f, 180.0f, 290.0f),
  };
  const std::array<fg::ShapePrior, 2> priors = {
      test_prior(),
      fg::ShapePrior(2.0f, 4.5f, 1.5f, 0.2f, 0.5f, 0.2f, false),
  };
  std::array<fg::FrustumObservation, 2> batch{};
  fg::project_frustum_batch(boxes.data(), intrinsics, priors.data(),
                            fg::DetectorNoise{}, batch.data(), batch.size());

  for (size_t index = 0; index < boxes.size(); ++index) {
    const auto scalar =
        fg::project_frustum(boxes[index], intrinsics, priors[index]);
    for (size_t axis = 0; axis < 3; ++axis) {
      EXPECT_NEAR(batch[index].mu[axis], scalar.mu[axis], 1e-6f);
      EXPECT_NEAR(batch[index].ray[axis], scalar.ray[axis], 1e-6f);
    }
    for (size_t value = 0; value < 9; ++value) {
      EXPECT_NEAR(batch[index].Sigma[value], scalar.Sigma[value], 1e-6f);
    }
    EXPECT_NEAR(batch[index].depth_est, scalar.depth_est, 1e-6f);
    EXPECT_NEAR(batch[index].depth_sigma, scalar.depth_sigma, 1e-6f);
    EXPECT_EQ(batch[index].edge_valid, scalar.edge_valid);
  }
}

TEST(FrustumProjectionTest, EmptyBatchDoesNotDereferenceBuffers) {
  fg::project_frustum_batch(nullptr, test_intrinsics(), nullptr,
                            fg::DetectorNoise{}, nullptr, 0);
}

TEST(FrustumProjectionTest, ParallelRangeBatchMatchesScalarRangeProjection) {
  constexpr size_t count = 64;
  const fg::Intrinsics intrinsics = test_intrinsics();
  std::array<fg::BoundingBox, count> boxes{};
  std::array<fg::ShapePrior, count> priors{};
  std::array<float, count> ranges{};
  std::array<fg::FrustumObservation, count> batch{};
  const fg::RangeSensorConfig sensor(0.05f, 0.0f, 100.0f,
                                     fg::RangeConvention::SLANT_RANGE);

  for (size_t index = 0; index < count; ++index) {
    const float left = 80.0f + static_cast<float>(index % 32);
    boxes[index] = fg::BoundingBox(left, 100.0f, left + 100.0f, 300.0f);
    priors[index] = test_prior();
    ranges[index] = 5.0f + static_cast<float>(index % 4);
  }

  fg::project_frustum_batch(boxes.data(), intrinsics, priors.data(),
                            fg::DetectorNoise{}, batch.data(), count,
                            ranges.data(), sensor);

  for (size_t index = 0; index < count; ++index) {
    const auto scalar =
        fg::project_frustum(boxes[index], intrinsics, priors[index],
                            fg::DetectorNoise{}, ranges[index], sensor);
    expect_observations_near(batch[index], scalar, 2e-5f);
  }
}

TEST(RangeProjectionTest, InvalidRangesFallBackToAngularProjection) {
  const fg::BoundingBox box(140.0f, 100.0f, 260.0f, 300.0f);
  const fg::DetectorNoise noise;
  const fg::RangeSensorConfig sensor(0.05f, 1.0f, 10.0f,
                                     fg::RangeConvention::SLANT_RANGE);
  const auto angular =
      fg::project_frustum(box, test_intrinsics(), test_prior(), noise);
  const std::array<float, 3> invalid_ranges = {
      std::numeric_limits<float>::quiet_NaN(),
      1.0f,
      10.1f,
  };

  for (const float range : invalid_ranges) {
    const auto observation = fg::project_frustum(
        box, test_intrinsics(), test_prior(), noise, range, sensor);
    expect_observations_near(observation, angular);
  }
}

TEST(RangeProjectionTest, CartesianAndSlantRangesProduceEquivalentFusion) {
  const fg::BoundingBox box(240.0f, 100.0f, 340.0f, 300.0f);
  const fg::DetectorNoise noise;
  const auto intrinsics = test_intrinsics();
  const auto angular =
      fg::project_frustum(box, intrinsics, test_prior(), noise);
  const float slant_range = 8.0f;
  const float cartesian_depth = slant_range * angular.ray[2];
  const fg::RangeSensorConfig slant_sensor(0.05f, 0.1f, 100.0f,
                                           fg::RangeConvention::SLANT_RANGE);
  const fg::RangeSensorConfig cartesian_sensor(
      0.05f, 0.1f, 100.0f, fg::RangeConvention::CARTESIAN_DEPTH);

  const auto slant = fg::project_frustum(box, intrinsics, test_prior(), noise,
                                         slant_range, slant_sensor);
  const auto cartesian = fg::project_frustum(
      box, intrinsics, test_prior(), noise, cartesian_depth, cartesian_sensor);

  expect_observations_near(slant, cartesian, 2e-5f);
  EXPECT_GE(slant.depth_est, slant.depth_lo);
  EXPECT_LE(slant.depth_est, slant.depth_hi);
}

TEST(RangeProjectionTest, RangeBeyondAngularBoundCollapsesDepthInterval) {
  const fg::BoundingBox box(150.0f, 100.0f, 250.0f, 300.0f);
  const fg::RangeSensorConfig sensor(0.05f, 0.0f, 2000.0f,
                                     fg::RangeConvention::SLANT_RANGE);
  const auto observation =
      fg::project_frustum(box, test_intrinsics(), test_prior(),
                          fg::DetectorNoise{}, 1000.0f, sensor);

  EXPECT_FLOAT_EQ(observation.depth_lo, 1000.0f);
  EXPECT_FLOAT_EQ(observation.depth_hi, observation.depth_lo);
  EXPECT_FLOAT_EQ(observation.depth_est, observation.depth_lo);
}

TEST(FrustumProjection3DTest, UsesCenterAndRotatesBodyFrameUncertainty) {
  const float translation[3] = {1.0f, 2.0f, 8.0f};
  const float half_extents[3] = {0.5f, 1.0f, 0.75f};
  const float identity[9] = {1.0f, 0.0f, 0.0f, 0.0f, 1.0f,
                             0.0f, 0.0f, 0.0f, 1.0f};
  const float body_sigmas[3] = {0.1f, 0.2f, 0.3f};
  const auto observation = fg::project_frustum_3d(
      translation, half_extents, identity, test_intrinsics(), body_sigmas);

  for (size_t axis = 0; axis < 3; ++axis) {
    EXPECT_FLOAT_EQ(observation.mu[axis], translation[axis]);
  }
  EXPECT_NEAR(observation.depth_est, std::sqrt(69.0f), 1e-6f);
  EXPECT_NEAR(observation.Sigma[0], 0.01f, 1e-6f);
  EXPECT_NEAR(observation.Sigma[4], 0.04f, 1e-6f);
  EXPECT_NEAR(observation.Sigma[8], 0.09f, 1e-6f);
  EXPECT_EQ(observation.edge_valid, fg::EDGE_ALL);
}

TEST(FrustumProjection3DTest, RotatesAnisotropicCovarianceWithBodyOrientation) {
  const float translation[3] = {1.0f, 2.0f, 8.0f};
  const float half_extents[3] = {0.5f, 1.0f, 0.75f};
  const float rotation[9] = {0.0f, -1.0f, 0.0f, 1.0f, 0.0f,
                             0.0f, 0.0f,  0.0f, 1.0f};
  const float body_sigmas[3] = {0.1f, 0.2f, 0.3f};
  const auto observation = fg::project_frustum_3d(
      translation, half_extents, rotation, test_intrinsics(), body_sigmas);

  EXPECT_NEAR(observation.Sigma[0], 0.04f, 1e-6f);
  EXPECT_NEAR(observation.Sigma[4], 0.01f, 1e-6f);
  EXPECT_NEAR(observation.Sigma[8], 0.09f, 1e-6f);
  const float expected_variance = 5.84f / 69.0f;
  EXPECT_NEAR(observation.depth_sigma, std::sqrt(expected_variance), 1e-6f);
}

TEST(FrustumProjection3DTest, IsotropicOverloadUsesSameNoiseOnEveryAxis) {
  const float translation[3] = {0.0f, 0.0f, 8.0f};
  const float half_extents[3] = {0.5f, 1.0f, 0.75f};
  const float identity[9] = {1.0f, 0.0f, 0.0f, 0.0f, 1.0f,
                             0.0f, 0.0f, 0.0f, 1.0f};
  const auto observation = fg::project_frustum_3d(
      translation, half_extents, identity, test_intrinsics(), 0.25f);

  EXPECT_FLOAT_EQ(observation.Sigma[0], 0.0625f);
  EXPECT_FLOAT_EQ(observation.Sigma[4], 0.0625f);
  EXPECT_FLOAT_EQ(observation.Sigma[8], 0.0625f);
  EXPECT_FLOAT_EQ(observation.depth_sigma, 0.25f);
}

TEST(WorldTransformTest, ScalesDepthMetadataWithAnisotropicPose) {
  fg::FrustumObservation observation;
  observation.mu[0] = 1.0f;
  observation.mu[1] = 2.0f;
  observation.mu[2] = 3.0f;
  observation.Sigma[0] = 1.0f;
  observation.Sigma[4] = 1.0f;
  observation.Sigma[8] = 1.0f;
  observation.ray[2] = 1.0f;
  observation.depth_est = 5.0f;
  observation.depth_sigma = 1.0f;
  observation.depth_lo = 4.0f;
  observation.depth_hi = 6.0f;
  observation.score = 0.7f;
  observation.edge_valid = fg::EDGE_ALL;
  const float pose[16] = {
      2.0f, 0.0f, 0.0f, 10.0f, 0.0f, 3.0f, 0.0f, 20.0f,
      0.0f, 0.0f, 4.0f, 30.0f, 0.0f, 0.0f, 0.0f, 1.0f,
  };

  const auto world = fg::transform_to_world(observation, pose);

  EXPECT_FLOAT_EQ(world.mu[0], 12.0f);
  EXPECT_FLOAT_EQ(world.mu[1], 26.0f);
  EXPECT_FLOAT_EQ(world.mu[2], 42.0f);
  EXPECT_FLOAT_EQ(world.Sigma[0], 4.0f);
  EXPECT_FLOAT_EQ(world.Sigma[4], 9.0f);
  EXPECT_FLOAT_EQ(world.Sigma[8], 16.0f);
  EXPECT_FLOAT_EQ(world.depth_est, 20.0f);
  EXPECT_FLOAT_EQ(world.depth_sigma, 4.0f);
  EXPECT_FLOAT_EQ(world.depth_lo, 16.0f);
  EXPECT_FLOAT_EQ(world.depth_hi, 24.0f);
  EXPECT_FLOAT_EQ(world.score, observation.score);
  EXPECT_EQ(world.edge_valid, observation.edge_valid);
}

} // namespace