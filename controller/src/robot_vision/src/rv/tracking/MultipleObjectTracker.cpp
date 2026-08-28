// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/MultipleObjectTracker.hpp"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <optional>
#include "rv/Utils.hpp"
#include "rv/tracking/Classification.hpp"

namespace rv {
namespace tracking {

namespace {

constexpr const char *METADATA_PREFIX = "metadata.";
constexpr const char *METADATA_CONFIDENCE_PREFIX = "metadata_confidence.";

bool startsWith(const std::string &value, const char *prefix)
{
  return value.rfind(prefix, 0) == 0;
}

std::optional<double> metadataConfidence(const TrackedObject &object, const std::string &field)
{
  const auto confidence = object.attributes.find(METADATA_CONFIDENCE_PREFIX + field);
  if (confidence == object.attributes.end())
  {
    return std::nullopt;
  }

  double value{};
  const auto *begin = confidence->second.data();
  const auto *end = begin + confidence->second.size();
  const auto [ptr, error] = std::from_chars(begin, end, value);
  if (error != std::errc{} || ptr != end || !std::isfinite(value))
  {
    return std::nullopt;
  }
  return value;
}

void clearMetadataAttributes(TrackedObject &object)
{
  for (auto attribute = object.attributes.begin(); attribute != object.attributes.end();)
  {
    if (startsWith(attribute->first, METADATA_PREFIX) || startsWith(attribute->first, METADATA_CONFIDENCE_PREFIX))
    {
      attribute = object.attributes.erase(attribute);
    }
    else
    {
      ++attribute;
    }
  }
}

void fuseMetadata(const std::vector<std::pair<size_t, size_t>> &matches,
                  const std::vector<std::vector<TrackedObject>> &objectsPerCamera,
                  TrackedObject &measurement)
{
  struct Winner
  {
    std::optional<double> confidence;
    size_t cameraIndex;
  };

  std::unordered_map<std::string, Winner> winners;
  clearMetadataAttributes(measurement);

  for (const auto &[cameraIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerCamera[cameraIndex][objectIndex];
    for (const auto &[key, value] : object.attributes)
    {
      if (!startsWith(key, METADATA_PREFIX))
      {
        continue;
      }

      const std::string field = key.substr(std::char_traits<char>::length(METADATA_PREFIX));
      const auto confidence = metadataConfidence(object, field);
      const auto winner = winners.find(field);
      const bool winnerExists = winner != winners.end();
      const std::optional<double> winnerConfidence = winnerExists ? winner->second.confidence : std::optional<double>{};
      const size_t winnerCameraIndex = winnerExists ? winner->second.cameraIndex : 0;
      if (!metadata_fusion::shouldReplace(winnerExists, confidence, cameraIndex, winnerConfidence, winnerCameraIndex))
      {
        continue;
      }

      measurement.attributes[key] = value;
      const std::string confidenceKey = METADATA_CONFIDENCE_PREFIX + field;
      if (confidence)
      {
        measurement.attributes[confidenceKey] = object.attributes.at(confidenceKey);
      }
      else
      {
        measurement.attributes.erase(confidenceKey);
      }
      winners[field] = Winner{confidence, cameraIndex};
    }
  }
}

void mergeHistoricalMetadata(const TrackedObject &track, TrackedObject &measurement)
{
  for (const auto &[key, value] : track.attributes)
  {
    if (!startsWith(key, METADATA_PREFIX))
    {
      continue;
    }

    const std::string field = key.substr(std::char_traits<char>::length(METADATA_PREFIX));
    const auto storedConfidence = metadataConfidence(track, field);
    const auto currentValue = measurement.attributes.find(key);
    const auto currentConfidence = metadataConfidence(measurement, field);

    const bool currentIsHigher = currentValue != measurement.attributes.end() && currentConfidence
      && (!storedConfidence || *currentConfidence > *storedConfidence);
    if (currentIsHigher)
    {
      continue;
    }

    measurement.attributes[key] = value;
    const std::string confidenceKey = METADATA_CONFIDENCE_PREFIX + field;
    if (storedConfidence)
    {
      measurement.attributes[confidenceKey] = track.attributes.at(confidenceKey);
    }
    else
    {
      measurement.attributes.erase(confidenceKey);
    }
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
                                                  std::vector<size_t> &unassignedObjects)
{
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;

  match(tracks, objects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

  // Update measurements - set measurement
  for (const auto &assignment : assignments)
  {
    auto const &track = tracks[assignment.first];
    auto &measurement = objects[assignment.second];
    mergeHistoricalMetadata(track, measurement);
    mTrackManager.setMeasurement(track.id, measurement);
  }

  // Remove tracks already assigned
  return filterByIndex(tracks, unassignedTracks);
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  double scoreThreshold)
{
  track(objects, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold);
}

void MultipleObjectTracker::track(std::vector<tracking::TrackedObject> objects,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType &distanceType,
                                  double distanceThreshold,
                                  double scoreThreshold)
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
  tracks
    = matchAndAssignMeasurements(tracks, lowScoreObjects, distanceType, distanceThreshold, unassignedLowScoreObjects);

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

std::vector<tracking::TrackedObject>
MultipleObjectTracker::matchAndAssignMeasurements(const std::vector<tracking::TrackedObject> &tracks,
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
    match(tracks,
          objectsPerCamera[i],
          assignments[i],
          unassignedTracks,
          unassignedObjectsPerCamera[i],
          distanceType,
          distanceThreshold);
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
    auto matches = matchesPerTrack[trackIdx];
    if (matches.empty())
    {
      continue;
    }

    // Deterministic camera order so repeated runs fuse observations identically.
    std::sort(matches.begin(), matches.end());

    // Feed every matched observation to the track; the last one carries the fused
    // metadata so its attributes win in the sequential Kalman correction step.
    for (size_t matchIdx = 0; matchIdx < matches.size(); ++matchIdx)
    {
      auto observation = objectsPerCamera[matches[matchIdx].first][matches[matchIdx].second];
      if (matchIdx + 1 == matches.size())
      {
        fuseMetadata(matches, objectsPerCamera, observation);
        mergeHistoricalMetadata(tracks[trackIdx], observation);
      }
      mTrackManager.addMeasurement(tracks[trackIdx].id, observation);
    }

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
  track(objectsPerCamera, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold);
}

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerCamera,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType &distanceType,
                                  double distanceThreshold,
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

  // 4. - Group unmatched detections across cameras before creating tracks.
  std::vector<tracking::TrackedObject> newObjects;
  size_t totalUnassignedObjects = 0;
  for (auto &cameraObjects : objectsPerCamera)
  {
    totalUnassignedObjects += cameraObjects.size();
  }
  newObjects.reserve(totalUnassignedObjects);

  for (auto &cameraObjects : objectsPerCamera)
  {
    if (newObjects.empty())
    {
      newObjects.insert(newObjects.end(), cameraObjects.begin(), cameraObjects.end());
      continue;
    }

    std::vector<std::pair<size_t, size_t>> assignments;
    std::vector<size_t> unassignedTracks;
    std::vector<size_t> unassignedObjects;
    match(newObjects, cameraObjects, assignments, unassignedTracks, unassignedObjects, distanceType, distanceThreshold);

    for (const auto &[newObjectIndex, cameraObjectIndex] : assignments)
    {
      auto fusedObject = cameraObjects[cameraObjectIndex];
      const std::vector<std::vector<TrackedObject>> candidates = {{newObjects[newObjectIndex]}, {fusedObject}};
      const std::vector<std::pair<size_t, size_t>> matches = {{0, 0}, {1, 0}};
      fuseMetadata(matches, candidates, fusedObject);
      newObjects[newObjectIndex] = std::move(fusedObject);
    }

    for (const auto objectIndex : unassignedObjects)
    {
      newObjects.push_back(cameraObjects[objectIndex]);
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
