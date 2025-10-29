// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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
   * @brief Sets the list of measurements from multiple cameras and triggers the tracking procedure
   * @param objectsPerCamera Vector of vectors, where each inner vector contains objects from one camera
   * @param timestamp Time point for this tracking iteration
   * @param scoreThreshold Threshold for object scoring
   */
  void track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
             const std::chrono::system_clock::time_point &timestamp,
             double scoreThreshold = 0.50);

  /**
   * @brief Sets the batched list of measurements from multiple cameras and triggers the tracking procedure
   * @param objectsPerCamera Vector of vectors, where each inner vector contains objects from one camera
   * @param timestamp Time point for this tracking iteration
   * @param distanceType Distance type for matching
   * @param distanceThreshold Distance threshold for matching
   * @param scoreThreshold Threshold for object scoring
   */
  void track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
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

  /**
   * @brief Helper function to match tracks with objects and update measurements
   *
   * @param tracks Vector of tracks to match
   * @param objects Vector of objects to match
   * @param distanceType Distance calculation method
   * @param distanceThreshold Maximum distance for matching
   * @param[out] unassignedObjects Indices of objects that were not assigned to any track
   * @return Updated vector of unassigned tracks
   */
  std::vector<tracking::TrackedObject> matchAndAssignMeasurements(
    const std::vector<tracking::TrackedObject> &tracks,
    const std::vector<tracking::TrackedObject> &objects,
    const DistanceType &distanceType,
    double distanceThreshold,
    std::vector<size_t> &unassignedObjects);

  /**
   * @brief Helper function to match tracks with objects batched from multiple cameras
   * and update measurements
   *
   * @param tracks Vector of tracks to match
   * @param[inout] objects Vector of vectors, where each inner vector contains objects from one camera
            assigned objects will be removed from each inner vector
   * @param distanceType Distance calculation method
   * @param distanceThreshold Maximum distance for matching
   * @return Updated vector of unassigned tracks
   */
  std::vector<tracking::TrackedObject> matchAndAssignMeasurements(
    const std::vector<tracking::TrackedObject> &tracks,
    std::vector<std::vector<tracking::TrackedObject>> &objectsPerCamera,
    const DistanceType &distanceType,
    double distanceThreshold);

};
} // namespace tracking
} // namespace rv
