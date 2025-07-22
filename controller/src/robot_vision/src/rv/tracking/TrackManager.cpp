// SPDX-FileCopyrightText: (C) 2017 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/Utils.hpp"
#include "rv/tracking/TrackManager.hpp"
#include <iostream>
#include <omp.h>

namespace rv {
namespace tracking {

Id TrackManager::createTrack(TrackedObject object, const std::chrono::system_clock::time_point &timestamp)
{
  if (mAutoIdGeneration)
  {
    mCurrentId++;
    object.id = mCurrentId;
  }

  mKalmanEstimators[object.id].initialize(object, timestamp, mConfig.mDefaultProcessNoise, mConfig.mDefaultMeasurementNoise, mConfig.mInitStateCovariance, mConfig.mMotionModels);

  // Initialize non measurement and tracked frames counters
  mNonMeasurementFrames[object.id] = 0;
  mNumberOfTrackedFrames[object.id] = 0;
  return object.id;
}

void TrackManager::deleteTrack(const Id &id)
{
  if (isSuspended(id))
  {
    reactivateTrack(id);
  }

  mKalmanEstimators.erase(id);
  mNonMeasurementFrames.erase(id);
  mNumberOfTrackedFrames.erase(id);
}

void TrackManager::suspendTrack(const Id &id)
{
  mSuspendedKalmanEstimators[id] = std::move(mKalmanEstimators.at(id));
  mKalmanEstimators.erase(id);
  mNonMeasurementFrames.erase(id);
}

void TrackManager::reactivateTrack(const Id &id)
{
  mKalmanEstimators[id] = std::move(mSuspendedKalmanEstimators.at(id));

  // Initialize non measurement and tracked frames counters
  mNonMeasurementFrames[id] = 0;
  mNumberOfTrackedFrames[id] = mConfig.mMaxNumberOfUnreliableFrames - mConfig.mReactivationFrames;

  mSuspendedKalmanEstimators.erase(id);
}

void TrackManager::predict(const std::chrono::system_clock::time_point &timestamp)
{
  // Convert map to vector for parallel iteration
  std::vector<std::reference_wrapper<MultiModelKalmanEstimator>> estimators;
  estimators.reserve(mKalmanEstimators.size());

  for (auto &element : mKalmanEstimators)
  {
    estimators.push_back(std::ref(element.second));
  }

  // Parallelize the prediction step
  #pragma omp parallel for
  for (size_t i = 0; i < estimators.size(); ++i)
  {
    estimators[i].get().predict(timestamp);
  }
  mMeasurementMap.clear();
}


void TrackManager::predict(double deltaT)
{
  // Convert map to vector for parallel iteration
  std::vector<std::reference_wrapper<MultiModelKalmanEstimator>> estimators;
  estimators.reserve(mKalmanEstimators.size());

  for (auto &element : mKalmanEstimators)
  {
    estimators.push_back(std::ref(element.second));
  }

  // Parallelize the prediction step
  #pragma omp parallel for
  for (size_t i = 0; i < estimators.size(); ++i)
  {
    estimators[i].get().predict(deltaT);
  }

  mMeasurementMap.clear();
}

void TrackManager::correct()
{
  // Convert map to vector for parallel iteration
  std::vector<std::pair<Id, std::reference_wrapper<MultiModelKalmanEstimator>>> estimators;
  estimators.reserve(mKalmanEstimators.size());

  for (auto &element : mKalmanEstimators)
  {
    estimators.push_back(std::make_pair(element.first, std::ref(element.second)));
  }

  // Parallelize the correction step
  #pragma omp parallel for
  for (size_t i = 0; i < estimators.size(); ++i)
  {
    auto const &id = estimators[i].first;
    auto &estimator = estimators[i].second.get();

    if (mMeasurementMap.count(id))
    {
      auto const measurement = mMeasurementMap.find(id);
      estimator.correct(measurement->second);
    }
  }

  // Update counters sequentially to avoid race conditions
  for (auto &element : mKalmanEstimators)
  {
    auto const &id = element.first;
    if (mMeasurementMap.count(id))
    {
      // Reset non measurement frames counter, increment tracked frames
      mNonMeasurementFrames[id] = 0;
      mNumberOfTrackedFrames[id]++;
    }
    else
    {
      mNonMeasurementFrames[id]++;
    }
  }

  std::vector<Id> reactivationList;
  for (auto &element : mSuspendedKalmanEstimators)
  {
    if (mMeasurementMap.count(element.first) > 0)
    {
      reactivationList.push_back(element.first);
    }
  }
  for (const auto &id : reactivationList)
  {
    reactivateTrack(id);
    mKalmanEstimators[id].correct(mMeasurementMap[id]);
  }

  std::vector<Id> deletionList;
  std::vector<Id> suspendList;

  // Check no longer valid states and delete accordingly
  for (const auto &element : mNonMeasurementFrames)
  {
    auto const &id = element.first;
    auto const &nonmeasurementFrames = element.second;

    if (isReliable(id))
    {
      uint32_t maxNonMeasurementFrames = 0;
      // let static objects stay longer
      if (mKalmanEstimators[id].currentState().isDynamic())
      {
        if (nonmeasurementFrames > mConfig.mNonMeasurementFramesDynamic)
        {
          deletionList.push_back(id);
        }
      }
      else
      {
        if (nonmeasurementFrames > mConfig.mNonMeasurementFramesStatic)
        {
          suspendList.push_back(id);
        }
      }
    }
    else
    {
      if (nonmeasurementFrames > mConfig.mNonMeasurementFramesDynamic)
      {
        deletionList.push_back(id);
      }
    }
  }
  for (const auto &id : deletionList)
  {
    deleteTrack(id);
  }
  for (const auto &id : suspendList)
  {
    suspendTrack(id);
  }
}

std::vector<TrackedObject> TrackManager::getTracks()
{
  std::vector<TrackedObject> tracks;

  for (const auto &element : mKalmanEstimators)
  {
    tracks.push_back(element.second.currentState());
  }
  for (const auto &element : mSuspendedKalmanEstimators)
  {
    tracks.push_back(element.second.currentState());
  }

  return tracks;
}

std::vector<TrackedObject> TrackManager::getReliableTracks()
{
  std::vector<TrackedObject> tracks;

  for (const auto &element : mKalmanEstimators)
  {
    if (isReliable(element.first))
    {
      tracks.push_back(element.second.currentState());
    }
  }

  return tracks;
}


std::vector<TrackedObject> TrackManager::getUnreliableTracks()
{
  std::vector<TrackedObject> tracks;

  for (const auto &element : mKalmanEstimators)
  {
    if (!isReliable(element.first))
    {
      tracks.push_back(element.second.currentState());
    }
  }

  return tracks;
}

std::vector<TrackedObject> TrackManager::getSuspendedTracks()
{
  std::vector<TrackedObject> tracks;

  for (const auto &element : mSuspendedKalmanEstimators)
  {
    tracks.push_back(element.second.currentState());
  }

  return tracks;
}

std::vector<TrackedObject> TrackManager::getDriftingTracks()
{
  std::vector<TrackedObject> tracks;

  for (const auto &element : mKalmanEstimators)
  {
    if (isReliable(element.first) && (mNonMeasurementFrames[element.first] > mConfig.mNonMeasurementFramesDynamic / 2))
    {
      tracks.push_back(element.second.currentState());
    }
  }

  return tracks;
}

void TrackManager::setMeasurement(const Id &id, const TrackedObject &measurement)
{
  auto previousMeasurement = mMeasurementMap.find(id);
  if (previousMeasurement != mMeasurementMap.end())
  {
    mMeasurementMap[id] = measurement;
  }
  else
  {
    mMeasurementMap.insert(std::make_pair(id, measurement));
  }
}

TrackedObject TrackManager::getTrack(const Id &id)
{
  return getKalmanEstimator(id).currentState();
}

MultiModelKalmanEstimator TrackManager::getKalmanEstimator(const Id &id)
{
  if (mKalmanEstimators.count(id) > 0)
  {
    return mKalmanEstimators[id];
  }
  else if(mSuspendedKalmanEstimators.count(id) > 0)
  {
    return mSuspendedKalmanEstimators[id];
  }
  else
  {
    throw std::runtime_error("The given id is not registered in this TrackManager.");
  }
}


bool TrackManager::hasId(const Id &id)
{
  return (mKalmanEstimators.count(id) > 0) || (mSuspendedKalmanEstimators.count(id) > 0);
}

bool TrackManager::isReliable(const Id &id)
{
  return mNumberOfTrackedFrames[id] >= mConfig.mMaxNumberOfUnreliableFrames;
}

bool TrackManager::isSuspended(const Id &id)
{
  return mSuspendedKalmanEstimators.count(id) > 0;
}

void TrackManager::updateTrackerConfig(int camera_frame_rate)
{
  mConfig.mMaxNumberOfUnreliableFrames = std::ceil(camera_frame_rate*mConfig.mMaxUnreliableTime);
  mConfig.mNonMeasurementFramesDynamic = std::ceil(camera_frame_rate*mConfig.mNonMeasurementTimeDynamic);
  mConfig.mNonMeasurementFramesStatic = std::ceil(camera_frame_rate*mConfig.mNonMeasurementTimeStatic);
  std::cout << "Updated parameters for reference camera frame rate = " << camera_frame_rate << "fps" << std::endl;
  std::cout << "max_unreliable_frames = " << mConfig.mMaxNumberOfUnreliableFrames << std::endl;
  std::cout << "non_measurement_frames_dynamic = " << mConfig.mNonMeasurementFramesDynamic << std::endl;
  std::cout << "non_measurement_frames_static = " << mConfig.mNonMeasurementFramesStatic << std::endl;
}

} // namespace tracking
} // namespace rv
