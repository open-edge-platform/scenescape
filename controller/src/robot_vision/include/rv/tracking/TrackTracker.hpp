// SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include "rv/tracking/TrackManager.hpp"
#include "rv/tracking/TrackedObject.hpp"

#include <chrono>
#include <vector>

namespace rv {
namespace tracking {

class TrackTracker
{
public:
  TrackTracker()
    : mTrackManager(false)
  {
  }

  TrackTracker(TrackManagerConfig const &config)
    : mTrackManager(config, false)
  {
  }

  TrackTracker(const TrackTracker &) = delete;
  TrackTracker &operator=(const TrackTracker &) = delete;

  /**
   * @brief Sets the list of measurements and triggers the tracking procedure
   *
   */
  void track(std::vector<tracking::TrackedObject> objects, const std::chrono::system_clock::time_point &timestamp);

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
   * @brief Returns current timestamp
   *
   */
  std::chrono::system_clock::time_point getTimestamp()
  {
    return mLastTimestamp;
  }

private:
  TrackManager mTrackManager;
  std::chrono::system_clock::time_point mLastTimestamp;
};
} // namespace tracking
} // namespace rv
