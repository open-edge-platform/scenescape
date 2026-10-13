// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>

#include <gtest/gtest.h>

#include <rv/tracking/MultiModelKalmanEstimator.hpp>
#include <rv/tracking/TrackedObject.hpp>

TEST(MultiModelKalmanEstimatorTest, KalmanFilterCovarianceGettersReturnMatchingMatrices)
{
  rv::tracking::TrackedObject object;
  object.length = 1.0;
  object.width = 1.0;
  object.height = 1.0;

  // Single model: the estimator publishes filter 0's covariances unmodified, so they can be compared exactly.
  rv::tracking::MultiModelKalmanEstimator estimator;
  estimator.initialize(object, std::chrono::system_clock::time_point{}, 1e-4, 2e-1, 1.0,
                       {rv::tracking::MotionModel::CV});
  estimator.predict(0.1);

  const auto state = estimator.currentState();
  const cv::Mat errorCov = estimator.getKalmanFilterErrorCovariance(0);
  const cv::Mat measurementCov = estimator.getKalmanFilterMeasurementCovariance(0);

  ASSERT_EQ(errorCov.rows, rv::tracking::TrackedObject::StateSize);
  ASSERT_EQ(errorCov.cols, rv::tracking::TrackedObject::StateSize);
  ASSERT_EQ(measurementCov.rows, rv::tracking::TrackedObject::MeasurementSize);
  ASSERT_EQ(measurementCov.cols, rv::tracking::TrackedObject::MeasurementSize);
  EXPECT_DOUBLE_EQ(cv::norm(errorCov, state.errorCovariance, cv::NORM_INF), 0.0);
  EXPECT_DOUBLE_EQ(cv::norm(measurementCov, state.predictedMeasurementCov, cv::NORM_INF), 0.0);
}
