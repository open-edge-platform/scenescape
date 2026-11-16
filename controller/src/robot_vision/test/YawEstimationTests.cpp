// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cmath>
#include <numbers>
#include <optional>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/MultiModelKalmanEstimator.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/Scenario.hpp"

namespace {

using namespace rv::tracking::test;
using rv::tracking::MotionModel;

constexpr double kFps = 10.0;
constexpr double kFrame = 1.0 / kFps;

// Yaw of each model; a single-model estimator only keeps the combined state.
std::vector<double> modelYaws(const FilterRun &run)
{
  if (run.estimator.mKalmanFilters.size() == 1)
  {
    return {run.state().yaw};
  }
  std::vector<double> yaws;
  for (const auto &state : run.estimator.currentStates())
  {
    yaws.push_back(state.yaw);
  }
  return yaws;
}

std::vector<double> modelYawVariances(const FilterRun &run)
{
  std::vector<double> variances;
  for (const auto &filter : run.estimator.mKalmanFilters)
  {
    variances.push_back(filter->getErrorCov().at<double>(idx::Yaw, idx::Yaw));
  }
  return variances;
}

// Largest yaw difference between two models [rad].
double modelYawSpread(const FilterRun &run)
{
  const auto yaws = modelYaws(run);
  double lowest = 0.0;
  double highest = 0.0;
  for (double yaw : yaws)
  {
    const double offset = std::remainder(yaw - yaws.front(), 2.0 * std::numbers::pi);
    lowest = std::min(lowest, offset);
    highest = std::max(highest, offset);
  }
  return highest - lowest;
}

} // namespace

// Bug: a detection without orientation corrected yaw with the predicted yaw as a fake measurement, so every camera
// frame shrank the yaw variance and pulled each model's yaw toward the combined yaw; fails on 4ac31c2f7.
TEST(YawEstimationTest, CameraOnlyUpdateLeavesYawUntouched)
{
  // A car turning on the spot under an orienting sensor: CTRV learns the turn rate, so the models disagree on yaw.
  // Standing still, yaw is uncorrelated with the measured position and size.
  const auto truth = Trajectory({.box = kCar}).straight(1.0).turn(0.5, 2.0).sample(kFps);
  const auto cameraDetection = makeDetection(truth.back());
  const double cameraTime = truth.back().t + kFrame;

  for (const auto &[name, models] : {std::pair{"CV", std::vector<MotionModel>{MotionModel::CV}},
                                     std::pair{"production", rv::tracking::kProductionMotionModels}})
  {
    SCOPED_TRACE(name);
    auto config = productionConfig();
    config.mMotionModels = models;
    Sensor lidar{.id = "lidar", .orienting = true};
    FilterRun run(config);
    run.feed(observe(truth, lidar));

    run.estimator.predict(atSeconds(cameraTime));
    const auto predictedYaws = modelYaws(run);
    const auto predictedVariances = modelYawVariances(run);
    run.estimator.correct(cameraDetection);
    const auto correctedYaws = modelYaws(run);
    const auto correctedVariances = modelYawVariances(run);

    for (size_t i = 0; i < predictedYaws.size(); ++i)
    {
      EXPECT_NEAR(correctedYaws[i], predictedYaws[i], 1e-9) << "model " << i;
      EXPECT_NEAR(correctedVariances[i], predictedVariances[i], 1e-9 * predictedVariances[i]) << "model " << i;
    }
  }
}

// Bug: camera frames shrank the yaw variance, so an orienting sensor that later saw a camera-started track moved its
// yaw only slowly; fails on 4ac31c2f7.
TEST(YawEstimationTest, CameraOnlyPeriodKeepsLidarResponsive)
{
  // A parked car facing 0.5 rad. The camera reports no yaw, so the track starts at yaw 0; then 1 s of LiDAR.
  const TruthSample parked{.heading = 0.5, .box = kCar};
  const auto yawAfterLidar = [&](double cameraSeconds) {
    const auto truth = Trajectory(parked).straight(cameraSeconds + 1.0).sample(kFps);
    Sensor camera;
    Sensor lidar{.id = "lidar", .orienting = true};
    FilterRun run;
    run.feed(observe(between(truth, 0.0, cameraSeconds + 0.5 * kFrame), camera));
    run.feed(observe(between(truth, cameraSeconds + 0.5 * kFrame, cameraSeconds + 1.0 + 0.5 * kFrame), lidar));
    return run.state().yaw;
  };

  const double afterBirth = yawAfterLidar(0.0);
  const double afterCameraPeriod = yawAfterLidar(10.0);
  EXPECT_GE(afterCameraPeriod, afterBirth) << "yaw after 1 s of LiDAR [rad]";
}

// Without yaw measurements a camera-only track keeps its covariances positive definite and its models close in yaw.
// The yaw variance is not observed and keeps growing slowly (0.13 rad^2 after 60 s here, 0.55 after 10 min); the bound
// catches a faster blow-up.
TEST(YawEstimationTest, CameraOnlyTurningYawStaysBounded)
{
  // More than four laps of a car seen by a camera only.
  const auto truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 58.0).sample(kFps);
  Sensor camera{.positionNoise = 0.05};
  FilterRun run;
  std::optional<double> firstFailure;
  double maxVariance = 0.0;
  double maxSpread = 0.0;
  for (const auto &observation : observe(truth, camera))
  {
    run.feed({observation});
    for (const auto &filter : run.estimator.mKalmanFilters)
    {
      const cv::Mat covariance = filter->getErrorCov();
      if (!firstFailure && !(cv::checkRange(covariance) && minEigenvalue(covariance) > 0.0))
      {
        firstFailure = observation.t;
      }
    }
    maxVariance = std::max(maxVariance, run.state().errorCovariance(idx::Yaw, idx::Yaw));
    maxSpread = std::max(maxSpread, modelYawSpread(run));
  }

  EXPECT_FALSE(firstFailure) << "a model covariance is not positive definite at t = " << firstFailure.value_or(0.0)
                             << " s";
  EXPECT_LE(maxVariance, 0.2) << "yaw variance [rad^2]";
  EXPECT_LE(maxSpread, 0.3) << "largest yaw difference between the models [rad]";
}
