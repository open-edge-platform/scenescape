// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iterator>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/MultiModelKalmanEstimator.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/Scenario.hpp"

namespace {

using namespace rv::tracking::test;
using rv::tracking::MotionModel;
using rv::tracking::MultiModelKalmanEstimator;

struct CorrectedEstimate
{
  rv::tracking::TrackedObject state;
  cv::Mat modelProbability;
};

// One predict + correct from rest, with the detection 1 m along x carrying the given R.
CorrectedEstimate correctWithNoise(const std::optional<rv::tracking::TrackedObject::MeasurementMatrix> &noise,
                                   const std::vector<MotionModel> &models)
{
  rv::tracking::TrackedObject object;
  object.length = object.width = object.height = 1.0;

  MultiModelKalmanEstimator estimator;
  estimator.initialize(object,
                       std::chrono::system_clock::time_point{},
                       rv::tracking::kProductionProcessNoise,
                       rv::tracking::kProductionMeasurementNoise,
                       rv::tracking::kProductionInitStateCovariance,
                       models);
  estimator.predict(0.1);

  rv::tracking::TrackedObject measurement = object;
  measurement.x = 1.0;
  measurement.measurementNoiseCov = noise;
  estimator.correct(measurement);
  return {estimator.currentState(), estimator.getModelProbability()};
}

const std::vector<std::vector<MotionModel>> kSingleAndProductionModels{{MotionModel::CV},
                                                                       rv::tracking::kProductionMotionModels};

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
                              expected.velocity,
                              kMeasurementNoise,
                              kMeasurementNoise,
                              kMeasurementNoise,
                              expected.yaw,
                              expected.yawRate);
    EXPECT_DOUBLE_EQ(cv::norm(estimator.getKalmanFilterErrorCovariance(0), cv::Mat::diag(diagonal), cv::NORM_INF), 0.0);
  }
}

TEST(MultiModelKalmanEstimatorTest, ProcessNoisePerModelShape)
{
  // Velocity noise is aligned with the motion (along >> cross), scales linearly with dt and has a floor. CA repeats it
  // on the acceleration and CTRV adds turn-rate noise; states a model resets to 0 get a small floor. vz gets the
  // unscaled velocity noise in every model. Position, z and size get no direct noise.
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
    double vz;
    double yaw;
    double turnRate; // CTRV only
    double reset;    // states the model resets to 0
  };
  const Case cases[] = {
    {"stationary falls back to the x axis", 1e-4, 0.0, 0.0, 0.1, 1.0, 0.0, 1e-2, 1e-4, 1e-2, 1e-7, 1e-2, 1e-7},
    {"diagonal motion rotates the noise", 1e-4, 3.0, 4.0, 0.1, 0.6, 0.8, 6e-2, 1e-4, 1e-2, 1e-7, 1e-2, 1e-7},
    {"noise grows linearly with dt", 1e-4, 3.0, 4.0, 0.2, 0.6, 0.8, 12e-2, 2e-4, 2e-2, 2e-7, 2e-2, 2e-7},
    {"zero dt is treated as 1 ms", 1e-4, 0.0, 0.0, 0.0, 1.0, 0.0, 1e-4, 1e-6, 1e-4, 1e-9, 1e-4, 1e-9},
    {"tiny process noise hits the velocity and turn-rate floor",
     1e-8,
     0.0,
     0.0,
     0.1,
     1.0,
     0.0,
     1e-4,
     1e-6,
     1e-4,
     1e-11,
     1e-4,
     1e-7},
  };
  constexpr double kTolerance = 1e-12;

  for (const auto &testCase : cases)
  {
    for (const auto &[model, modelName] :
         {std::pair{MotionModel::CV, "CV"}, std::pair{MotionModel::CA, "CA"}, std::pair{MotionModel::CTRV, "CTRV"}})
    {
      SCOPED_TRACE(std::string(modelName) + ": " + testCase.name);
      const cv::Mat noise = MultiModelKalmanEstimator::processNoiseCov(
        model, testCase.processNoise, testCase.vx, testCase.vy, testCase.deltaT);
      const cv::Mat velocityBlock = noise(cv::Rect(idx::Vx, idx::Vx, 2, 2));
      const cv::Mat accelerationBlock = noise(cv::Rect(idx::Ax, idx::Ax, 2, 2));
      const cv::Mat along = (cv::Mat_<double>(2, 1) << testCase.alongX, testCase.alongY);
      const cv::Mat cross = (cv::Mat_<double>(2, 1) << -testCase.alongY, testCase.alongX);

      EXPECT_LT(cv::norm(velocityBlock * along, testCase.along * along, cv::NORM_INF), kTolerance);
      EXPECT_LT(cv::norm(velocityBlock * cross, testCase.cross * cross, cv::NORM_INF), kTolerance);
      EXPECT_NEAR(noise.at<double>(idx::Vz, idx::Vz), testCase.vz, kTolerance);
      EXPECT_NEAR(noise.at<double>(idx::Yaw, idx::Yaw), testCase.yaw, kTolerance);

      const cv::Mat expectedAcceleration
        = model == MotionModel::CA ? velocityBlock : cv::Mat(cv::Mat::eye(2, 2, CV_64F) * testCase.reset);
      const double expectedTurnRate = model == MotionModel::CTRV ? testCase.turnRate : testCase.reset;
      EXPECT_LT(cv::norm(accelerationBlock, expectedAcceleration, cv::NORM_INF), kTolerance);
      EXPECT_NEAR(noise.at<double>(idx::YawRate, idx::YawRate), expectedTurnRate, kTolerance);

      cv::Mat rest = noise.clone();
      rest(cv::Rect(idx::Vx, idx::Vx, 2, 2)).setTo(0.0);
      rest(cv::Rect(idx::Ax, idx::Ax, 2, 2)).setTo(0.0);
      rest.at<double>(idx::Vz, idx::Vz) = 0.0;
      rest.at<double>(idx::Yaw, idx::Yaw) = 0.0;
      rest.at<double>(idx::YawRate, idx::YawRate) = 0.0;
      EXPECT_DOUBLE_EQ(cv::norm(rest, cv::NORM_INF), 0.0) << "position, z and size must get no direct noise";
    }
  }
}

TEST(MultiModelKalmanEstimatorTest, PredictAppliesPerModelProcessNoise)
{
  constexpr double kDeltaT = 0.1;
  const auto config = productionConfig();
  const auto truth = Trajectory({.speed = 2.0, .box = kCar}).accelerate(1.0, 1.5).turn(0.6, 1.5).sample(10.0);

  // An accelerating, turning target makes the models' velocities differ. Each model's noise follows its own mixed
  // velocity, built as in PredictMixesModelStates.
  Sensor camera;
  FilterRun run(config);
  run.feed(observe(truth, camera));
  const auto before = run.estimator.currentStates();
  const cv::Mat mixing = run.estimator.getConditionalProbability();
  run.estimator.predict(kDeltaT);

  double spread = 0.0;
  for (const auto &state : before)
  {
    spread = std::max(spread, std::hypot(state.vx - before[0].vx, state.vy - before[0].vy));
  }
  ASSERT_GT(spread, 1e-2) << "models must disagree on the velocity";
  for (size_t j = 0; j < before.size(); ++j)
  {
    double vx = 0.0;
    double vy = 0.0;
    for (size_t i = 0; i < before.size(); ++i)
    {
      vx += mixing.at<double>(static_cast<int>(i), static_cast<int>(j)) * before[i].vx;
      vy += mixing.at<double>(static_cast<int>(i), static_cast<int>(j)) * before[i].vy;
    }
    const cv::Mat expected = MultiModelKalmanEstimator::processNoiseCov(
      config.mMotionModels[j], config.mDefaultProcessNoise, vx, vy, kDeltaT);
    EXPECT_LT(cv::norm(run.estimator.mKalmanFilters[j]->getProcessNoiseCov(), expected, cv::NORM_INF), 1e-12)
      << "model " << j;
  }

  // A single model uses its own state.
  auto singleConfig = config;
  singleConfig.mMotionModels = {MotionModel::CV};
  Sensor singleCamera;
  FilterRun single(singleConfig);
  single.feed(observe(truth, singleCamera));
  const auto state = single.state();
  single.estimator.predict(kDeltaT);
  const cv::Mat expected = MultiModelKalmanEstimator::processNoiseCov(
    MotionModel::CV, config.mDefaultProcessNoise, state.vx, state.vy, kDeltaT);
  EXPECT_LT(cv::norm(single.estimator.mKalmanFilters[0]->getProcessNoiseCov(), expected, cv::NORM_INF), 1e-12);

  // Without a model list the estimator runs CTRV, CV and CA, in that order.
  MultiModelKalmanEstimator defaults;
  defaults.initialize(makeDetection(truth[0]),
                      atSeconds(0.0),
                      config.mDefaultProcessNoise,
                      config.mDefaultMeasurementNoise,
                      config.mInitStateCovariance);
  defaults.predict(kDeltaT);
  const MotionModel defaultModels[] = {MotionModel::CTRV, MotionModel::CV, MotionModel::CA};
  ASSERT_EQ(defaults.mKalmanFilters.size(), std::size(defaultModels));
  for (size_t i = 0; i < std::size(defaultModels); ++i)
  {
    const cv::Mat stationary
      = MultiModelKalmanEstimator::processNoiseCov(defaultModels[i], config.mDefaultProcessNoise, 0.0, 0.0, kDeltaT);
    EXPECT_LT(cv::norm(defaults.mKalmanFilters[i]->getProcessNoiseCov(), stationary, cv::NORM_INF), 1e-12)
      << "model " << i;
  }
}

TEST(MultiModelKalmanEstimatorTest, PredictIntegratesVzWithoutMeasurement)
{
  rv::tracking::MultiModelKalmanEstimator estimator;
  rv::tracking::TrackedObject seed;
  seed.x = 0.0;
  seed.y = 0.0;
  seed.z = 2.5;
  seed.vz = 0.5;
  seed.yaw = 0.3;
  seed.length = 0.5;
  seed.width = 0.5;
  seed.height = 1.8;

  auto timestamp = std::chrono::system_clock::now();
  estimator.initialize(seed, timestamp, 1e-5, 1e-3, 1.0, {rv::tracking::MotionModel::CV});
  constexpr double coastDt = 2.0;
  estimator.predict(timestamp + std::chrono::seconds(2));
  auto state = estimator.currentState();
  EXPECT_NEAR(state.z, 2.5 + 0.5 * coastDt, 0.05);
  EXPECT_NEAR(state.vz, 0.5, 0.05);
  EXPECT_NEAR(state.yaw, 0.3, 1e-3);
}

TEST(MultiModelKalmanEstimatorTest, CorrectUsesPerMeasurementNoise)
{
  for (const auto &models : kSingleAndProductionModels)
  {
    SCOPED_TRACE(models.size() == 1 ? "single model" : "production IMM");
    const auto legacy = correctWithNoise(std::nullopt, models);
    const auto explicitDefault = correctWithNoise(diagonalMeasurementNoise(0.2, 0.2, 0.2), models);
    const auto sharp = correctWithNoise(diagonalMeasurementNoise(1e-4, 0.2, 0.2), models);
    const auto blurry = correctWithNoise(diagonalMeasurementNoise(100.0, 0.2, 0.2), models);

    // An explicit default R reproduces the update without R, model probabilities included.
    EXPECT_NEAR(explicitDefault.state.x, legacy.state.x, 1e-12);
    EXPECT_LT(cv::norm(explicitDefault.modelProbability, legacy.modelProbability, cv::NORM_INF), 1e-12);
    EXPECT_GT(sharp.state.x, 0.95);
    EXPECT_LT(blurry.state.x, 0.05);
    EXPECT_GT(sharp.state.x, legacy.state.x);
    EXPECT_LT(blurry.state.x, legacy.state.x);
  }
}

TEST(MultiModelKalmanEstimatorTest, CorrectWithoutNoiseAfterCorrectWithNoiseUsesDefaultR)
{
  // Two corrections without a predict between them: the second, without R, must not reuse the first one's R.
  for (const auto &models : kSingleAndProductionModels)
  {
    SCOPED_TRACE(models.size() == 1 ? "single model" : "production IMM");
    auto correctTwice = [&](const std::optional<rv::tracking::TrackedObject::MeasurementMatrix> &secondNoise) {
      rv::tracking::TrackedObject object;
      object.length = object.width = object.height = 1.0;
      MultiModelKalmanEstimator estimator;
      estimator.initialize(object, std::chrono::system_clock::time_point{}, 1e-4, 0.2, 1.0, models);
      estimator.predict(0.1);

      auto first = object;
      first.x = 1.0;
      first.measurementNoiseCov = diagonalMeasurementNoise(1e-4, 0.2, 0.2);
      estimator.correct(first);
      auto second = object;
      second.y = 1.0;
      second.measurementNoiseCov = secondNoise;
      estimator.correct(second);
      return CorrectedEstimate{estimator.currentState(), estimator.getModelProbability()};
    };

    const auto withoutR = correctTwice(std::nullopt);
    const auto explicitDefault = correctTwice(diagonalMeasurementNoise(0.2, 0.2, 0.2));
    EXPECT_NEAR(withoutR.state.y, explicitDefault.state.y, 1e-12);
    EXPECT_LT(
      cv::norm(cv::Mat(withoutR.state.errorCovariance), cv::Mat(explicitDefault.state.errorCovariance), cv::NORM_INF),
      1e-12);
    EXPECT_LT(cv::norm(withoutR.modelProbability, explicitDefault.modelProbability, cv::NORM_INF), 1e-12);
  }
}

TEST(MultiModelKalmanEstimatorTest, ModelProbabilityUsesPerMeasurementNoise)
{
  // The IMM likelihood must use S = H P H^T + R_detection, not the default S from predict.
  const auto legacy = correctWithNoise(std::nullopt, rv::tracking::kProductionMotionModels);
  const auto sharp = correctWithNoise(diagonalMeasurementNoise(1e-4, 0.2, 0.2), rv::tracking::kProductionMotionModels);

  EXPECT_GT(cv::norm(sharp.modelProbability, legacy.modelProbability, cv::NORM_INF), 1e-6);
}

TEST(MultiModelKalmanEstimatorTest, PredictPublishesMeasurementCovarianceWithoutNoise)
{
  for (const auto &models : kSingleAndProductionModels)
  {
    SCOPED_TRACE(models.size() == 1 ? "single model" : "production IMM");
    rv::tracking::TrackedObject object;
    object.length = object.width = object.height = 1.0;

    MultiModelKalmanEstimator estimator;
    estimator.initialize(object, std::chrono::system_clock::time_point{}, 1e-4, 0.2, 1.0, models);
    estimator.predict(0.1);
    auto measurement = object;
    measurement.x = 0.3;
    estimator.correct(measurement);
    estimator.predict(0.1);
    const auto state = estimator.currentState();

    // Same H P H^T as the UKF of the model chosen for association (highest probability, first on ties).
    cv::Point bestModel;
    cv::minMaxLoc(estimator.getModelProbability(), nullptr, nullptr, nullptr, &bestModel);
    const cv::Mat expected = estimator.mKalmanFilters[bestModel.y]->getPredictedMeasurementCovWithoutNoise();
    EXPECT_LT(cv::norm(cv::Mat(state.predictedStateMeasurementCov), expected, cv::NORM_INF), 1e-12);
    // S = H P H^T + R_default.
    const rv::tracking::TrackedObject::MeasurementMatrix noise
      = state.predictedMeasurementCov - state.predictedStateMeasurementCov;
    EXPECT_LT(cv::norm(noise, rv::tracking::TrackedObject::MeasurementMatrix::eye() * 0.2, cv::NORM_INF), 1e-12);
    EXPECT_GT(minEigenvalue(cv::Mat(state.predictedStateMeasurementCov)), 0.0);
  }
}

TEST(MultiModelKalmanEstimatorTest, InitializeSeedsErrorCovarianceFromMeasurementNoise)
{
  using rv::tracking::MeasurementIndex;
  using rv::tracking::StateIndex;

  rv::tracking::TrackedObject object;
  object.length = object.width = object.height = 1.0;
  object.measurementNoiseCov = diagonalMeasurementNoise(4.0, 0.5, 0.3);
  (*object.measurementNoiseCov)(MeasurementIndex::X, MeasurementIndex::Y) = 1.0;
  (*object.measurementNoiseCov)(MeasurementIndex::Y, MeasurementIndex::X) = 1.0;
  (*object.measurementNoiseCov)(MeasurementIndex::HEIGHT, MeasurementIndex::HEIGHT) = 0.7;

  MultiModelKalmanEstimator estimator;
  estimator.initialize(object, std::chrono::system_clock::time_point{}, 1e-4, 0.2, 1.0, {MotionModel::CV});

  const cv::Mat P = estimator.getKalmanFilterErrorCovariance(0);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::X, StateIndex::X), 4.0);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::Y, StateIndex::Y), 0.5);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::Z, StateIndex::Z), 0.3);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::X, StateIndex::Y), 1.0);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::HEIGHT, StateIndex::HEIGHT), 0.7);
  // Latent states keep their capped priors; the detection's yaw variance does not seed P.
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::VX, StateIndex::VX), 0.05);
  EXPECT_DOUBLE_EQ(P.at<double>(StateIndex::YAW, StateIndex::YAW), 0.05);
  EXPECT_FALSE(estimator.currentState().measurementNoiseCov) << "tracks must not carry a detection R";
}
