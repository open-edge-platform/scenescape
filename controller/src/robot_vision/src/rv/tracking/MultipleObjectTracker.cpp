// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/MultipleObjectTracker.hpp"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include "rv/Utils.hpp"
#include "rv/tracking/Classification.hpp"
#include "rv/tracking/MetadataFusion.hpp"
#include "rv/tracking/OrientationAttributes.hpp"

namespace rv {
namespace tracking {

namespace {

/**
 * @brief Average world position and size across multi-camera matches into measurement.
 *
 * Last-camera-wins for x/y biases static objects when cameras disagree on the
 * ground-plane projection. Equal-weight averaging is the Phase-1 fix; per-detection
 * R weighting belongs with Phase 2 measurement covariance. Yaw is not averaged:
 * non-orienting detections carry no yaw (see applyOrientingYaw).
 */
void fuseGeometry(const std::vector<std::pair<size_t, size_t>> &matches,
                  const std::vector<std::vector<TrackedObject>> &objectsPerCamera,
                  TrackedObject &measurement)
{
  if (matches.size() <= 1)
  {
    return;
  }

  double sumX = 0.0;
  double sumY = 0.0;
  double sumZ = 0.0;
  double sumLength = 0.0;
  double sumWidth = 0.0;
  double sumHeight = 0.0;

  for (const auto &[cameraIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerCamera[cameraIndex][objectIndex];
    sumX += object.x;
    sumY += object.y;
    sumZ += object.z;
    sumLength += object.length;
    sumWidth += object.width;
    sumHeight += object.height;
  }

  const double n = static_cast<double>(matches.size());
  measurement.x = sumX / n;
  measurement.y = sumY / n;
  measurement.z = sumZ / n;
  measurement.length = sumLength / n;
  measurement.width = sumWidth / n;
  measurement.height = sumHeight / n;
}

/**
 * Prefer yaw from an orienting detection among matches. Position and size are
 * averaged separately by fuseGeometry. When several orienting
 * detections match, pick the highest classification confidence and break ties
 * with later camera order.
 */
void applyOrientingYaw(const std::vector<std::pair<size_t, size_t>> &matches,
                       const std::vector<std::vector<TrackedObject>> &objectsPerCamera,
                       TrackedObject &fusedObject)
{
  bool found = false;
  double bestConfidence = -1.0;
  size_t bestCameraIndex = 0;
  double bestYaw = fusedObject.yaw;

  for (const auto &[cameraIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerCamera[cameraIndex][objectIndex];
    if (!orientation::hasOrientation(object))
    {
      continue;
    }
    const double confidence = object.classification.size() > 0 ? object.classification.maxCoeff() : 0.0;
    if (!found || confidence > bestConfidence || (confidence == bestConfidence && cameraIndex > bestCameraIndex))
    {
      found = true;
      bestConfidence = confidence;
      bestCameraIndex = cameraIndex;
      bestYaw = object.yaw;
    }
  }

  if (found)
  {
    fusedObject.yaw = bestYaw;
    orientation::setHasOrientation(fusedObject, true);
  }
  else
  {
    orientation::setHasOrientation(fusedObject, false);
  }
}

} // namespace

template <class ElementType>
std::vector<ElementType> filterByIndex(const std::vector<ElementType> &elements, const std::vector<size_t> indexToKeep)
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

std::vector<tracking::TrackedObject>
MultipleObjectTracker::matchAndAssignMeasurements(const std::vector<tracking::TrackedObject> &tracks,
                                                  std::vector<tracking::TrackedObject> &objects,
                                                  const DistanceType &distanceType,
                                                  double distanceThreshold,
                                                  std::vector<size_t> &unassignedObjects,
                                                  double maxRadiusM)
{
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;

  match(tracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold,
        maxRadiusM);

  // Update measurements - set measurement
  for (const auto &assignment : assignments)
  {
    auto const &track = tracks[assignment.first];
    auto &measurement = objects[assignment.second];
    metadata_fusion::mergeHistoricalMetadata(track, measurement);
    mTrackManager.setMeasurement(track.id, measurement);
  }

  // Remove tracks already assigned
  return filterByIndex(tracks, unassignedTracks);
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  double scoreThreshold)
{
  track(objects, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold, mMaxRadiusM);
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType &distanceType,
                                  double distanceThreshold,
                                  double scoreThreshold,
                                  double maxRadiusM)
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
  tracks
    = matchAndAssignMeasurements(tracks, objects, distanceType, distanceThreshold, unassignedObjects, maxRadiusM);

  std::vector<size_t> unassignedLowScoreObjects;
  tracks = matchAndAssignMeasurements(tracks, lowScoreObjects, distanceType, distanceThreshold,
                                      unassignedLowScoreObjects, maxRadiusM);

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  // Remove objects already assigned to tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  matchAndAssignMeasurements(unreliableTracks, objects, distanceType, distanceThreshold, unassignedObjects,
                             maxRadiusM);

  // Remove objects already assigned to Unreliable tracks
  objects = filterByIndex(objects, unassignedObjects);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  matchAndAssignMeasurements(suspendedTracks, objects, distanceType, distanceThreshold, unassignedObjects,
                             maxRadiusM);

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

std::vector<tracking::TrackedObject>
MultipleObjectTracker::matchAndAssignMeasurements(const std::vector<tracking::TrackedObject> &tracks,
                                                  std::vector<std::vector<tracking::TrackedObject>> &objectsPerCamera,
                                                  const DistanceType &distanceType,
                                                  double distanceThreshold,
                                                  double maxRadiusM)
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
    match(tracks,
          objectsPerCamera[i],
          assignments[i],
          unassignedTracks,
          unassignedObjectsPerCamera[i],
          distanceType,
          distanceThreshold,
          maxRadiusM);
  }

  // Group all camera matches per track index so each track gets one fused measurement.
  std::vector<std::vector<std::pair<size_t, size_t>>> matchesPerTrack(tracks.size());
  for (size_t cameraIdx = 0; cameraIdx < numCameras; ++cameraIdx)
  {
    for (const auto &assignment : assignments[cameraIdx])
    {
      matchesPerTrack[assignment.first].push_back(std::make_pair(cameraIdx, assignment.second));
    }
  }

  // Sequential assignment phase to avoid race conditions
  for (size_t trackIdx = 0; trackIdx < tracks.size(); ++trackIdx)
  {
    const auto &matches = matchesPerTrack[trackIdx];
    if (matches.empty())
    {
      continue;
    }

    // Seed from the latest matched camera, then average geometry across all cameras
    // that matched this track (metadata still uses confidence / camera-order policy).
    const auto &lastMatch = matches.back();
    auto fusedObject = objectsPerCamera[lastMatch.first][lastMatch.second];
    fuseGeometry(matches, objectsPerCamera, fusedObject);
    applyOrientingYaw(matches, objectsPerCamera, fusedObject);
    metadata_fusion::fuseMetadata(matches, objectsPerCamera, fusedObject);
    metadata_fusion::mergeHistoricalMetadata(tracks[trackIdx], fusedObject);

    mTrackManager.setMeasurement(tracks[trackIdx].id, fusedObject);
    isTrackAssigned[trackIdx] = true;
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
  track(objectsPerCamera, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold, mMaxRadiusM);
}

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType &distanceType,
                                  double distanceThreshold,
                                  double scoreThreshold,
                                  double maxRadiusM)
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

  tracks = matchAndAssignMeasurements(tracks, objectsPerCamera, distanceType, distanceThreshold, maxRadiusM);

  tracks = matchAndAssignMeasurements(tracks, lowScoreObjectsPerCamera, distanceType, distanceThreshold, maxRadiusM);

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  matchAndAssignMeasurements(unreliableTracks, objectsPerCamera, distanceType, distanceThreshold, maxRadiusM);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  matchAndAssignMeasurements(suspendedTracks, objectsPerCamera, distanceType, distanceThreshold, maxRadiusM);

  // 3.2 Update measurements - Correct measurements
  mTrackManager.correct();

  // 4. - Group unmatched detections across cameras before creating tracks.
  // Detection-to-detection clustering must use Euclidean meters: raw detections
  // do not carry track predictedMeasurementCov, so PositionMahalanobis treats
  // them as near-delta covariances and fails to fuse the same object seen by
  // two cameras (duplicate frozen tracks). EuclideanBirth uses XY unless both
  // sides have measured Z (zMeasured), so planar + 3D OD still fuse; two 3D
  // detections use XYZ so stacked floors stay separate. Legacy ~2 m birth
  // radius — not maxRadiusM — so a Mahalanobis association ceiling (e.g. 10 m)
  // does not over-merge nearby people at birth. Track-to-detection association
  // above still uses distanceType / distanceThreshold / maxRadiusM.
  std::vector<tracking::TrackedObject> newObjects;
  // (camera, object) members of each newObjects entry, re-fused together so cameras weigh equally.
  std::vector<std::vector<std::pair<size_t, size_t>>> clusterMembers;
  size_t totalUnassignedObjects = 0;
  for (auto &cameraObjects : objectsPerCamera)
  {
    totalUnassignedObjects += cameraObjects.size();
  }
  newObjects.reserve(totalUnassignedObjects);
  clusterMembers.reserve(totalUnassignedObjects);

  for (size_t cameraIndex = 0; cameraIndex < objectsPerCamera.size(); ++cameraIndex)
  {
    const auto &cameraObjects = objectsPerCamera[cameraIndex];
    if (newObjects.empty())
    {
      for (size_t objectIndex = 0; objectIndex < cameraObjects.size(); ++objectIndex)
      {
        newObjects.push_back(cameraObjects[objectIndex]);
        clusterMembers.push_back({{cameraIndex, objectIndex}});
      }
      continue;
    }

    std::vector<std::pair<size_t, size_t>> assignments;
    std::vector<size_t> unassignedTracks;
    std::vector<size_t> unassignedObjects;
    match(newObjects, cameraObjects, assignments, unassignedTracks, unassignedObjects,
          DistanceType::EuclideanBirth, kDefaultBirthClusterRadiusM, kDefaultBirthClusterRadiusM);

    for (const auto &[newObjectIndex, cameraObjectIndex] : assignments)
    {
      auto &members = clusterMembers[newObjectIndex];
      members.emplace_back(cameraIndex, cameraObjectIndex);
      // Re-fuse on every join, not once after the loop: later cameras are matched against the fused cluster.
      auto &fusedObject = newObjects[newObjectIndex];
      fuseGeometry(members, objectsPerCamera, fusedObject);
      applyOrientingYaw(members, objectsPerCamera, fusedObject);
      metadata_fusion::fuseMetadata(members, objectsPerCamera, fusedObject);
    }

    for (const auto objectIndex : unassignedObjects)
    {
      newObjects.push_back(cameraObjects[objectIndex]);
      clusterMembers.push_back({{cameraIndex, objectIndex}});
    }
  }

  for (const auto &newObject : newObjects)
  {
    mTrackManager.createTrack(newObject, timestamp);
  }

  mLastTimestamp = timestamp;
}
} // namespace tracking
} // namespace rv
