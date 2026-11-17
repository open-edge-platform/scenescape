// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <rv/Utils.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/ObjectMatching.hpp>

#include "Scenario.hpp"

namespace rv::tracking::test {

// Track-to-detection association as the Controller (association_match_params) and the Tracker Service
// (AssociationConfig) pass it to MultipleObjectTracker::track().
struct Association
{
  std::string_view method; // association.method in the tracker config
  DistanceType distanceType = DistanceType::Euclidean;
  double threshold = 0.0;       // matching cost threshold: meters, or chi-squared for PositionMahalanobis
  double maxRadiusM = 0.0;      // hard Euclidean ceiling
  double gateProbability = 0.0; // PositionMahalanobis only
};

// Legacy meter gate: association.method euclidean with max_radius_m 2.
inline Association euclideanAssociation(double radiusM = 2.0)
{
  return {.method = "euclidean", .distanceType = DistanceType::Euclidean, .threshold = radiusM, .maxRadiusM = radiusM};
}

// Production default: association.method position_mahalanobis, gate_probability 0.99, max_radius_m 10.
inline Association positionMahalanobisAssociation(double gateProbability = 0.99, double maxRadiusM = 10.0)
{
  return {.method = "position_mahalanobis",
          .distanceType = DistanceType::PositionMahalanobis,
          .threshold = rv::chi2Threshold(gateProbability),
          .maxRadiusM = maxRadiusM,
          .gateProbability = gateProbability};
}

// productionConfig() with the track lifecycle times of the default Controller and Tracker Service configs.
inline TrackManagerConfig productionTrackerConfig()
{
  auto config = productionConfig();
  config.mMaxUnreliableTime = 1.0;
  config.mNonMeasurementTimeDynamic = 0.8;
  config.mNonMeasurementTimeStatic = 1.6;
  return config;
}

// Observations without those in from <= t < to, e.g. while the object is occluded.
inline std::vector<Observation> withoutBetween(const std::vector<Observation> &observations, double from, double to)
{
  constexpr double kEpsilon = 1e-9;
  std::vector<Observation> kept;
  for (const auto &observation : observations)
  {
    if (observation.t < from - kEpsilon || observation.t > to - kEpsilon)
    {
      kept.push_back(observation);
    }
  }
  return kept;
}

inline std::vector<double> sampleTimes(const std::vector<TruthSample> &samples)
{
  std::vector<double> times;
  times.reserve(samples.size());
  for (const auto &sample : samples)
  {
    times.push_back(sample.t);
  }
  return times;
}

class TrackerRun;

// Notified by TrackerRun after every track() call, e.g. by ScenarioRecorder.
class TrackerRunObserver
{
public:
  virtual ~TrackerRunObserver() = default;
  // `observations` are the detections of this frame.
  virtual void trackerStep(const TrackerRun &run, double t, const std::vector<Observation> &observations) = 0;
};

// Drives a MultipleObjectTracker like the Tracker Service and the Controller's time-chunking mode: one batched
// track() per frame with one detection list per sensor, production filter and lifecycle settings.
// Each detection carries its ground-truth object id as an attribute. A track keeps the attributes of the detection
// it was last updated with, so after every frame the run knows which object updated which track.
class TrackerRun
{
public:
  static constexpr const char *kObjectIdAttribute = "test.object_id";

  TrackerRun(Association association,
             double fps,
             TrackManagerConfig config = productionTrackerConfig(),
             TrackerRunObserver *observer = nullptr)
    : mAssociation(association)
    , mConfig(std::move(config))
    , mTracker(mConfig)
    , mObserver(observer)
  {
    mTracker.updateTrackerParams(static_cast<int>(std::lround(fps)));
  }

  // One frame at every time in `times`, with the observations at that time (none: an empty frame).
  void play(const std::vector<double> &times, const std::vector<Observation> &observations)
  {
    std::map<std::int64_t, std::vector<Observation>> frames;
    for (const auto &observation : observations)
    {
      frames[frameKey(observation.t)].push_back(observation);
    }
    for (const double t : times)
    {
      step(t, frames[frameKey(t)]);
    }
  }

  void step(double t, const std::vector<Observation> &observations)
  {
    std::map<std::string, std::vector<TrackedObject>> perSensor;
    for (const auto &observation : observations)
    {
      auto detection = observation.detection;
      detection.attributes[kObjectIdAttribute] = std::to_string(observation.objectId);
      perSensor[observation.sensorId].push_back(std::move(detection));
    }
    std::vector<std::vector<TrackedObject>> objectsPerCamera;
    for (auto &[sensorId, detections] : perSensor)
    {
      objectsPerCamera.push_back(std::move(detections));
    }
    mTracker.track(std::move(objectsPerCamera),
                   atSeconds(t),
                   mAssociation.distanceType,
                   mAssociation.threshold,
                   kScoreThreshold,
                   mAssociation.maxRadiusM);
    recordUpdates(t);
    if (mObserver != nullptr)
    {
      mObserver->trackerStep(*this, t, observations);
    }
  }

  // Tracks the object's detections updated or started, in order of first update. More than one: an identity
  // switch or a fragmented track.
  std::vector<Id> tracksOf(int objectId) const
  {
    std::vector<Id> tracks;
    for (const auto &update : mUpdates)
    {
      if (update.objectId == objectId && std::ranges::find(tracks, update.trackId) == tracks.end())
      {
        tracks.push_back(update.trackId);
      }
    }
    return tracks;
  }

  // Objects whose detections updated or started the track. More than one: the track jumped to another object.
  std::set<int> objectsOf(Id trackId) const
  {
    std::set<int> objects;
    for (const auto &update : mUpdates)
    {
      if (update.trackId == trackId)
      {
        objects.insert(update.objectId);
      }
    }
    return objects;
  }

  // Extra tracks per object plus extra objects per track; 0 when every object keeps one track of its own.
  int identityErrors(const std::set<int> &objectIds) const
  {
    int errors = 0;
    std::set<Id> trackIds;
    for (const int objectId : objectIds)
    {
      const auto tracks = tracksOf(objectId);
      errors += std::max(static_cast<int>(tracks.size()) - 1, 0);
      trackIds.insert(tracks.begin(), tracks.end());
    }
    for (const Id trackId : trackIds)
    {
      errors += std::max(static_cast<int>(objectsOf(trackId).size()) - 1, 0);
    }
    return errors;
  }

  // Frames in which the object's detection updated or started a track.
  int updatesOf(int objectId) const
  {
    return static_cast<int>(
      std::ranges::count_if(mUpdates, [objectId](const Update &update) { return update.objectId == objectId; }));
  }

  // Published tracks, as the Controller and the Tracker Service output them.
  std::vector<TrackedObject> reliableTracks() const
  {
    std::vector<TrackedObject> tracks;
    for (const Id id : reliableTrackIds())
    {
      tracks.push_back(estimator(id).currentState());
    }
    return tracks;
  }

  std::vector<Id> reliableTrackIds() const
  {
    const auto &manager = mTracker.mTrackManager;
    std::vector<Id> ids;
    for (const auto &[id, estimator] : manager.mKalmanEstimators)
    {
      if (manager.mNumberOfTrackedFrames.at(id) >= manager.mConfig.mMaxNumberOfUnreliableFrames)
      {
        ids.push_back(id);
      }
    }
    std::ranges::sort(ids);
    return ids;
  }

  const MultiModelKalmanEstimator &estimator(Id id) const
  {
    return mTracker.mTrackManager.mKalmanEstimators.at(id);
  }

  // Ground-truth object of the detection that last updated the track; 0 if unknown.
  static int objectIdOf(const TrackedObject &track)
  {
    const auto found = track.attributes.find(kObjectIdAttribute);
    return found != track.attributes.end() ? std::stoi(found->second) : 0;
  }

  const Association &association() const
  {
    return mAssociation;
  }

  const TrackManagerConfig &config() const
  {
    return mConfig;
  }

private:
  static constexpr double kScoreThreshold = 0.5;

  struct Update
  {
    double t;
    int objectId;
    Id trackId;
  };

  static std::int64_t frameKey(double t)
  {
    return std::llround(t * 1e6);
  }

  // A track measured or started in this frame has no non-measurement frames.
  void recordUpdates(double t)
  {
    const auto &manager = mTracker.mTrackManager;
    for (const auto &[id, estimator] : manager.mKalmanEstimators)
    {
      const int objectId = objectIdOf(estimator.currentState());
      if (manager.mNonMeasurementFrames.at(id) == 0 && objectId != 0)
      {
        mUpdates.push_back({t, objectId, id});
      }
    }
  }

  Association mAssociation;
  TrackManagerConfig mConfig;
  MultipleObjectTracker mTracker;
  TrackerRunObserver *mObserver = nullptr;
  std::vector<Update> mUpdates;
};

} // namespace rv::tracking::test
