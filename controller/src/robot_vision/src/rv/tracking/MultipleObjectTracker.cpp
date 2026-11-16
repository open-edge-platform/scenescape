// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/MultipleObjectTracker.hpp"
#include <algorithm>
#include <array>
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
 * Information matrix of a geometry R without its z row and column: the inverse of the remaining
 * 5x5 covariance, embedded with zeros for z.
 */
cv::Matx<double, 6, 6> informationWithoutZ(const cv::Matx<double, 6, 6> &noise)
{
  constexpr int kReduced = 5;
  constexpr std::array<int, kReduced> kKept = {MeasurementIndex::X,
                                               MeasurementIndex::Y,
                                               MeasurementIndex::LENGTH,
                                               MeasurementIndex::WIDTH,
                                               MeasurementIndex::HEIGHT};
  cv::Matx<double, kReduced, kReduced> reduced;
  for (int row = 0; row < kReduced; ++row)
  {
    for (int col = 0; col < kReduced; ++col)
    {
      reduced(row, col) = noise(kKept[row], kKept[col]);
    }
  }
  const cv::Matx<double, kReduced, kReduced> reducedInv = reduced.inv(cv::DECOMP_SVD);
  cv::Matx<double, 6, 6> information;
  for (int row = 0; row < kReduced; ++row)
  {
    for (int col = 0; col < kReduced; ++col)
    {
      information(kKept[row], kKept[col]) = reducedInv(row, col);
    }
  }
  return information;
}

constexpr int kGeometrySize = MeasurementIndex::HEIGHT + 1;
static_assert(MeasurementIndex::X == 0 && MeasurementIndex::HEIGHT == 5 && MeasurementIndex::YAW == 6,
              "x, y, z, length, width, height must lead the measurement vector, followed by yaw");

bool anyMatchMeasuredZ(const std::vector<std::pair<size_t, size_t>> &matches,
                       const std::vector<std::vector<TrackedObject>> &objectsPerSource)
{
  return std::any_of(matches.begin(), matches.end(), [&](const auto &match) {
    return objectsPerSource[match.first][match.second].z_measured;
  });
}

/**
 * Information on [x, y, z, length, width, height] that one match contributes to the fusion: the inverse of its
 * geometry R (the tracker default without one). z comes from the measured detections only: a detection without
 * measured z carries the ground point, so it gives no z information when another match measured z.
 */
cv::Matx<double, kGeometrySize, kGeometrySize>
fusionInformation(const TrackedObject &object, bool anyZMeasured, double defaultMeasurementNoise)
{
  // track() has already rejected invalid R; unset means the tracker default.
  const auto noise
    = object.measurementNoiseCov.value_or(TrackedObject::MeasurementMatrix::eye() * defaultMeasurementNoise)
        .get_minor<kGeometrySize, kGeometrySize>(0, 0);
  return anyZMeasured && !object.z_measured ? informationWithoutZ(noise) : noise.inv(cv::DECOMP_SVD);
}

/**
 * @brief Fuse world position and size across multi-source matches into measurement.
 *
 * Without any per-detection R this is the equal-weight average: last-source-wins for x/y
 * biases static objects when sources disagree on world position. When at least
 * one match carries R, [x, y, z, length, width, height] are fused in information form
 * (R_f = (sum R_i^-1)^-1, z_f = R_f * sum R_i^-1 z_i), using the tracker default R for
 * matches without one, and R_f is attached to the fused measurement for the Kalman update.
 * Yaw is not averaged: non-orienting detections carry no yaw, and its variance is kept from
 * the seed measurement here and replaced by the selected detection's in applyOrientingYaw, which
 * also fills the geometry-yaw covariance.
 */
void fuseGeometry(const std::vector<std::pair<size_t, size_t>> &matches,
                  const std::vector<std::vector<TrackedObject>> &objectsPerSource,
                  TrackedObject &measurement,
                  double defaultMeasurementNoise)
{
  if (matches.size() <= 1)
  {
    return;
  }

  const bool anyMeasurementNoise = std::any_of(matches.begin(), matches.end(), [&](const auto &match) {
    return objectsPerSource[match.first][match.second].measurementNoiseCov.has_value();
  });

  if (anyMeasurementNoise)
  {
    constexpr int kFusedSize = kGeometrySize;
    using FusedMatrix = cv::Matx<double, kFusedSize, kFusedSize>;
    using FusedVector = cv::Matx<double, kFusedSize, 1>;
    const TrackedObject::MeasurementMatrix defaultNoise
      = TrackedObject::MeasurementMatrix::eye() * defaultMeasurementNoise;

    const bool anyZMeasured = anyMatchMeasuredZ(matches, objectsPerSource);

    FusedMatrix information;
    FusedVector informationVector;
    for (const auto &[sourceIndex, objectIndex] : matches)
    {
      const auto &object = objectsPerSource[sourceIndex][objectIndex];
      const FusedMatrix noiseInv = fusionInformation(object, anyZMeasured, defaultMeasurementNoise);
      information += noiseInv;
      informationVector += noiseInv * object.measurementVector().get_minor<kFusedSize, 1>(0, 0);
    }

    const FusedMatrix fusedCov = information.inv(cv::DECOMP_SVD);
    const FusedVector fused = fusedCov * informationVector;
    measurement.x = fused(MeasurementIndex::X);
    measurement.y = fused(MeasurementIndex::Y);
    measurement.z = fused(MeasurementIndex::Z);
    measurement.length = fused(MeasurementIndex::LENGTH);
    measurement.width = fused(MeasurementIndex::WIDTH);
    measurement.height = fused(MeasurementIndex::HEIGHT);

    TrackedObject::MeasurementMatrix fusedNoise;
    for (int row = 0; row < kFusedSize; ++row)
    {
      for (int col = 0; col < kFusedSize; ++col)
      {
        fusedNoise(row, col) = fusedCov(row, col);
      }
    }
    fusedNoise(MeasurementIndex::YAW, MeasurementIndex::YAW)
      = measurement.measurementNoiseCov.value_or(defaultNoise)(MeasurementIndex::YAW, MeasurementIndex::YAW);
    measurement.measurementNoiseCov = fusedNoise;
    return;
  }

  double sumX = 0.0;
  double sumY = 0.0;
  double sumZ = 0.0;
  double sumLength = 0.0;
  double sumWidth = 0.0;
  double sumHeight = 0.0;

  for (const auto &[sourceIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerSource[sourceIndex][objectIndex];
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
 * fused separately by fuseGeometry. When several orienting
 * detections match, pick the highest classification confidence and break ties
 * with later source order. When the fused measurement carries R, its yaw variance
 * follows the selected detection, and so does its geometry-yaw covariance when several
 * matches were fused: x_f = R_f * sum I_i x_i with independent detections gives
 * Cov(x_f, yaw_s) = R_f * I_s * Cov(x_s, yaw_s), I_s the information fuseGeometry took from s.
 */
void applyOrientingYaw(const std::vector<std::pair<size_t, size_t>> &matches,
                       const std::vector<std::vector<TrackedObject>> &objectsPerSource,
                       TrackedObject &fusedObject,
                       double defaultMeasurementNoise)
{
  const TrackedObject *best = nullptr;
  double bestConfidence = -1.0;
  size_t bestSourceIndex = 0;

  for (const auto &[sourceIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerSource[sourceIndex][objectIndex];
    if (!orientation::hasOrientation(object))
    {
      continue;
    }
    const double confidence = object.classification.size() > 0 ? object.classification.maxCoeff() : 0.0;
    if (best == nullptr || confidence > bestConfidence
        || (confidence == bestConfidence && sourceIndex > bestSourceIndex))
    {
      best = &object;
      bestConfidence = confidence;
      bestSourceIndex = sourceIndex;
    }
  }

  if (best != nullptr)
  {
    fusedObject.yaw = best->yaw;
    orientation::setHasOrientation(fusedObject, true);
    if (fusedObject.measurementNoiseCov)
    {
      auto &noise = *fusedObject.measurementNoiseCov;
      const TrackedObject::MeasurementMatrix bestNoise
        = best->measurementNoiseCov.value_or(TrackedObject::MeasurementMatrix::eye() * defaultMeasurementNoise);
      noise(MeasurementIndex::YAW, MeasurementIndex::YAW) = bestNoise(MeasurementIndex::YAW, MeasurementIndex::YAW);
      // A single match is its own measurement and keeps its R as it is.
      if (matches.size() > 1)
      {
        const auto cross = noise.get_minor<kGeometrySize, kGeometrySize>(0, 0)
          * fusionInformation(*best, anyMatchMeasuredZ(matches, objectsPerSource), defaultMeasurementNoise)
          * bestNoise.get_minor<kGeometrySize, 1>(0, MeasurementIndex::YAW);
        for (int row = 0; row < kGeometrySize; ++row)
        {
          noise(row, MeasurementIndex::YAW) = noise(MeasurementIndex::YAW, row) = cross(row);
        }
      }
    }
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
                                                  std::vector<std::vector<tracking::TrackedObject>> &objectsPerSource,
                                                  const DistanceType &distanceType,
                                                  double distanceThreshold,
                                                  double maxRadiusM)
{
  const size_t numSources = objectsPerSource.size();
  if (numSources == 0 || tracks.empty())
  {
    return tracks; // No sources or tracks, return all tracks as unassigned
  }

  // Boolean vector to track which tracks have been assigned
  std::vector<bool> isTrackAssigned(tracks.size(), false);

  // Store assignments and unassigned objects for each source
  std::vector<std::vector<std::pair<size_t, size_t>>> assignments(numSources);
  std::vector<std::vector<size_t>> unassignedObjectsPerSource(numSources);

// Parallelizable matching phase
#pragma omp parallel for
  for (size_t i = 0; i < numSources; ++i)
  {
    std::vector<size_t> unassignedTracks;
    match(tracks,
          objectsPerSource[i],
          assignments[i],
          unassignedTracks,
          unassignedObjectsPerSource[i],
          distanceType,
          distanceThreshold,
          maxRadiusM);
  }

  // Group all source matches per track index so each track gets one fused measurement.
  std::vector<std::vector<std::pair<size_t, size_t>>> matchesPerTrack(tracks.size());
  const double defaultMeasurementNoise = mTrackManager.getConfig().mDefaultMeasurementNoise;
  for (size_t sourceIdx = 0; sourceIdx < numSources; ++sourceIdx)
  {
    for (const auto &assignment : assignments[sourceIdx])
    {
      matchesPerTrack[assignment.first].push_back(std::make_pair(sourceIdx, assignment.second));
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

    // Seed from the latest matched source, then fuse geometry across all sources
    // that matched this track (metadata still uses confidence / source-order policy).
    const auto &lastMatch = matches.back();
    auto fusedObject = objectsPerSource[lastMatch.first][lastMatch.second];
    fuseGeometry(matches, objectsPerSource, fusedObject, defaultMeasurementNoise);
    applyOrientingYaw(matches, objectsPerSource, fusedObject, defaultMeasurementNoise);
    // The update measured z if any matched source did, whichever source seeds the fused object.
    fusedObject.z_measured = std::any_of(matches.begin(), matches.end(), [&](const auto &match) {
      return objectsPerSource[match.first][match.second].z_measured;
    });
    metadata_fusion::fuseMetadata(matches, objectsPerSource, fusedObject);
    metadata_fusion::mergeHistoricalMetadata(tracks[trackIdx], fusedObject);

    mTrackManager.setMeasurement(tracks[trackIdx].id, fusedObject);
    isTrackAssigned[trackIdx] = true;
  }

  // Remove assigned objects from each source's object list using filterByIndex
  for (size_t i = 0; i < numSources; ++i)
  {
    // Use the unassigned objects from the matching phase
    objectsPerSource[i] = filterByIndex(objectsPerSource[i], unassignedObjectsPerSource[i]);
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

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerSource,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  double scoreThreshold)
{
  track(objectsPerSource, timestamp, mDistanceType, mDistanceThreshold, scoreThreshold, mMaxRadiusM);
}

void MultipleObjectTracker::track(std::vector<std::vector<tracking::TrackedObject>> objectsPerSource,
                                  const std::chrono::system_clock::time_point &timestamp,
                                  const DistanceType &distanceType,
                                  double distanceThreshold,
                                  double scoreThreshold,
                                  double maxRadiusM,
                                  double birthClusterRadiusM)
{
  if (objectsPerSource.empty())
  {
    mTrackManager.predict(timestamp);
    mTrackManager.correct();
    mLastTimestamp = timestamp;
    return;
  }

  // Reject invalid per-detection R before association, fusion, birth, or the Kalman update.
  for (auto &sourceObjects : objectsPerSource)
  {
    for (auto &object : sourceObjects)
    {
      ensureValidMeasurementNoiseCov(object);
    }
  }

  std::vector<std::vector<tracking::TrackedObject>> lowScoreObjectsPerSource;
  lowScoreObjectsPerSource.reserve(objectsPerSource.size());
  for (auto &objects : objectsPerSource)
  {
    std::vector<tracking::TrackedObject> lowScoreObjects;
    splitByThreshold(objects, lowScoreObjects, scoreThreshold);
    lowScoreObjectsPerSource.push_back(std::move(lowScoreObjects));
  }

  // 1. - Predict
  mTrackManager.predict(rv::toSeconds(timestamp - mLastTimestamp));

  // 2.- Associate with the reliable states first
  auto tracks = mTrackManager.getReliableTracks();

  tracks = matchAndAssignMeasurements(tracks, objectsPerSource, distanceType, distanceThreshold, maxRadiusM);

  tracks = matchAndAssignMeasurements(tracks, lowScoreObjectsPerSource, distanceType, distanceThreshold, maxRadiusM);

  // 3.1 Update measurements - Match to unreliable objects first and then suspended tracks.
  auto unreliableTracks = mTrackManager.getUnreliableTracks();
  matchAndAssignMeasurements(unreliableTracks, objectsPerSource, distanceType, distanceThreshold, maxRadiusM);

  auto suspendedTracks = mTrackManager.getSuspendedTracks();
  matchAndAssignMeasurements(suspendedTracks, objectsPerSource, distanceType, distanceThreshold, maxRadiusM);

  // 3.2 Update measurements - Correct measurements
  mTrackManager.correct();

  // 4. - Group unmatched detections across sources before creating tracks.
  // Detection-to-detection clustering must use Euclidean meters: raw detections
  // do not carry track predictedMeasurementCov, so PositionMahalanobis treats
  // them as near-delta covariances and fails to fuse the same object seen by
  // two sources (duplicate frozen tracks). EuclideanBirth uses XY unless both
  // sides have measured Z (z_measured), so planar + 3D OD still fuse; two 3D
  // detections use XYZ so stacked floors stay separate. Use birthClusterRadiusM
  // (default 2 m) — not maxRadiusM — so a Mahalanobis association ceiling
  // (e.g. 10 m) does not over-merge nearby people at birth. Track-to-detection
  // association above still uses distanceType / distanceThreshold / maxRadiusM.
  std::vector<tracking::TrackedObject> newObjects;
  // (source, object) members of each newObjects entry, re-fused together so each source counts once.
  std::vector<std::vector<std::pair<size_t, size_t>>> clusterMembers;
  const double defaultMeasurementNoise = mTrackManager.getConfig().mDefaultMeasurementNoise;
  size_t totalUnassignedObjects = 0;
  for (auto &sourceObjects : objectsPerSource)
  {
    totalUnassignedObjects += sourceObjects.size();
  }
  newObjects.reserve(totalUnassignedObjects);
  clusterMembers.reserve(totalUnassignedObjects);

  for (size_t sourceIndex = 0; sourceIndex < objectsPerSource.size(); ++sourceIndex)
  {
    const auto &sourceObjects = objectsPerSource[sourceIndex];
    if (newObjects.empty())
    {
      for (size_t objectIndex = 0; objectIndex < sourceObjects.size(); ++objectIndex)
      {
        newObjects.push_back(sourceObjects[objectIndex]);
        clusterMembers.push_back({{sourceIndex, objectIndex}});
      }
      continue;
    }

    std::vector<std::pair<size_t, size_t>> assignments;
    std::vector<size_t> unassignedTracks;
    std::vector<size_t> unassignedObjects;
    match(newObjects, sourceObjects, assignments, unassignedTracks, unassignedObjects,
          DistanceType::EuclideanBirth, birthClusterRadiusM, birthClusterRadiusM);

    for (const auto &[newObjectIndex, sourceObjectIndex] : assignments)
    {
      auto &members = clusterMembers[newObjectIndex];
      members.emplace_back(sourceIndex, sourceObjectIndex);
      // Re-fuse on every join, not once after the loop: later sources are matched against the fused cluster.
      auto &fusedObject = newObjects[newObjectIndex];
      fuseGeometry(members, objectsPerSource, fusedObject, defaultMeasurementNoise);
      applyOrientingYaw(members, objectsPerSource, fusedObject, defaultMeasurementNoise);
      // Same sticky rule as track↔detection fusion: any measured-z source marks the birth seed.
      fusedObject.z_measured = std::any_of(members.begin(), members.end(), [&](const auto &match) {
        return objectsPerSource[match.first][match.second].z_measured;
      });
      metadata_fusion::fuseMetadata(members, objectsPerSource, fusedObject);
    }

    for (const auto objectIndex : unassignedObjects)
    {
      newObjects.push_back(sourceObjects[objectIndex]);
      clusterMembers.push_back({{sourceIndex, objectIndex}});
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
