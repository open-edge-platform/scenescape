// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cmath>
#include <numbers>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include "support/Scenario.hpp"

namespace {

using namespace rv::tracking::test;
using rv::tracking::MotionModel;

struct SelectionCase
{
  const char *name;
  std::vector<TruthSample> truth;
  double from; // model probabilities are averaged over [from, to)
  double to;
  MotionModel expected;
  double minProbability; // mean probability of the expected model
  double minMargin;      // over the runner-up
};

// Windows start once the probabilities have settled: after the speed pick-up at birth, about 1 s into braking, 2 s into
// a turn, 3 s after it. Turns at walking speed have no row: CA or CV still win them, as with a measurement noise of
// 0.2 the turn adds too little information (TracksMotionCases bounds their accuracy).
std::vector<SelectionCase> modelSelectionCases()
{
  constexpr double kFps = 10.0;
  return {
    {.name = "constant velocity, person 1.5 m/s",
     .truth = Trajectory({.speed = 1.5, .box = kPerson}).straight(12.0).sample(kFps),
     .from = 3.0,
     .to = 12.0,
     .expected = MotionModel::CV,
     .minProbability = 0.0,
     .minMargin = 0.03},
    {.name = "constant velocity, car 10 m/s",
     .truth = Trajectory({.speed = 10.0, .box = kCar}).straight(12.0).sample(kFps),
     .from = 3.0,
     .to = 12.0,
     .expected = MotionModel::CV,
     .minProbability = 0.0,
     .minMargin = 0.05},
    {.name = "pulling away at 2 m/s^2",
     .truth = Trajectory({.box = kCar}).accelerate(2.0, 8.0).sample(kFps),
     .from = 2.0,
     .to = 8.0,
     .expected = MotionModel::CA,
     .minProbability = 0.45,
     .minMargin = 0.0},
    {.name = "braking at -4 m/s^2 from 10 m/s",
     .truth = Trajectory({.speed = 10.0, .box = kCar}).straight(3.0).accelerate(-4.0, 2.5).sample(kFps),
     .from = 4.0,
     .to = 5.5,
     .expected = MotionModel::CA,
     .minProbability = 0.45,
     .minMargin = 0.0},
    {.name = "turn, car 5 m/s at 0.5 rad/s",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 10.0).sample(kFps),
     .from = 4.0,
     .to = 12.0,
     .expected = MotionModel::CTRV,
     .minProbability = 0.45,
     .minMargin = 0.2},
    {.name = "turn, car 5 m/s at -0.3 rad/s",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(-0.3, 10.0).sample(kFps),
     .from = 4.0,
     .to = 12.0,
     .expected = MotionModel::CTRV,
     .minProbability = 0.40,
     .minMargin = 0.1},
    {.name = "straight after a 4 s turn",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 4.0).straight(6.0).sample(kFps),
     .from = 9.0,
     .to = 12.0,
     .expected = MotionModel::CV,
     .minProbability = 0.0,
     .minMargin = 0.03},
  };
}

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
  // Bounds are the current errors plus margin.
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
     .maxPositionError = 0.65,
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
     .maxPositionError = 0.6,
     .maxFinalSpeedError = 0.25},
    {.name = "circle, car",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 8.0).sample(kFps),
     .maxPositionError = 0.65,
     .maxFinalSpeedError = 0.2},
    {.name = "turn, person",
     .truth = Trajectory({.speed = 1.5, .box = kPerson}).straight(2.0).turn(0.4, 6.0).sample(kFps),
     .maxPositionError = 0.5,
     .maxFinalSpeedError = 0.1},
  };
  constexpr double kWarmUp = 2.0;

  for (const auto &motion : cases)
  {
    SCOPED_TRACE(motion.name);
    const auto &truth = motion.truth;
    Sensor camera{.positionNoise = 0.05};
    FilterRun run;
    const auto states = run.feed(observe(truth, camera));

    EXPECT_LE(std::ranges::max(positionErrors(truth, states, kWarmUp)), motion.maxPositionError);
    EXPECT_LE(std::fabs(std::hypot(states.back().vx, states.back().vy) - truth.back().speed),
              motion.maxFinalSpeedError);
  }
}

// Bug: CTRV did not win sustained car turns, nor CV the straight driving after them; fails on main 5d80db465.
TEST(MotionScenarioTest, ModelSelection)
{
  for (const auto &selection : modelSelectionCases())
  {
    SCOPED_TRACE(selection.name);
    Sensor camera{.positionNoise = 0.05};
    FilterRun run;
    run.feed(observe(between(selection.truth, 0.0, selection.from), camera));

    const auto window = observe(between(selection.truth, selection.from, selection.to), camera);
    cv::Mat probabilitySum = cv::Mat::zeros(static_cast<int>(rv::tracking::kProductionMotionModels.size()), 1, CV_64F);
    for (const auto &observation : window)
    {
      run.feed({observation});
      probabilitySum += run.estimator.getModelProbability();
    }
    const cv::Mat mean = probabilitySum / static_cast<double>(window.size());
    const double expected = mean.at<double>(modelIndex(selection.expected));
    double runnerUp = 0.0;
    for (const auto model : rv::tracking::kProductionMotionModels)
    {
      if (model != selection.expected)
      {
        runnerUp = std::max(runnerUp, mean.at<double>(modelIndex(model)));
      }
    }

    EXPECT_GE(expected, selection.minProbability) << "mean model probabilities (CV, CA, CTRV) " << mean.t();
    EXPECT_GT(expected - runnerUp, selection.minMargin) << "mean model probabilities (CV, CA, CTRV) " << mean.t();
  }
}

TEST(MotionScenarioTest, CovarianceStaysPositiveDefinite)
{
  // CV, CA and CTRV each reset some states to 0; their process noise keeps those variances positive.
  for (const auto &selection : modelSelectionCases())
  {
    SCOPED_TRACE(selection.name);
    Sensor camera{.positionNoise = 0.05};
    FilterRun run;
    std::optional<double> firstFailure;
    for (const auto &observation : observe(selection.truth, camera))
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
    }
    EXPECT_FALSE(firstFailure) << "a model covariance is not positive definite at t = " << firstFailure.value_or(0.0)
                               << " s";
  }
}

// Bug: CTRV's turn rate did not follow the target's turns; fails on main 5d80db465.
TEST(MotionScenarioTest, TurningTargetLearnsTurnRate)
{
  struct TurnCase
  {
    const char *name;
    std::vector<TruthSample> truth;
    double minTurnRate; // CTRV's own estimate after the last observation [rad/s]
    double maxTurnRate;
  };
  constexpr double kFps = 10.0;
  const TurnCase cases[] = {
    {.name = "end of a 10 s turn at 0.5 rad/s",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 10.0).sample(kFps),
     .minTurnRate = 0.3,
     .maxTurnRate = 0.6},
    {.name = "end of a 10 s turn at -0.3 rad/s",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(-0.3, 10.0).sample(kFps),
     .minTurnRate = -0.45,
     .maxTurnRate = -0.15},
    {.name = "2 s after a 4 s turn at 0.5 rad/s",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 4.0).straight(2.0).sample(kFps),
     .minTurnRate = -0.05,
     .maxTurnRate = 0.05},
  };

  for (const auto &turn : cases)
  {
    SCOPED_TRACE(turn.name);
    Sensor camera{.positionNoise = 0.05};
    FilterRun run;
    run.feed(observe(turn.truth, camera));

    // The combined turn rate is diluted by the CV and CA probabilities.
    const double turnRate = run.estimator.currentStates()[modelIndex(MotionModel::CTRV)].w;
    EXPECT_GE(turnRate, turn.minTurnRate);
    EXPECT_LE(turnRate, turn.maxTurnRate);
  }
}

// Bug: a track coasting out of a turn drifted more than 2 m off the path within 1 s; fails on main 5d80db465.
TEST(MotionScenarioTest, CoastingAfterTurn)
{
  // Observed for 8 s of the turn, then 1 s without detections; the tracker predicts every frame.
  const auto observed = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 8.0).sample(10.0);
  const auto truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 9.0).sample(10.0).back();
  Sensor camera{.positionNoise = 0.05};
  FilterRun run;
  run.feed(observe(observed, camera));

  for (int frame = 0; frame < 10; ++frame)
  {
    run.coast(0.1);
  }
  EXPECT_LE(positionError(run.state(), truth), 1.8);
}

// Bug: yaw drifted away from an orienting sensor's heading in a sustained turn; fails on main 5d80db465.
TEST(MotionScenarioTest, OrientingSensorFollowsTurningHeading)
{
  // More than four laps.
  const auto truth = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.5, 58.0).sample(10.0);
  Sensor lidar{.positionNoise = 0.05, .yawNoise = 0.05, .orienting = true};
  FilterRun run;

  double maxSpread = 0.0;
  for (const auto &observation : observe(truth, lidar))
  {
    run.feed({observation});
    const auto &models = run.estimator.currentStates();
    double lowest = 0.0;
    double highest = 0.0;
    for (const auto &model : models)
    {
      const double offset = std::remainder(model.yaw - models.front().yaw, 2.0 * std::numbers::pi);
      lowest = std::min(lowest, offset);
      highest = std::max(highest, offset);
    }
    maxSpread = std::max(maxSpread, highest - lowest);
  }

  EXPECT_LE(std::fabs(std::remainder(run.state().yaw - truth.back().heading, 2.0 * std::numbers::pi)), 0.2);
  EXPECT_LE(maxSpread, 0.3) << "largest yaw difference between the models [rad]";
}

// Bug: a car turning on the spot took more than 5 s to show the orienting sensor's yaw; fails on main 5d80db465.
TEST(MotionScenarioTest, OrientingSensorFollowsRotationInPlace)
{
  constexpr double kFps = 10.0;
  const auto truth = Trajectory({.box = kCar}).straight(5.0).turn(0.5, 1.0).straight(5.0).sample(kFps);
  Sensor lidar{.positionNoise = 0.05, .yawNoise = 0.02, .orienting = true};
  FilterRun run;
  const auto states = run.feed(observe(truth, lidar));

  const auto yawAt = [&](double t) { return states[static_cast<size_t>(std::lround(t * kFps))].yaw; };
  EXPECT_GE(yawAt(7.0), 0.35) << "1 s after the rotation";
  EXPECT_GE(yawAt(11.0), 0.45) << "5 s after the rotation";
}

TEST(MotionScenarioTest, StraightLineMatchesConstantVelocityFilter)
{
  // On straight lines the extra models must cost little accuracy against a CV-only filter. The ratio varies by about
  // 0.2 between noise seeds, so this catches gross regressions only.
  constexpr double kFps = 10.0;
  constexpr double kWarmUp = 3.0;
  constexpr double kMaxRatio = 1.1;
  const auto positionRms = [](const std::vector<TruthSample> &truth, const std::vector<MotionModel> &models) {
    auto config = productionConfig();
    config.mMotionModels = models;
    Sensor camera{.positionNoise = 0.05};
    FilterRun run(config);
    return rms(positionErrors(truth, run.feed(observe(truth, camera)), kWarmUp));
  };

  for (const auto &[name, start] : {std::pair{"person 1.5 m/s", TruthSample{.speed = 1.5, .box = kPerson}},
                                    std::pair{"car 10 m/s", TruthSample{.speed = 10.0, .box = kCar}},
                                    std::pair{"stationary car", TruthSample{.box = kCar}}})
  {
    SCOPED_TRACE(name);
    const auto truth = Trajectory(start).straight(12.0).sample(kFps);
    const double imm = positionRms(truth, rv::tracking::kProductionMotionModels);
    const double cv = positionRms(truth, {MotionModel::CV});
    EXPECT_LE(imm, kMaxRatio * cv) << "position rms: IMM " << imm << " m, CV only " << cv << " m";
  }
}

TEST(MotionScenarioTest, ConstantVelocityConvergence)
{
  // Same scenario and tolerance as the constant-velocity tests in tests/sscape_tests/robot_vision/tracking_test.py.
  constexpr double kTolerance = 0.05;
  for (const auto &models :
       {std::vector{MotionModel::CV}, std::vector{MotionModel::CV, MotionModel::CA, MotionModel::CTRV}})
  {
    SCOPED_TRACE(std::to_string(models.size()) + " motion model(s)");
    auto config = productionConfig();
    config.mDefaultProcessNoise = 1e-5;
    config.mDefaultMeasurementNoise = 1e-2;
    config.mMotionModels = models;
    Sensor camera{.positionNoise = 0.01};
    FilterRun run(config);
    run.feed(observe(
      Trajectory({.heading = std::atan2(1.0, 2.0), .speed = std::sqrt(5.0), .box = kPerson}).straight(9.9).sample(10.0),
      camera));

    EXPECT_NEAR(run.state().vx, 2.0, kTolerance);
    EXPECT_NEAR(run.state().vy, 1.0, kTolerance);
  }
}

TEST(MotionScenarioTest, TargetBornMovingAcquiresSpeed)
{
  // The 0.05 velocity prior cap slows speed pick-up: about half of the true 10 m/s after 1 s.
  Sensor camera;
  FilterRun run;
  run.feed(observe(Trajectory({.speed = 10.0, .box = kCar}).straight(1.0).sample(10.0), camera));

  EXPECT_GE(std::hypot(run.state().vx, run.state().vy), 4.5);
}
