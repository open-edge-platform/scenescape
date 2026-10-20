// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <chrono>
#include <string>
#include <type_traits>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/MultiModelKalmanEstimator.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/Scenario.hpp"

namespace {

using namespace rv::tracking::test;
using rv::tracking::MotionModel;
using rv::tracking::MultiModelKalmanEstimator;

// Row of a motion model in getModelProbability() for productionConfig().
int modelIndex(MotionModel model)
{
  const auto &models = rv::tracking::kProductionMotionModels;
  return static_cast<int>(std::ranges::find(models, model) - models.begin());
}

} // namespace

// Bug: MultiModelKalmanEstimator covariance getters returned each other's matrix; fails on main 6b0a3156b.
TEST(MultiModelKalmanEstimatorTest, KalmanFilterCovarianceGettersReturnMatchingMatrices)
{
  rv::tracking::TrackedObject object;
  object.length = 1.0;
  object.width = 1.0;
  object.height = 1.0;

  // Single model: the estimator publishes filter 0's covariances unmodified, so they can be compared exactly.
  rv::tracking::MultiModelKalmanEstimator estimator;
  estimator.initialize(
    object, std::chrono::system_clock::time_point{}, 1e-4, 2e-1, 1.0, {rv::tracking::MotionModel::CV});
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

// Bug: IMM mixing had no effect (UnscentedKalmanFilterMod::setStateAndCovariance no-op); fails on main 6b0a3156b.
TEST(MultiModelKalmanEstimatorTest, PredictMixesModelStates)
{
  // An accelerating, turning target makes CV, CA and CTRV disagree.
  Sensor camera;
  FilterRun run;
  run.feed(observe(Trajectory({.speed = 2.0, .box = kCar}).accelerate(1.0, 1.5).turn(0.6, 1.5).sample(10.0), camera));

  const auto before = run.estimator.currentStates();
  const cv::Mat mixing = run.estimator.getConditionalProbability();
  run.estimator.predict(0.0);
  const auto after = run.estimator.currentStates();

  double spread = 0.0;
  for (const auto &state : before)
  {
    spread = std::max(spread, cv::norm(state.stateVector(), before[0].stateVector(), cv::NORM_INF));
  }
  ASSERT_GT(spread, 1e-2) << "models must disagree for mixing to be observable";

  // At dt = 0 every model keeps these components, so after predict they must equal the IMM-mixed prior.
  const int kept[] = {idx::X, idx::Y, idx::Vx, idx::Vy, idx::Z, idx::Length, idx::Width, idx::Height, idx::Yaw};
  for (size_t j = 0; j < before.size(); ++j)
  {
    cv::Mat mixed = cv::Mat::zeros(rv::tracking::TrackedObject::StateSize, 1, CV_64F);
    for (size_t i = 0; i < before.size(); ++i)
    {
      mixed += mixing.at<double>(static_cast<int>(i), static_cast<int>(j)) * before[i].stateVector();
    }
    const cv::Mat predicted = after[j].stateVector();
    for (int k : kept)
    {
      EXPECT_NEAR(predicted.at<double>(k), mixed.at<double>(k), 1e-9) << "model " << j << ", state index " << k;
    }
  }
}

// Bug: all model states shared one predicted-measurement buffer, so every model reported the last model's (CTRV)
// prediction; fails on main 6b0a3156b.
TEST(MultiModelKalmanEstimatorTest, PredictKeepsPerModelPredictedMeasurements)
{
  // An accelerating, turning target makes CV, CA and CTRV predict different positions.
  Sensor camera;
  FilterRun run;
  run.feed(observe(Trajectory({.speed = 2.0, .box = kCar}).accelerate(1.0, 1.5).turn(0.6, 1.5).sample(10.0), camera));
  run.coast(0.5);

  // Reference: each filter's own predicted measurement, the mean that goes with its S in the model likelihood.
  // Reading the private mKalmanFilters and measurementEstimate requires -fno-access-control (test/CMakeLists.txt).
  const auto &filters = run.estimator.mKalmanFilters;
  double spread = 0.0;
  for (const auto &filter : filters)
  {
    spread = std::max(spread, cv::norm(filter->measurementEstimate, filters[0]->measurementEstimate, cv::NORM_INF));
  }
  ASSERT_GT(spread, 1e-2) << "models must predict different measurements";

  // The combined predicted measurement is the probability-weighted mean of the model predictions.
  const auto models = run.estimator.currentStates();
  const cv::Mat probability = run.estimator.getModelProbability();
  cv::Mat mixture = cv::Mat::zeros(rv::tracking::TrackedObject::MeasurementSize, 1, CV_64F);
  for (size_t i = 0; i < filters.size(); ++i)
  {
    EXPECT_LT(cv::norm(models[i].predictedMeasurementMean, filters[i]->measurementEstimate, cv::NORM_INF), 1e-9)
      << "model " << i;
    mixture += probability.at<double>(static_cast<int>(i)) * filters[i]->measurementEstimate;
  }
  EXPECT_LT(cv::norm(run.state().predictedMeasurementMean, mixture, cv::NORM_INF), 1e-9);
}

// Bug: MultiModelKalmanEstimator::initialize cleared only mSystemModels, so filters piled up; fails on main 6b0a3156b.
TEST(MultiModelKalmanEstimatorTest, ReinitializeDoesNotDuplicateFilters)
{
  const auto config = productionConfig();
  MultiModelKalmanEstimator estimator;
  for (int i = 0; i < 2; ++i)
  {
    estimator.initialize(makeDetection(0.0, 0.0, 0.0, kCar.length, kCar.width, kCar.height),
                         atSeconds(0.0),
                         config.mDefaultProcessNoise,
                         config.mDefaultMeasurementNoise,
                         config.mInitStateCovariance,
                         config.mMotionModels);
  }

  EXPECT_EQ(estimator.mSystemModels.size(), 3U);
  EXPECT_EQ(estimator.mKalmanFilters.size(), 3U);
  EXPECT_EQ(estimator.mSystemModelStates.size(), 3U);
}

TEST(MultiModelKalmanEstimatorTest, IsMoveOnly)
{
  // A copy would share the per-model filters and probability matrices with the original.
  static_assert(!std::is_copy_constructible_v<MultiModelKalmanEstimator>);
  static_assert(!std::is_copy_assignable_v<MultiModelKalmanEstimator>);
  static_assert(std::is_move_constructible_v<MultiModelKalmanEstimator>);
  static_assert(std::is_move_assignable_v<MultiModelKalmanEstimator>);
}

TEST(MultiModelKalmanEstimatorTest, InitialCovarianceUsesMeasurementNoiseAndCaps)
{
  // Measured states start at the measurement noise; init_state_covariance only caps the latent states.
  struct Case
  {
    double initStateCovariance;
    double velocity;
    double acceleration;
    double yaw;
    double yawRate;
  };
  constexpr double kMeasurementNoise = 0.2;

  for (const auto &expected : {Case{100.0, 0.05, 0.1, 0.05, 0.01}, Case{1e-3, 1e-3, 1e-3, 1e-3, 1e-3}})
  {
    SCOPED_TRACE("init_state_covariance " + std::to_string(expected.initStateCovariance));
    MultiModelKalmanEstimator estimator;
    estimator.initialize(makeDetection(0.0, 0.0, 0.0, kCar.length, kCar.width, kCar.height),
                         atSeconds(0.0),
                         1e-4,
                         kMeasurementNoise,
                         expected.initStateCovariance,
                         {MotionModel::CV});

    const cv::Mat diagonal = (cv::Mat_<double>(rv::tracking::TrackedObject::StateSize, 1) << kMeasurementNoise,
                              kMeasurementNoise,
                              expected.velocity,
                              expected.velocity,
                              expected.acceleration,
                              expected.acceleration,
                              kMeasurementNoise,
                              kMeasurementNoise,
                              kMeasurementNoise,
                              kMeasurementNoise,
                              expected.yaw,
                              expected.yawRate);
    EXPECT_DOUBLE_EQ(cv::norm(estimator.getKalmanFilterErrorCovariance(0), cv::Mat::diag(diagonal), cv::NORM_INF), 0.0);
  }
}

TEST(MultiModelKalmanEstimatorTest, KinematicProcessNoiseShape)
{
  // Velocity noise is aligned with the motion (along >> cross), scales linearly with dt and has a floor;
  // the acceleration block repeats it; position, z and size get no direct noise.
  struct Case
  {
    const char *name;
    double processNoise;
    double vx;
    double vy;
    double deltaT;
    double alongX;
    double alongY;
    double along;
    double cross;
    double yaw;
    double yawRate;
  };
  const Case cases[] = {
    {"stationary falls back to the x axis", 1e-4, 0.0, 0.0, 0.1, 1.0, 0.0, 1e-2, 1e-4, 1e-7, 1e-5},
    {"diagonal motion rotates the noise", 1e-4, 3.0, 4.0, 0.1, 0.6, 0.8, 6e-2, 1e-4, 1e-7, 1e-5},
    {"noise grows linearly with dt", 1e-4, 3.0, 4.0, 0.2, 0.6, 0.8, 12e-2, 2e-4, 2e-7, 2e-5},
    {"zero dt is treated as 1 ms", 1e-4, 0.0, 0.0, 0.0, 1.0, 0.0, 1e-4, 1e-6, 1e-9, 1e-7},
    {"tiny process noise hits the velocity floor", 1e-8, 0.0, 0.0, 0.1, 1.0, 0.0, 1e-4, 1e-6, 1e-11, 1e-9},
  };
  constexpr double kTolerance = 1e-12;

  for (const auto &testCase : cases)
  {
    SCOPED_TRACE(testCase.name);
    const cv::Mat noise = MultiModelKalmanEstimator::kinematicProcessNoiseCov(
      testCase.processNoise, testCase.vx, testCase.vy, testCase.deltaT);
    const cv::Mat velocityBlock = noise(cv::Rect(idx::Vx, idx::Vx, 2, 2));
    const cv::Mat accelerationBlock = noise(cv::Rect(idx::Ax, idx::Ax, 2, 2));
    const cv::Mat along = (cv::Mat_<double>(2, 1) << testCase.alongX, testCase.alongY);
    const cv::Mat cross = (cv::Mat_<double>(2, 1) << -testCase.alongY, testCase.alongX);

    EXPECT_LT(cv::norm(velocityBlock * along, testCase.along * along, cv::NORM_INF), kTolerance);
    EXPECT_LT(cv::norm(velocityBlock * cross, testCase.cross * cross, cv::NORM_INF), kTolerance);
    EXPECT_DOUBLE_EQ(cv::norm(accelerationBlock, velocityBlock, cv::NORM_INF), 0.0);
    EXPECT_NEAR(noise.at<double>(idx::Yaw, idx::Yaw), testCase.yaw, kTolerance);
    EXPECT_NEAR(noise.at<double>(idx::YawRate, idx::YawRate), testCase.yawRate, kTolerance);

    cv::Mat rest = noise.clone();
    rest(cv::Rect(idx::Vx, idx::Vx, 4, 4)).setTo(0.0);
    rest.at<double>(idx::Yaw, idx::Yaw) = 0.0;
    rest.at<double>(idx::YawRate, idx::YawRate) = 0.0;
    EXPECT_DOUBLE_EQ(cv::norm(rest, cv::NORM_INF), 0.0) << "position, z and size must get no direct noise";
  }
}

// Bug: all models were scored against one shared predicted measurement, so only S could separate them. With IMM mixing
// working, the models' S are nearly equal and the probabilities stayed near 1/3 for an accelerating target.
TEST(MultiModelKalmanEstimatorTest, AcceleratingTargetFavoursConstantAcceleration)
{
  struct MotionCase
  {
    const char *name;
    std::vector<TruthSample> truth;
    double from; // model probabilities are averaged over [from, to)
    double to;
    bool accelerating;
  };
  // Windows start once the probabilities have settled: after the speed pick-up at birth, about 1 s into braking.
  const MotionCase cases[] = {
    {.name = "pulling away",
     .truth = Trajectory({.box = kCar}).accelerate(2.0, 8.0).sample(10.0),
     .from = 2.0,
     .to = 8.0,
     .accelerating = true},
    {.name = "braking",
     .truth = Trajectory({.speed = 10.0, .box = kCar}).straight(3.0).accelerate(-4.0, 2.5).sample(10.0),
     .from = 4.0,
     .to = 5.5,
     .accelerating = true},
    {.name = "constant velocity",
     .truth = Trajectory({.speed = 5.0, .box = kCar}).straight(8.0).sample(10.0),
     .from = 3.0,
     .to = 8.0,
     .accelerating = false},
  };
  constexpr double kFavoured = 0.45;

  for (const auto &motion : cases)
  {
    SCOPED_TRACE(motion.name);
    Sensor camera{.positionNoise = 0.05};
    FilterRun run;
    run.feed(observe(between(motion.truth, 0.0, motion.from), camera));

    const auto window = observe(between(motion.truth, motion.from, motion.to), camera);
    cv::Mat probabilitySum = cv::Mat::zeros(static_cast<int>(rv::tracking::kProductionMotionModels.size()), 1, CV_64F);
    for (const auto &observation : window)
    {
      run.feed({observation});
      probabilitySum += run.estimator.getModelProbability();
    }
    const cv::Mat mean = probabilitySum / static_cast<double>(window.size());
    const double constantAcceleration = mean.at<double>(modelIndex(MotionModel::CA));

    if (motion.accelerating)
    {
      EXPECT_GE(constantAcceleration, kFavoured) << "mean model probabilities " << mean.t();
      EXPECT_GT(constantAcceleration, mean.at<double>(modelIndex(MotionModel::CV)));
      EXPECT_GT(constantAcceleration, mean.at<double>(modelIndex(MotionModel::CTRV)));
    }
    else
    {
      EXPECT_LT(constantAcceleration, kFavoured) << "mean model probabilities " << mean.t();
    }
  }
}
