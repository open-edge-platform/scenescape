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

constexpr int kStateSize = 12;
constexpr int kMeasurementSize = 7;
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

TEST(UnscentedKalmanFilterTest, LinearModelMatchesExactKalmanFilter)
{
  // CV is linear, so the unscented transform must reproduce the exact Kalman filter.
  TrackedObject start;
  start.length = 4.0;
  start.width = 1.8;
  start.height = 1.5;
  cv::Mat errorCov = cv::Mat::diag(
    (cv::Mat_<double>(kStateSize, 1) << 0.2, 0.2, 0.05, 0.05, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2, 0.05, 0.01));
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
    const cv::Mat measurement = target.measurementVector();

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
