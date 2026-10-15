// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cmath>
#include <numbers>
#include <vector>

#include <gtest/gtest.h>

#include "support/ScenarioRecorder.hpp"

namespace {

using namespace rv::tracking::test;
using rv::tracking::MotionModel;

} // namespace

TEST(ScenarioSupportTest, TrajectoryKinematics)
{
  // One full circle at 2 m/s ends where it started.
  const double turnRate = std::numbers::pi / 5.0;
  const auto circle = Trajectory({.speed = 2.0, .box = kPerson}).turn(turnRate, 10.0).sample(10.0);
  ASSERT_EQ(circle.size(), 101U);
  EXPECT_NEAR(circle.back().t, 10.0, 1e-9);
  EXPECT_NEAR(circle.back().x, 0.0, 1e-6);
  EXPECT_NEAR(circle.back().y, 0.0, 1e-6);
  EXPECT_NEAR(circle.back().heading, 2.0 * std::numbers::pi, 1e-9);
  const double radius = 2.0 / turnRate;
  EXPECT_NEAR(std::hypot(circle[25].x, circle[25].y - radius), radius, 1e-6);

  // Braking at 10 m/s^2 from 5 m/s stops after 0.5 s and 1.25 m, then stays put.
  const auto braking = Trajectory({.speed = 5.0, .box = kCar}).accelerate(-10.0, 1.0).sample(10.0);
  EXPECT_DOUBLE_EQ(braking.back().speed, 0.0);
  EXPECT_NEAR(braking.back().x, 1.25, 1e-3);
  EXPECT_EQ(between(braking, 0.5, 1.0).size(), 5U);
}

TEST(ScenarioSupportTest, ObserveReportsTruthWithSensorNoise)
{
  const auto truth = Trajectory({.heading = 3.0, .speed = 1.0, .box = kCar}).straight(100.0).sample(10.0);

  Sensor camera;
  const auto exact = observe(truth, camera);
  EXPECT_DOUBLE_EQ(exact.back().detection.x, truth.back().x);
  EXPECT_DOUBLE_EQ(exact.back().detection.height, kCar.height);
  EXPECT_DOUBLE_EQ(exact.back().detection.yaw, 0.0);
  EXPECT_FALSE(rv::tracking::orientation::hasOrientation(exact.back().detection));

  Sensor lidar{.positionNoise = 0.1, .sizeNoise = 0.05, .yawNoise = 0.02, .orienting = true};
  const auto noisy = observe(truth, lidar);
  double xSquares = 0.0;
  double heightSquares = 0.0;
  double yawSquares = 0.0;
  for (size_t i = 0; i < truth.size(); ++i)
  {
    const auto &detection = noisy[i].detection;
    xSquares += std::pow(detection.x - truth[i].x, 2);
    heightSquares += std::pow(detection.height - kCar.height, 2);
    yawSquares += std::pow(std::remainder(detection.yaw - truth[i].heading, 2.0 * std::numbers::pi), 2);
  }
  const double n = static_cast<double>(truth.size());
  EXPECT_NEAR(std::sqrt(xSquares / n), lidar.positionNoise, 0.1 * lidar.positionNoise);
  EXPECT_NEAR(std::sqrt(heightSquares / n), lidar.sizeNoise, 0.1 * lidar.sizeNoise);
  EXPECT_NEAR(std::sqrt(yawSquares / n), lidar.yawNoise, 0.1 * lidar.yawNoise);
  EXPECT_TRUE(rv::tracking::orientation::hasOrientation(noisy.back().detection));
}

TEST(MotionScenarioTest, TracksMotionCases)
{
  struct MotionCase
  {
    const char *name;
    std::vector<TruthSample> truth;
    double maxPositionError;   // after warm-up [m]
    double maxFinalSpeedError; // [m/s]
  };
  // Bounds are the current errors plus margin; turns stay loose while CTRV does not learn the turn rate.
  constexpr double kFps = 10.0;
  const MotionCase cases[] = {
    {.name = "constant velocity",
     .truth = Trajectory({.speed = 1.5, .box = kPerson}).straight(8.0).sample(kFps),
     .maxPositionError = 0.15,
     .maxFinalSpeedError = 0.03},
    {.name = "acceleration",
     .truth = Trajectory({.box = kCar}).accelerate(1.0, 5.0).straight(3.0).sample(kFps),
     .maxPositionError = 0.45,
     .maxFinalSpeedError = 0.01},
    {.name = "turn",
     .truth = Trajectory({.speed = 3.0, .box = kCar}).straight(2.0).turn(0.5, 4.0).straight(2.0).sample(kFps),
     .maxPositionError = 1.0,
     .maxFinalSpeedError = 0.05},
    {.name = "sudden stop",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(3.0).accelerate(-10.0, 0.5).straight(4.5).sample(kFps),
     .maxPositionError = 0.9,
     .maxFinalSpeedError = 0.05},
    // Ends 1 s after the stop; CA keeps some deceleration, so the estimated speed overshoots through zero.
    {.name = "manoeuvre",
     .truth = Trajectory({.speed = 2.0, .box = kCar})
                .straight(2.0)
                .accelerate(1.0, 2.0)
                .turn(-0.4, 3.0)
                .accelerate(-2.0, 2.0)
                .straight(1.0)
                .sample(kFps),
     .maxPositionError = 2.1,
     .maxFinalSpeedError = 0.35},
  };
  constexpr double kWarmUp = 2.0;

  for (const auto &motion : cases)
  {
    SCOPED_TRACE(motion.name);
    const auto &truth = motion.truth;
    Sensor camera{.positionNoise = 0.05};
    ScenarioRecorder recorder(motion.name);
    recorder.truth(truth);
    FilterRun run(productionConfig(), &recorder);
    const auto states = run.feed(recorder.detections(observe(truth, camera), "camera"));

    double maxPositionError = 0.0;
    for (size_t i = 0; i < truth.size(); ++i)
    {
      if (truth[i].t >= kWarmUp)
      {
        maxPositionError = std::max(maxPositionError, std::hypot(states[i].x - truth[i].x, states[i].y - truth[i].y));
      }
    }
    EXPECT_LE(maxPositionError, motion.maxPositionError);
    EXPECT_LE(std::fabs(std::hypot(states.back().vx, states.back().vy) - truth.back().speed),
              motion.maxFinalSpeedError);
  }
}

TEST(MotionScenarioTest, ConstantVelocityConvergence)
{
  // Same scenario and tolerance as the constant-velocity tests in tests/sscape_tests/robot_vision/tracking_test.py.
  constexpr double kTolerance = 0.05;
  const struct
  {
    const char *name;
    std::vector<MotionModel> models;
  } modelSets[] = {{"CV", {MotionModel::CV}}, {"CV CA CTRV", {MotionModel::CV, MotionModel::CA, MotionModel::CTRV}}};
  for (const auto &[name, models] : modelSets)
  {
    SCOPED_TRACE(name);
    auto config = productionConfig();
    config.mDefaultProcessNoise = 1e-5;
    config.mDefaultMeasurementNoise = 1e-2;
    config.mMotionModels = models;
    Sensor camera{.positionNoise = 0.01};
    const auto truth = Trajectory({.heading = std::atan2(1.0, 2.0), .speed = std::sqrt(5.0), .box = kPerson})
                         .straight(9.9)
                         .sample(10.0);
    ScenarioRecorder recorder(name);
    recorder.truth(truth);
    FilterRun run(config, &recorder);
    run.feed(recorder.detections(observe(truth, camera), "camera"));

    EXPECT_NEAR(run.state().vx, 2.0, kTolerance);
    EXPECT_NEAR(run.state().vy, 1.0, kTolerance);
  }
}

TEST(MotionScenarioTest, TargetBornMovingAcquiresSpeed)
{
  // The 0.05 velocity prior cap slows speed pick-up: about half of the true 10 m/s after 1 s.
  Sensor camera;
  const auto truth = Trajectory({.speed = 10.0, .box = kCar}).straight(1.0).sample(10.0);
  ScenarioRecorder recorder;
  recorder.truth(truth);
  FilterRun run(productionConfig(), &recorder);
  run.feed(recorder.detections(observe(truth, camera), "camera"));

  EXPECT_GE(std::hypot(run.state().vx, run.state().vy), 4.5);
}
