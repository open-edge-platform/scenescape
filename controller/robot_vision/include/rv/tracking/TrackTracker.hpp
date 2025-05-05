// ----------------- BEGIN LICENSE BLOCK ---------------------------------
//
// INTEL CONFIDENTIAL
//
// Copyright (c) 2021-2023 Intel Corporation
//
// This software and the related documents are Intel copyrighted materials, and
// your use of them is governed by the express license under which they were
// provided to you (License). Unless the License provides otherwise, you may not
// use, modify, copy, publish, distribute, disclose or transmit this software or
// the related documents without Intel's prior written permission.
//
// This software and the related documents are provided as is, with no express or
// implied warranties, other than those that are expressly stated in the License.
//
// ----------------- END LICENSE BLOCK -----------------------------------

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
