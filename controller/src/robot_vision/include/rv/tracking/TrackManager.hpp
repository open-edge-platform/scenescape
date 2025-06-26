// SPDX-FileCopyrightText: 2017 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <memory>
#include <stdint.h>
#include <string>
#include <unordered_map>
#include <chrono>
#include <vector>
#include "rv/tracking/MultiModelKalmanEstimator.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

struct TrackManagerConfig
{
  uint32_t mNonMeasurementFramesDynamic{15};
  uint32_t mNonMeasurementFramesStatic{30};
  uint32_t mMaxNumberOfUnreliableFrames{2};
  uint32_t mReactivationFrames{1};

  double mNonMeasurementTimeDynamic{0.2666};
  double mNonMeasurementTimeStatic{0.5333};
  double mMaxUnreliableTime{0.3333};

  double mDefaultProcessNoise{1e-3};
  double mDefaultMeasurementNoise{1e-2};
  double mInitStateCovariance{1.};

  std::vector<MotionModel> mMotionModels{MotionModel::CV, MotionModel::CA, MotionModel::CTRV};

  std::string toString() const
  {
    std::string motionModelsText = " motion_models:";
    for (auto const &motionModel: mMotionModels)
    {
      motionModelsText += " ";

      switch (motionModel)
      {
        case MotionModel::CV:
          motionModelsText += "CV";
          break;
        case MotionModel::CA:
          motionModelsText += "CA";
          break;
        case MotionModel::CTRV:
          motionModelsText += "CTRV";
          break;
        default:
          motionModelsText += "Unknown";
      }
    }

    return "TrackManagerConfig( non_measurement_time_dynamic:" + std::to_string(mNonMeasurementTimeDynamic)
      + ", non_measurement_time_static:" + std::to_string(mNonMeasurementTimeStatic) + ", max_unreliable_time:"
      + std::to_string(mMaxUnreliableTime) + ", reactivation_frames:" + std::to_string(mReactivationFrames)
      + ", default_process_noise:" + std::to_string(mDefaultProcessNoise) + ", default_measurement_noise:"
      + std::to_string(mDefaultMeasurementNoise) + ", init_state_covariance:"
      + std::to_string(mInitStateCovariance) + motionModelsText + ")";
  }
};

/**
 * @brief TrackManager: Provides interfaces to create new tracks and assign measurements to existing tracks
 *
 * The TrackManager module maintains tracks as a map of <Id, KalmanEstimator>
 * It also provides the functionality of Reliable/unreliable track, this reduces the number of false positives
 * and allows the user to work only with the reliable objects. An object becomes reliable when at least
 * mMaxNumberOfUnreliableFrames frames have been measured.
 */
class TrackManager
{
public:
  TrackManager()
  {
  }

  TrackManager(TrackManagerConfig const &trackManagerConfig)
    : mConfig(trackManagerConfig)
  {
  }

  TrackManager(bool autoIdGeneration)
    : mAutoIdGeneration(autoIdGeneration)
  {
  }

  TrackManager(TrackManagerConfig const &trackManagerConfig, bool autoIdGeneration)
    : mConfig(trackManagerConfig)
    , mAutoIdGeneration(autoIdGeneration)
  {
  }

  /**
   * @brief Create a new track with the object information
   *
   */
  Id createTrack(TrackedObject object, const std::chrono::system_clock::time_point &timestamp);

  /**
   * @brief Trigger state estimation update
   *
   */
  void predict(const std::chrono::system_clock::time_point &timestamp);

  /**
   * @brief Trigger state estimation update
   *
   */
  void predict(double deltaT);

  /**
   * @brief Assign a measurement to an KalmanEstimator.
   *
   * The measurement won't be applied inmediately, it will be applied during the next correct measurement step
   */
  void setMeasurement(const Id &id, const TrackedObject &measurement);

  /**
   * @brief Triggers the correct measurements step
   *
   */
  void correct();

  /**
   * @brief Access a specific track
   *
   */
  TrackedObject getTrack(const Id &id);

  /**
   * @brief Access a specific kalman estimator
   *
   */
  MultiModelKalmanEstimator getKalmanEstimator(const Id &id);

  /**
   * @brief Returns a list of tracked objects states
   *
   */
  std::vector<TrackedObject> getTracks();
  std::vector<TrackedObject> getReliableTracks();
  std::vector<TrackedObject> getUnreliableTracks();
  std::vector<TrackedObject> getSuspendedTracks();
  std::vector<TrackedObject> getDriftingTracks();

  /**
   * @brief Check wether the given Id is registered in the track manager
   *
   * @param id
   * @return true
   * @return false
   */
  bool hasId(const Id &id);

  /**
   * @brief Delete an existing track
   */
  void deleteTrack(const Id &id);

  /**
   * @brief Sets a track into suspended mode
   */
  void suspendTrack(const Id &id);

  /**
   * @brief Moves a track from suspended mode into non reliable tracks
   */
  void reactivateTrack(const Id &id);

  /**
   * @brief Track has been measured for at least mMaxNumberOfUnreliableFrames
   */
  bool isReliable(const Id &id);

  /**
   * @brief Track is in the mSuspendedKalmanEstimators map
   */
  bool isSuspended(const Id &id);

  /**
   * @brief Update frame_based_parameters based on the input frame_rate
   */
  void updateTrackerConfig(int camera_frame_rate);

  inline TrackManagerConfig getConfig()
  {
    return mConfig;
  }

private:
  std::unordered_map<Id, MultiModelKalmanEstimator> mKalmanEstimators;
  std::unordered_map<Id, MultiModelKalmanEstimator> mSuspendedKalmanEstimators;
  std::unordered_map<Id, TrackedObject> mMeasurementMap;
  std::unordered_map<Id, uint32_t> mNonMeasurementFrames;
  std::unordered_map<Id, uint32_t> mNumberOfTrackedFrames;

  Id mCurrentId = 0;

  bool mAutoIdGeneration{true};

  TrackManagerConfig mConfig;
};

} // namespace tracking
} // namespace rv
