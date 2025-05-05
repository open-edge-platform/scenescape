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

#include <algorithm>
#include "rv/Utils.hpp"
#include "rv/tracking/TrackTracker.hpp"
#include "rv/tracking/Classification.hpp"

namespace rv {
namespace tracking {

void TrackTracker::track(std::vector<tracking::TrackedObject> trackedObjects, const std::chrono::system_clock::time_point &timestamp)
{
  if (trackedObjects.empty())
  {
    mTrackManager.predict(timestamp);
    mTrackManager.correct();
    mLastTimestamp = timestamp;
    return;
  }
  std::vector<tracking::TrackedObject> tracks; // temporary vector used to hold the tracks at every match stage

  // 1. - Predict
  mTrackManager.predict(timestamp);

  // 2. - Update measurements - set measurement
  for (const auto &trackedObject : trackedObjects)
  {
    if (mTrackManager.hasId(trackedObject.id))
    {
      mTrackManager.setMeasurement(trackedObject.id, trackedObject);
    }
  }

  // Update measurements - Correct measurements
  mTrackManager.correct();

  // 3. - Create new tracks
  for (const auto &trackedObject : trackedObjects)
  {
    if (!mTrackManager.hasId(trackedObject.id))
    {
      mTrackManager.createTrack(trackedObject, timestamp);
    }
  }

  mLastTimestamp = timestamp;
}
} // namespace tracking
} // namespace rv
