// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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

std::vector<tracking::TrackedObject> MultipleObjectTracker::matchAndAssignMeasurements(
    const std::vector<tracking::TrackedObject> &tracks,
    const std::vector<tracking::TrackedObject> &objects,
    const DistanceType &distanceType,
    double distanceThreshold,
    std::vector<size_t> &unassignedObjects)
{
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;

  match(tracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

  // Update measurements - set measurement
  for (const auto &assignment : assignments)
  {
    auto const &track = tracks[assignment.first];
    auto const &object = objects[assignment.second];
    mTrackManager.setMeasurement(track.id, object);
  }

  // Remove tracks already assigned
  return filterByIndex(tracks, unassignedTracks);
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

  std::vector<size_t> unassignedObjects;
  tracks = matchAndAssignMeasurements(tracks, objects, distanceType, distanceThreshold, unassignedObjects);

  std::vector<size_t> unassignedLowScoreObjects;
  tracks = matchAndAssignMeasurements(tracks, lowScoreObjects, distanceType, distanceThreshold, unassignedLowScoreObjects);

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  // Remove objects already assigned to tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  matchAndAssignMeasurements(unreliableTracks, objects, distanceType, distanceThreshold, unassignedObjects);

  // Remove objects already assigned to Unreliable tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  matchAndAssignMeasurements(suspendedTracks, objects, distanceType, distanceThreshold, unassignedObjects);

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

std::vector<tracking::TrackedObject> MultipleObjectTracker::matchAndAssignMeasurements(
    const std::vector<tracking::TrackedObject> &tracks,
    std::vector<std::vector<tracking::TrackedObject>> &objectsPerCamera,
    const DistanceType &distanceType,
    double distanceThreshold)
{
  const size_t numCameras = objectsPerCamera.size();
  if (numCameras == 0 || tracks.empty())
  {
    return tracks; // No cameras or tracks, return all tracks as unassigned
  }

  // Boolean vector to track which tracks have been assigned
  std::vector<bool> isTrackAssigned(tracks.size(), false);

  // Store assignments and unassigned objects for each camera
  std::vector<std::vector<std::pair<size_t, size_t>>> assignments(numCameras);
  std::vector<std::vector<size_t>> unassignedObjectsPerCamera(numCameras);

  // Parallelizable matching phase
  #pragma omp parallel for
  for (size_t i = 0; i < numCameras; ++i)
  {
    std::vector<size_t> unassignedTracks;
    match(tracks, objectsPerCamera[i], assignments[i], unassignedTracks, unassignedObjectsPerCamera[i], distanceType, distanceThreshold);
  }

  // Sequential assignment phase to avoid race conditions
  for (size_t i = 0; i < numCameras; ++i)
  {
    for (const auto &assignment : assignments[i])
    {
      const auto &track = tracks[assignment.first];
      const auto &object = objectsPerCamera[i][assignment.second];
      mTrackManager.setMeasurement(track.id, object);

      // Mark track as assigned
      isTrackAssigned[assignment.first] = true;
    }
  }

  // Remove assigned objects from each camera's object list using filterByIndex
  for (size_t i = 0; i < numCameras; ++i)
  {
    // Use the unassigned objects from the matching phase
    objectsPerCamera[i] = filterByIndex(objectsPerCamera[i], unassignedObjectsPerCamera[i]);
  }

  // Filter unassigned tracks
  std::vector<tracking::TrackedObject> unassignedTracks;
  unassignedTracks.reserve(tracks.size());
  for (size_t i = 0; i < tracks.size(); ++i)
  {
    if (!isTrackAssigned[i])
    {
      unassignedTracks.push_back(tracks[i]);
    }
  }

  // Return unassigned tracks
  return unassignedTracks;
}

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  double scoreThreshold)
{
  track(objectsPerCamera, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold);
}

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType & distanceType, double distanceThreshold,
                                  double scoreThreshold)
{
  if (objectsPerCamera.empty())
  {
    mTrackManager.predict(timestamp);
    mTrackManager.correct();
    mLastTimestamp = timestamp;
    return;
  }

  std::vector<std::vector<tracking::TrackedObject>> lowScoreObjectsPerCamera;
  lowScoreObjectsPerCamera.reserve(objectsPerCamera.size());
  for (auto &objects : objectsPerCamera)
  {
    std::vector<tracking::TrackedObject> lowScoreObjects;
    splitByThreshold(objects, lowScoreObjects, scoreThreshold);
    lowScoreObjectsPerCamera.push_back(std::move(lowScoreObjects));
  }

  // 1. - Predict
  mTrackManager.predict(rv::toSeconds(timestamp - mLastTimestamp));

  // 2.- Associate with the reliable states first
  auto tracks = mTrackManager.getReliableTracks();

  tracks = matchAndAssignMeasurements(tracks, objectsPerCamera, distanceType, distanceThreshold);

  tracks = matchAndAssignMeasurements(tracks, lowScoreObjectsPerCamera, distanceType, distanceThreshold);

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  matchAndAssignMeasurements(unreliableTracks, objectsPerCamera, distanceType, distanceThreshold);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  matchAndAssignMeasurements(suspendedTracks, objectsPerCamera, distanceType, distanceThreshold);

  // 3.2 Update measurements - Correct measurements
  mTrackManager.correct();

  // 4. - Create new tracks sequentially for each camera
  std::vector<tracking::TrackedObject> newTracks;
  size_t totalUnassignedObjects = 0;
  for (auto &cameraObjects : objectsPerCamera)
  {
    totalUnassignedObjects += cameraObjects.size();
  }
  newTracks.reserve(totalUnassignedObjects);

  // Process cameras in reverse order to prioritize latest camera's objects for accuracy
  for (auto it = objectsPerCamera.rbegin(); it != objectsPerCamera.rend(); ++it)
  {
    auto &cameraObjects = *it;
    // first assign objects to already created new tracks (in case multiple cameras see the same new object)
    if (!newTracks.empty())
    {
      std::vector<size_t> unassignedObjects;
      // the goal of this step is to filter out objects matching existing new tracks, the assignment will be skipped
      matchAndAssignMeasurements(newTracks, cameraObjects, distanceType, distanceThreshold, unassignedObjects);
      cameraObjects = filterByIndex(cameraObjects, unassignedObjects);
    }

    // Create new tracks for remaining unmatched objects
    for (const auto &object : cameraObjects)
    {
      Id newTrackId = mTrackManager.createTrack(object, timestamp);
      newTracks.push_back(mTrackManager.getTrack(newTrackId));
    }
  }

  mLastTimestamp = timestamp;
}
} // namespace tracking
} // namespace rv
