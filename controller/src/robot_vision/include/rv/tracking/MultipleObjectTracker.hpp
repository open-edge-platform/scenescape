// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include "rv/tracking/ObjectMatching.hpp"
#include "rv/tracking/TrackManager.hpp"
#include "rv/tracking/TrackedObject.hpp"

#include <chrono>
#include <vector>

namespace rv {
namespace tracking {

class MultipleObjectTracker
{
public:
  MultipleObjectTracker()
  : mDistanceType(DistanceType::MultiClassEuclidean), mDistanceThreshold(5.0)
  {
  }

  MultipleObjectTracker(TrackManagerConfig const &config)
    : mTrackManager(config), mDistanceType(DistanceType::MultiClassEuclidean), mDistanceThreshold(5.0)
  {
  }

  MultipleObjectTracker(TrackManagerConfig const &config, const DistanceType & distanceType, double distanceThreshold)
  : mTrackManager(config), mDistanceType(distanceType),  mDistanceThreshold(distanceThreshold)
  {
  }

  MultipleObjectTracker(const MultipleObjectTracker &) = delete;
  MultipleObjectTracker &operator=(const MultipleObjectTracker &) = delete;
  /**
   * @brief Sets the list of measurements and triggers the tracking procedure
   *
   */
  void track(std::vector<tracking::TrackedObject> objects,
             const std::chrono::system_clock::time_point &timestamp,
             double scoreThreshold = 0.50);

  /**
   * @brief Sets the list of measurements and triggers the tracking procedure
   *
   */
  void track(std::vector<tracking::TrackedObject> objects,
             const std::chrono::system_clock::time_point &timestamp,
             const DistanceType & distanceType, double distanceThreshold,
             double scoreThreshold = 0.50);

  /**
   * @brief Returns a list of reliable tracked objects states
   *
   */
  inline std::vector<TrackedObject> getReliableTracks()
  {
    return mTrackManager.getReliableTracks();
  }

  /**
   * @brief Returns a the list of all active tracked objects
   *
   */
  inline std::vector<TrackedObject> getTracks()
  {
    return mTrackManager.getTracks();
  }

  /**
   * @brief Updates the frame-based params in mTrackManager
   *
   */
  inline void updateTrackerParams(int camera_frame_rate)
  {
    mTrackManager.updateTrackerConfig(camera_frame_rate);
  }

  /**
   * @brief Returns current timestamp
   *
   */
  std::chrono::system_clock::time_point getTimestamp()
  {
    return mLastTimestamp;
  }

private:
  TrackManager mTrackManager;
  DistanceType mDistanceType;
  double mDistanceThreshold{5.0};

  std::chrono::system_clock::time_point mLastTimestamp;
};
} // namespace tracking
} // namespace rv
