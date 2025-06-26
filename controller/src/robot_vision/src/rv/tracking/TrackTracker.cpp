// SPDX-FileCopyrightText: 2021 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

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
