// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <cmath>
#include <cstdint>
#include <opencv2/core.hpp>
#include <opencv2/tracking/kalman_filters.hpp>
#include <vector>
#include <chrono>
#include "rv/Utils.hpp"
#include "rv/tracking/TrackedObject.hpp"
#include "rv/tracking/UnscentedKalmanFilter.hpp"

namespace rv {
namespace tracking {

enum MotionModel{
  CV,
  CA,
  CP,
  CTRV
};

class MultiModelKalmanEstimator
{
public:
  MultiModelKalmanEstimator(double alpha = 1.0, double beta = 2.0);

  /**
   * @brief Initialize the tracker with the current state
   */
  void initialize(TrackedObject track, const std::chrono::system_clock::time_point &timestamp, double processNoise = 1e-4, double measurementNoise = 1e-2, double initStateCovariance = 1., const std::vector<MotionModel> &motionModels = std::vector<MotionModel>());

  /**
   * @brief Set measurement and trigger tracking procedure
   *
   */
  void track(const TrackedObject &measurement, const std::chrono::system_clock::time_point &timestamp)
  {
    predict(timestamp);
    correct(measurement);

    mLastTimestamp = timestamp;
  }

  /**
   * @brief Trigger the state prediction step
   */
  void predict(const std::chrono::system_clock::time_point &timestamp);

  /**
   * @brief Trigger the state prediction step
   */
  void predict(const double deltaT);

  /**
   * @brief Correct the current state by measuring the current object state
   * The input is a measurement of the current state of the object.
   */
  void correct(const TrackedObject &measurement);

  /**
   * @brief Const access to the current state
   */
  TrackedObject currentState() const
  {
    return mCurrentState;
  }

  std::vector<TrackedObject> currentStates() const
  {
    return mSystemModelStates;
  }

  std::chrono::system_clock::time_point getTimestamp()
  {
    return mLastTimestamp;
  }

  void setTimestamp(std::chrono::system_clock::time_point timestamp)
  {
    mLastTimestamp = timestamp;
  }

  cv::Mat getKalmanFilterMeasurementCovariance(std::size_t j) const;
  cv::Mat getKalmanFilterErrorCovariance(std::size_t j) const;

  cv::Mat getModelProbability() const;
  cv::Mat getTransitionProbability() const;
  cv::Mat getConditionalProbability() const;

private:
  TrackedObject mCurrentState;
  std::chrono::system_clock::time_point mLastTimestamp;

  /**
   * @brief Trigger the state prediction step
   */
  void predictState(const double deltaT);

  /**
   * @brief Trigger the state prediction step
   */
  void singleModelPredict(double deltaT);

  /**
   * @brief Correct the current state by measuring the current object state
   * The input is a measurement of the current state of the object.
   */
  void singleModelCorrect(const TrackedObject &measurement);

  /**
   * @brief Combines probability coming from the three models and calculates the conditional probability
   */
  static void combiningProbability(cv::Mat const &transitionProbability,
                                   cv::Mat const &modelProbability,
                                   cv::Mat &conditionalProbablity);

  /**
   * @brief Calculates the Covariance and the State Estimates of the three models
   */
  static void interaction(std::vector<cv::Mat> const &states,
                          std::vector<cv::Mat> const &processNoiseCovariance,
                          cv::Mat const &conditionalProbablity,
                          std::vector<cv::Mat> &covarianceEstimate,
                          std::vector<cv::Mat> &stateEstimates);

  /**
   * @brief Updates the Model Probability to be used in the correction step
   */
  static void updateModelProbability(cv::Mat const &measurement,
                                     std::vector<cv::Mat> const &predictedMeasurements,
                                     std::vector<cv::Mat> const &measurementNoiseCovariance,
                                     cv::Mat &modelProbability,
                                     double maxProbability,
                                     double minProbability);

  /**
    * @brief Calculates a combined state estimate and a covariance estimate after the prediction and correction step is
   * done
    */
  static void combineStatesAndCovariances(std::vector<cv::Mat> const &states,
                                          std::vector<cv::Mat> const &covariances,
                                          cv::Mat const &modelProbability,
                                          cv::Mat &combinedState,
                                          cv::Mat &combinedCovariance);

  std::vector<TrackedObject> mSystemModelStates;

  int32_t mDP{0}; // Dimension of state vector
  int32_t mMP{0}; // Dimension of measurement vector
  int32_t mCP{0}; // Dimension of control vector

  double mAlpha{0.0}; // sigma points spread
  double mBeta{0.0};  // 2.0 for Gaussian distributions
  double mKappa{0.0}; // 3 - L

  std::vector<cv::Ptr<cv::detail::tracking::UnscentedKalmanFilterMod>> mKalmanFilters;
  std::vector<cv::Ptr<cv::detail::tracking::UkfSystemModel>> mSystemModels;

  double mMaxProbability{1.};
  double mMinProbability{0.95};

  // Probability of the track of transitioning from the ith model to the jth model
  cv::Mat mTransitionProbability;

  // Probability of the track behaving like the ith model
  cv::Mat mModelProbability;

  std::size_t mNumberOfModels{0u};
};
} // namespace tracking
} // namespace rv
