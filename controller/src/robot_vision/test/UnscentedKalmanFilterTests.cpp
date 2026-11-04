// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <string>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/tracking/CVModel.hpp>
#include <rv/tracking/TrackedObject.hpp>
#include <rv/tracking/UnscentedKalmanFilter.hpp>

#include "support/TestUtils.hpp"

namespace {

using rv::tracking::TrackedObject;
namespace idx = rv::tracking::test::idx;

constexpr int kStateSize = TrackedObject::StateSize;
constexpr int kMeasurementSize = TrackedObject::MeasurementSize;
constexpr double kDeltaT = 0.1;

// Same UKF parameters as MultiModelKalmanEstimator.
cv::Ptr<cv::detail::tracking::UnscentedKalmanFilterMod>
makeCvFilter(const cv::Mat &state, const cv::Mat &errorCov, const cv::Mat &processNoise, double measurementNoise)
{
  cv::detail::tracking::UnscentedKalmanFilterParams params(
    kStateSize, kMeasurementSize, 1, 0, 0, cv::makePtr<rv::tracking::CVModel>());
  params.stateInit = state.clone();
  params.errorCovInit = errorCov.clone();
  params.processNoiseCov = processNoise.clone();
  params.measurementNoiseCov = cv::Mat::eye(kMeasurementSize, kMeasurementSize, CV_64F) * measurementNoise;
  params.alpha = 1.0;
  params.beta = 2.0;
  params.k = 3.0 - kStateSize;
  return cv::detail::tracking::createUnscentedKalmanFilterMod(params);
}

cv::Mat cvTransition(double deltaT)
{
  cv::Mat transition = cv::Mat::eye(kStateSize, kStateSize, CV_64F);
  transition.at<double>(idx::X, idx::Vx) = deltaT;
  transition.at<double>(idx::Y, idx::Vy) = deltaT;
  transition.at<double>(idx::Z, idx::Vz) = deltaT;
  transition.at<double>(idx::Ax, idx::Ax) = 0.0;
  transition.at<double>(idx::Ay, idx::Ay) = 0.0;
  transition.at<double>(idx::YawRate, idx::YawRate) = 0.0;
  return transition;
}

cv::Mat measurementSelection()
{
  cv::Mat selection = cv::Mat::zeros(kMeasurementSize, kStateSize, CV_64F);
  const int measured[] = {idx::X, idx::Y, idx::Z, idx::Length, idx::Width, idx::Height, idx::Yaw};
  for (int row = 0; row < kMeasurementSize; ++row)
  {
    selection.at<double>(row, measured[row]) = 1.0;
  }
  return selection;
}

} // namespace

// Bug: UnscentedKalmanFilterMod::setStateAndCovariance assigned shadowed parameters (no-op); fails on main 6b0a3156b.
TEST(UnscentedKalmanFilterTest, SetStateAndCovarianceOverwritesFilterState)
{
  const cv::Mat identity = cv::Mat::eye(kStateSize, kStateSize, CV_64F);
  auto filter = makeCvFilter(cv::Mat::zeros(kStateSize, 1, CV_64F), identity, identity * 1e-3, 0.2);

  const cv::Mat state(kStateSize, 1, CV_64F, cv::Scalar(42.0));
  const cv::Mat errorCov = identity * 7.0;
  filter->setStateAndCovariance(state, errorCov);

  EXPECT_DOUBLE_EQ(cv::norm(filter->getState(), state, cv::NORM_INF), 0.0);
  EXPECT_DOUBLE_EQ(cv::norm(filter->getErrorCov(), errorCov, cv::NORM_INF), 0.0);
}

// Bug: UnscentedKalmanFilterMod::correct paired prior sigma points with redrawn ones in Pxz; fails on main 6b0a3156b.
TEST(UnscentedKalmanFilterTest, LinearModelMatchesExactKalmanFilter)
{
  // CV is linear, so the unscented transform must reproduce the exact Kalman filter.
  TrackedObject start;
  start.length = 4.0;
  start.width = 1.8;
  start.height = 1.5;
  cv::Mat errorCov = cv::Mat::diag(
    (cv::Mat_<double>(kStateSize, 1) << 0.2, 0.2, 0.05, 0.05, 0.1, 0.1, 0.2, 0.05, 0.2, 0.2, 0.2, 0.05, 0.01));
  const cv::Mat processNoise = cv::Mat::eye(kStateSize, kStateSize, CV_64F) * 1e-3;
  const double measurementNoise = 0.2;
  auto filter = makeCvFilter(start.stateVector(), errorCov, processNoise, measurementNoise);

  const cv::Mat transition = cvTransition(kDeltaT);
  const cv::Mat selection = measurementSelection();
  const cv::Mat measurementNoiseCov = cv::Mat::eye(kMeasurementSize, kMeasurementSize, CV_64F) * measurementNoise;
  cv::Mat state = start.stateVector();
  const cv::Mat control(1, 1, CV_64F, cv::Scalar(kDeltaT));

  for (int update = 1; update <= 30; ++update)
  {
    TrackedObject target = start;
    target.x = 1.0 * kDeltaT * update;
    const cv::Mat measurement(target.measurementVector());

    filter->predict(control);
    filter->correct(measurement);

    state = transition * state;
    errorCov = transition * errorCov * transition.t() + processNoise;
    const cv::Mat innovationCov = selection * errorCov * selection.t() + measurementNoiseCov;
    const cv::Mat gain = errorCov * selection.t() * innovationCov.inv();
    state = state + gain * (measurement - selection * state);
    errorCov = errorCov - gain * selection * errorCov;

    SCOPED_TRACE("update " + std::to_string(update));
    ASSERT_LT(cv::norm(filter->getState(), state, cv::NORM_INF), 1e-9);
    ASSERT_LT(cv::norm(filter->getErrorCov(), errorCov, cv::NORM_INF), 1e-9);
  }
  EXPECT_GT(state.at<double>(idx::Vx), 0.5) << "velocity must be learned for the comparison to be meaningful";
}

// Bug: a failed Cholesky factorisation was ignored, so the sigma points used a half-factorised matrix whose earlier
// diagonal entries were stored inverted; fails on 6277c8cf5 (variance 4 comes out as 0.25).
TEST(UnscentedKalmanFilterTest, PredictRecoversFromNonPositiveDefiniteCovariance)
{
  // Variance 4 everywhere except a slightly negative yaw-rate variance, which the CV model resets anyway.
  cv::Mat errorCov = cv::Mat::eye(kStateSize, kStateSize, CV_64F) * 4.0;
  errorCov.at<double>(idx::YawRate, idx::YawRate) = -1e-3;
  const cv::Mat processNoise = cv::Mat::eye(kStateSize, kStateSize, CV_64F) * 1e-3;
  auto filter = makeCvFilter(cv::Mat::zeros(kStateSize, 1, CV_64F), errorCov, processNoise, 0.2);

  filter->predict(cv::Mat(1, 1, CV_64F, cv::Scalar(kDeltaT)));

  const cv::Mat predicted = filter->getErrorCov();
  ASSERT_TRUE(cv::checkRange(filter->getState()));
  ASSERT_TRUE(cv::checkRange(predicted));
  EXPECT_GT(rv::tracking::test::minEigenvalue(predicted), 0.0);
  // The other states keep their variance: x gets 4 + dt^2 * 4 from the velocity, plus the process noise.
  EXPECT_NEAR(predicted.at<double>(idx::X, idx::X), 4.0 + kDeltaT * kDeltaT * 4.0 + 1e-3, 1e-9);
  EXPECT_NEAR(predicted.at<double>(idx::Height, idx::Height), 4.0 + 1e-3, 1e-9);
}

// The reduced update selects the observed rows of small matrices for every model and detection. All rows but yaw are
// contiguous, so they must be views of the matrix rather than copies; rows with gaps are still copied.
TEST(UnscentedKalmanFilterTest, SelectRowsAndBlockShareContiguousData)
{
  cv::Mat matrix(kMeasurementSize, kMeasurementSize, CV_64F);
  for (int i = 0; i < kMeasurementSize; ++i)
  {
    for (int j = 0; j < kMeasurementSize; ++j)
    {
      matrix.at<double>(i, j) = 10.0 * i + j;
    }
  }
  const std::vector<int> leading{0, 1, 2, 3, 4, 5};

  const cv::Mat rows = cv::detail::tracking::selectRows(matrix, leading);
  const cv::Mat block = cv::detail::tracking::selectBlock(matrix, leading);
  EXPECT_EQ(rows.data, matrix.data) << "contiguous rows must share the matrix data";
  EXPECT_EQ(block.data, matrix.data) << "a contiguous block must share the matrix data";
  EXPECT_DOUBLE_EQ(cv::norm(rows, matrix.rowRange(0, 6), cv::NORM_INF), 0.0);
  EXPECT_DOUBLE_EQ(cv::norm(block, matrix(cv::Range(0, 6), cv::Range(0, 6)), cv::NORM_INF), 0.0);

  const std::vector<int> gapped{0, 2, 6};
  const cv::Mat gappedBlock = cv::detail::tracking::selectBlock(matrix, gapped);
  for (int i = 0; i < 3; ++i)
  {
    for (int j = 0; j < 3; ++j)
    {
      EXPECT_DOUBLE_EQ(gappedBlock.at<double>(i, j), matrix.at<double>(gapped[i], gapped[j]));
    }
  }
}

// The covariance repair needs double precision: float32 rounding loses its eigenvalue floor. robot_vision only creates
// double-precision filters, so single precision is rejected.
TEST(UnscentedKalmanFilterTest, RejectsSinglePrecision)
{
  const cv::detail::tracking::UnscentedKalmanFilterParams params(
    kStateSize, kMeasurementSize, 1, 1e-3, 0.2, cv::makePtr<rv::tracking::CVModel>(), CV_32F);

  EXPECT_THROW(cv::detail::tracking::createUnscentedKalmanFilterMod(params), cv::Exception);
}
