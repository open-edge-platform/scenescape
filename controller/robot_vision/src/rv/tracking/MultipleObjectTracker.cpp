// ----------------- BEGIN LICENSE BLOCK ---------------------------------
//
// INTEL CONFIDENTIAL
//
// Copyright (c) 2019-2023 Intel Corporation
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
#include "rv/tracking/MultipleObjectTracker.hpp"
#include "rv/tracking/Classification.hpp"

namespace rv {
namespace tracking {

template <class ElementType> std::vector<ElementType> filterByIndex(const std::vector<ElementType> &elements, const std::vector<size_t> indexToKeep)
{
  std::vector<ElementType> filtered;
  filtered.reserve(indexToKeep.size());

  for (auto const &index : indexToKeep)
  {
    filtered.push_back(elements[index]);
  }
  return filtered;
}

void splitByThreshold(std::vector<tracking::TrackedObject> &objects,
                      std::vector<tracking::TrackedObject> &lowScoreObjects,
                      double scoreThreshold)
{
  lowScoreObjects.clear();

  auto divider = [scoreThreshold](const tracking::TrackedObject &object) {
    double score = object.classification.maxCoeff();
    return score >= scoreThreshold;
  };

  auto it = std::partition(objects.begin(), objects.end(), divider);

  std::move(it, objects.end(), std::back_inserter(lowScoreObjects));
  objects.erase(it, objects.end());
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects, const std::chrono::system_clock::time_point &timestamp,
                                  double scoreThreshold)
{
  track(objects, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold);
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects, const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType & distanceType, double distanceThreshold, double scoreThreshold)
{
  if (objects.empty())
  {
    mTrackManager.predict(timestamp);
    mTrackManager.correct();
    mLastTimestamp = timestamp;
    return;
  }

  std::vector<tracking::TrackedObject> lowScoreObjects;
  splitByThreshold(objects, lowScoreObjects, scoreThreshold);

  // 1. - Predict
  mTrackManager.predict(rv::toSeconds(timestamp - mLastTimestamp));

  // 2.- Associate with the reliable states first
  auto tracks = mTrackManager.getReliableTracks();

  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedObjects;

  match(tracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

  // 3. - Update measurements - set measurement
  for (const auto &assignment : assignments)
  {
    auto const &track = tracks[assignment.first];
    auto const &object = objects[assignment.second];
    mTrackManager.setMeasurement(track.id, object);
  }

  // Remove tracks already assigned
  tracks = filterByIndex(tracks, unassignedTracks);

  std::vector<size_t> unassignedLowScoreObjects;

  match(tracks, lowScoreObjects, assignments, unassignedTracks, unassignedLowScoreObjects, distanceType, distanceThreshold);

  for (const auto &assignment : assignments)
  {
    auto track = tracks[assignment.first];
    auto object = lowScoreObjects[assignment.second];
    mTrackManager.setMeasurement(track.id, object);
  }

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  // Remove objects already assigned to tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  match(unreliableTracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

  for (const auto &assignment : assignments)
  {
    auto const &track = unreliableTracks[assignment.first];
    auto const &object = objects[assignment.second];
    mTrackManager.setMeasurement(track.id, object);
  }

  // Remove objects already assigned to Unreliable tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  match(suspendedTracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

  for (const auto &assignment : assignments)
  {
    auto const &track = suspendedTracks[assignment.first];
    auto const &object = objects[assignment.second];
    mTrackManager.setMeasurement(track.id, object);
  }

  // 3.2 Update measurements - Correct measurements
  mTrackManager.correct();

  // 4. - Create new tracks
  for (const auto &id : unassignedObjects)
  {
    auto const newTrack = objects[id];

    mTrackManager.createTrack(newTrack, timestamp);
  }

  mLastTimestamp = timestamp;
}
} // namespace tracking
} // namespace rv
