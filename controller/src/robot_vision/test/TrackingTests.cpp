// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>
#include <algorithm>
#include <chrono>
#include <iostream>
#include <string>
#include <utility>
#include <vector>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/Classification.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace {

using rv::tracking::TrackedObject;
using Detections = std::vector<TrackedObject>;
using DetectionsPerCamera = std::vector<Detections>;

constexpr double kFusionGate = 2.0;

rv::tracking::MultipleObjectTracker makeFusionTracker()
{
  rv::tracking::TrackManagerConfig config;
  config.mMotionModels = {rv::tracking::MotionModel::CV};
  config.mDefaultProcessNoise = 1e-4;
  config.mDefaultMeasurementNoise = 0.2;
  config.mMaxNumberOfUnreliableFrames = 0;
  return rv::tracking::MultipleObjectTracker(config, rv::tracking::DistanceType::Euclidean, kFusionGate);
}

TrackedObject makeBox(double x, double y, double z, double length, double width, double height,
                      const std::string &cameraId = {})
{
  TrackedObject object;
  object.x = x;
  object.y = y;
  object.z = z;
  object.length = length;
  object.width = width;
  object.height = height;
  if (!cameraId.empty())
  {
    object.attributes["camera_id"] = cameraId;
  }
  return object;
}

// Equal-weight average of every fused geometry field, without a camera_id so it is never fused again.
TrackedObject averageOf(const Detections &objects)
{
  TrackedObject average;
  for (const auto &object : objects)
  {
    average.x += object.x;
    average.y += object.y;
    average.z += object.z;
    average.length += object.length;
    average.width += object.width;
    average.height += object.height;
  }
  const double n = static_cast<double>(objects.size());
  average.x /= n;
  average.y /= n;
  average.z /= n;
  average.length /= n;
  average.width /= n;
  average.height /= n;
  return average;
}

void expectSameState(const TrackedObject &actual, const TrackedObject &expected)
{
  constexpr double kTolerance = 1e-9;
  EXPECT_NEAR(actual.x, expected.x, kTolerance);
  EXPECT_NEAR(actual.y, expected.y, kTolerance);
  EXPECT_NEAR(actual.z, expected.z, kTolerance);
  EXPECT_NEAR(actual.vx, expected.vx, kTolerance);
  EXPECT_NEAR(actual.vy, expected.vy, kTolerance);
  EXPECT_NEAR(actual.yaw, expected.yaw, kTolerance);
  EXPECT_NEAR(actual.length, expected.length, kTolerance);
  EXPECT_NEAR(actual.width, expected.width, kTolerance);
  EXPECT_NEAR(actual.height, expected.height, kTolerance);
}

// The twin is fed the expected fused detections directly, so equal states prove what fusion fed the filter.
void expectSameSingleTrack(rv::tracking::MultipleObjectTracker &tracker, rv::tracking::MultipleObjectTracker &twin)
{
  const auto tracks = tracker.getTracks();
  const auto twinTracks = twin.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  ASSERT_EQ(twinTracks.size(), 1U);
  expectSameState(tracks[0], twinTracks[0]);
}

std::vector<TrackedObject> tracksSortedByX(rv::tracking::MultipleObjectTracker &tracker)
{
  auto tracks = tracker.getTracks();
  std::sort(tracks.begin(), tracks.end(), [](const auto &a, const auto &b) { return a.x < b.x; });
  return tracks;
}

std::chrono::system_clock::time_point atMs(int milliseconds)
{
  return std::chrono::system_clock::time_point(std::chrono::milliseconds(milliseconds));
}

} // namespace

TEST(MultipleObjectTrackerTest, SingleDetectionTracking)
{
  // This test simulates the detection of a moving object and tests that the tracker is able to identify it
  // according to the configuration provided
  rv::tracking::TrackedObject object01;

  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  object01.x = 0.0;
  object01.y = 0.0;
  object01.z = 0.0;
  object01.yaw = 0.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.height = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 1e-5;
  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  bool feedObject = true;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {2 m/s, 1.5 m/s}
    object01.x = object01.x + 2.0 * deltaT;
    object01.y = object01.y + 1.5 * deltaT;

    std::vector<rv::tracking::TrackedObject> detectedObjects;

    if (feedObject)
    {
      // feed our simulated detected object
      detectedObjects.push_back(object01);
    }

    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();

    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfUnreliableFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames
        && (k <= (trackerConfig.mMaxNumberOfUnreliableFrames + trackerConfig.mNonMeasurementFramesDynamic)))
    {
      ASSERT_EQ(trackedObjects.size(), 1);
      feedObject = false;
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}

TEST(MultipleObjectTrackerTest, SingleDetectionSingleModelTracking)
{
  // This test simulates the detection of a moving object and tests that the tracker is able to identify it
  // according to the configuration provided
  rv::tracking::TrackedObject object01;

  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  object01.x = 0.0;
  object01.y = 0.0;
  object01.z = 0.0;
  object01.yaw = 0.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.height = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 1e-5;
  trackerConfig.mMotionModels = std::vector<rv::tracking::MotionModel>{rv::tracking::MotionModel::CV};
  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  bool feedObject = true;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {2 m/s, 1.5 m/s}
    object01.x = object01.x + 2.0 * deltaT;
    object01.y = object01.y + 1.5 * deltaT;

    std::vector<rv::tracking::TrackedObject> detectedObjects;

    if (feedObject)
    {
      // feed our simulated detected object
      detectedObjects.push_back(object01);
    }

    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();

    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfUnreliableFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames
        && (k <= (trackerConfig.mMaxNumberOfUnreliableFrames + trackerConfig.mNonMeasurementFramesDynamic)))
    {
      ASSERT_EQ(trackedObjects.size(), 1);
      feedObject = false;
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}



TEST(MultipleObjectTrackerTest, MultipleDetectionTrackingEuclideanDistance)
{
  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  // five objects, in a square arrangement, with the object05 at the center of the box,
  rv::tracking::TrackedObject object01;
  object01.x = 100.0;
  object01.y = 100.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object02;
  object02.x = -100.0;
  object02.y = 100.0;
  object02.width = 1.0;
  object02.length = 2.0;
  object02.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object03;
  object03.x = -100.0;
  object03.y = -100.0;
  object03.width = 1.0;
  object03.length = 2.0;
  object03.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object04;
  object04.x = 100.0;
  object04.y = -100.0;
  object04.width = 1.0;
  object04.length = 2.0;
  object04.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object05;
  object05.x = 0.0;
  object05.y = 0.0;
  object05.width = 1.0;
  object05.length = 2.0;
  object05.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 5.0);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {-5 m/s, -5 m/s}
    object01.x = object01.x - 5.0 * deltaT;
    object01.y = object01.y - 5.0 * deltaT;

    // simulate a movement with velocity {5 m/s, -5 m/s}
    object02.x = object02.x + 5.0 * deltaT;
    object02.y = object02.y - 5.0 * deltaT;

    // simulate a movement with velocity {10 m/s, 10 m/s}
    object03.x = object03.x + 10.0 * deltaT;
    object03.y = object03.y + 10.0 * deltaT;

    // simulate a movement with velocity {-2 m/s, 2 m/s}
    object04.x = object04.x - 2.0 * deltaT;
    object04.y = object04.y + 2.0 * deltaT;

    // simulate a movement with velocity {0 m/s, 0 m/s}
    object05.x = object05.x + 0. * deltaT;
    object05.y = object05.y + 0. * deltaT;

    auto detectedObjects = std::vector<rv::tracking::TrackedObject>{object01, object02, object03, object04, object05};
    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();
    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfNonMeasurementFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames)
    {
      ASSERT_EQ(trackedObjects.size(), 5);
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}

TEST(MultipleObjectTrackerTest, MultipleDetectionTrackingMultiClassEuclideanDistance)
{
  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  // five objects, in a square arrangement, with the object05 at the center of the box,
  rv::tracking::TrackedObject object01;
  object01.x = 100.0;
  object01.y = 100.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object02;
  object02.x = -100.0;
  object02.y = 100.0;
  object02.width = 1.0;
  object02.length = 2.0;
  object02.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object03;
  object03.x = -100.0;
  object03.y = -100.0;
  object03.width = 1.0;
  object03.length = 2.0;
  object03.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object04;
  object04.x = 100.0;
  object04.y = -100.0;
  object04.width = 1.0;
  object04.length = 2.0;
  object04.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object05;
  object05.x = 0.0;
  object05.y = 0.0;
  object05.width = 1.0;
  object05.length = 2.0;
  object05.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::MultiClassEuclidean, 5.0);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {-5 m/s, -5 m/s}
    object01.x = object01.x - 5.0 * deltaT;
    object01.y = object01.y - 5.0 * deltaT;

    // simulate a movement with velocity {5 m/s, -5 m/s}
    object02.x = object02.x + 5.0 * deltaT;
    object02.y = object02.y - 5.0 * deltaT;

    // simulate a movement with velocity {10 m/s, 10 m/s}
    object03.x = object03.x + 10.0 * deltaT;
    object03.y = object03.y + 10.0 * deltaT;

    // simulate a movement with velocity {-2 m/s, 2 m/s}
    object04.x = object04.x - 2.0 * deltaT;
    object04.y = object04.y + 2.0 * deltaT;

    // simulate a movement with velocity {0 m/s, 0 m/s}
    object05.x = object05.x + 0. * deltaT;
    object05.y = object05.y + 0. * deltaT;

    auto detectedObjects = std::vector<rv::tracking::TrackedObject>{object01, object02, object03, object04, object05};
    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();
    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfNonMeasurementFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames)
    {
      ASSERT_EQ(trackedObjects.size(), 5);
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}

TEST(MultipleObjectTrackerTest, MultipleDetectionTrackingMahalanobisDistance)
{
  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  // five objects, in a square arrangement, with the object05 at the center of the box,
  rv::tracking::TrackedObject object01;
  object01.x = 100.0;
  object01.y = 100.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object02;
  object02.x = -100.0;
  object02.y = 100.0;
  object02.width = 1.0;
  object02.length = 2.0;
  object02.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object03;
  object03.x = -100.0;
  object03.y = -100.0;
  object03.width = 1.0;
  object03.length = 2.0;
  object03.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object04;
  object04.x = 100.0;
  object04.y = -100.0;
  object04.width = 1.0;
  object04.length = 2.0;
  object04.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object05;
  object05.x = 0.0;
  object05.y = 0.0;
  object05.width = 1.0;
  object05.length = 2.0;
  object05.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Mahalanobis, 5.0);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {-5 m/s, -5 m/s}
    object01.x = object01.x - 5.0 * deltaT;
    object01.y = object01.y - 5.0 * deltaT;

    // simulate a movement with velocity {5 m/s, -5 m/s}
    object02.x = object02.x + 5.0 * deltaT;
    object02.y = object02.y - 5.0 * deltaT;

    // simulate a movement with velocity {10 m/s, 10 m/s}
    object03.x = object03.x + 10.0 * deltaT;
    object03.y = object03.y + 10.0 * deltaT;

    // simulate a movement with velocity {-2 m/s, 2 m/s}
    object04.x = object04.x - 2.0 * deltaT;
    object04.y = object04.y + 2.0 * deltaT;

    // simulate a movement with velocity {0 m/s, 0 m/s}
    object05.x = object05.x + 0. * deltaT;
    object05.y = object05.y + 0. * deltaT;

    auto detectedObjects = std::vector<rv::tracking::TrackedObject>{object01, object02, object03, object04, object05};
    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();
    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfNonMeasurementFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames)
    {
      ASSERT_EQ(trackedObjects.size(), 5);
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}


TEST(MultipleObjectTrackerTest, MultipleDetectionTrackingMCEMahalanobisDistance)
{
  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  // five objects, in a square arrangement, with the object05 at the center of the box,
  rv::tracking::TrackedObject object01;
  object01.x = 100.0;
  object01.y = 100.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object02;
  object02.x = -100.0;
  object02.y = 100.0;
  object02.width = 1.0;
  object02.length = 2.0;
  object02.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object03;
  object03.x = -100.0;
  object03.y = -100.0;
  object03.width = 1.0;
  object03.length = 2.0;
  object03.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object04;
  object04.x = 100.0;
  object04.y = -100.0;
  object04.width = 1.0;
  object04.length = 2.0;
  object04.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackedObject object05;
  object05.x = 0.0;
  object05.y = 0.0;
  object05.width = 1.0;
  object05.length = 2.0;
  object05.classification = classificationData.classification("Car", 1.0);

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::MCEMahalanobis, 5.0);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {-5 m/s, -5 m/s}
    object01.x = object01.x - 5.0 * deltaT;
    object01.y = object01.y - 5.0 * deltaT;

    // simulate a movement with velocity {5 m/s, -5 m/s}
    object02.x = object02.x + 5.0 * deltaT;
    object02.y = object02.y - 5.0 * deltaT;

    // simulate a movement with velocity {10 m/s, 10 m/s}
    object03.x = object03.x + 10.0 * deltaT;
    object03.y = object03.y + 10.0 * deltaT;

    // simulate a movement with velocity {-2 m/s, 2 m/s}
    object04.x = object04.x - 2.0 * deltaT;
    object04.y = object04.y + 2.0 * deltaT;

    // simulate a movement with velocity {0 m/s, 0 m/s}
    object05.x = object05.x + 0. * deltaT;
    object05.y = object05.y + 0. * deltaT;

    auto detectedObjects = std::vector<rv::tracking::TrackedObject>{object01, object02, object03, object04, object05};
    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getReliableTracks();
    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfNonMeasurementFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames)
    {
      ASSERT_EQ(trackedObjects.size(), 5);
    }
    else
    {
      ASSERT_EQ(trackedObjects.size(), 0);
    }
  }
}



rv::tracking::TrackedObject createObjectAtLocation(double x, double y, const rv::tracking::ClassificationData & classificationData, const std::string & className)
{
  rv::tracking::TrackedObject object;
  object.x = x;
  object.y = y;
  object.width = 1.0;
  object.length = 2.0;
  object.classification = classificationData.classification(className, 1.0);

  return object;
}

TEST(MultipleObjectTrackerTest, MultipleDetectionTrackingStressTest)
{
  auto classificationData = rv::tracking::ClassificationData({"1","2","3","4","5","6","7","8","9","10","11"});

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::MCEMahalanobis, 5.0);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 1000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  // to simplify the creation, we generate objects in a circle of radius r
  std::vector<rv::tracking::TrackedObject> objects;
  std::size_t numberObjects = 100;
  double r = 100;

  for (std::size_t k = 0; k < numberObjects; k++)
  {
    double s = static_cast<double>(k) / static_cast<double>(numberObjects);
    double x = r * std::cos(s * 2.0 * M_PI);
    double y = r * std::sin(s * 2.0 * M_PI);

    objects.push_back(createObjectAtLocation(x, y, classificationData, "1"));
  }

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {
    uint32_t k = timeMilliseconds / deltaMilliseconds;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    // simulate a movement with velocity {10 m/s, 10 m/s}
    for (auto &object : objects)
    {
      object.x = object.x + 10.0 * deltaT;
      object.y = object.y + 10.0 * deltaT;
    }

    objectTracker.track(objects, timestamp);
  }
  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), numberObjects);
}

TEST(MultipleObjectTrackerTest, SingleJumpingDetectionTracking)
{
  // This test simulates the detection of a moving object and tests that the tracker is able to identify it
  // according to the configuration provided
  rv::tracking::TrackedObject object01;

  auto classificationData = rv::tracking::ClassificationData({"Car", "Bike", "Pedestrian"});

  object01.x = 0.0;
  object01.y = 0.0;
  object01.z = 0.0;
  object01.yaw = 0.0;
  object01.width = 1.0;
  object01.length = 2.0;
  object01.height = 2.0;
  object01.classification = classificationData.classification("Car", 0.5);

  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMaxNumberOfUnreliableFrames = 5;
  trackerConfig.mNonMeasurementFramesDynamic = 7;
  trackerConfig.mNonMeasurementFramesStatic = 20;
  trackerConfig.mDefaultProcessNoise = 1e-4;
   trackerConfig.mDefaultMeasurementNoise = 1e-4;
  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig);

  std::vector<rv::tracking::TrackedObject> trackedObjects;

  trackedObjects = objectTracker.getTracks();

  ASSERT_EQ(trackedObjects.size(), 0);

  uint32_t timeMilliseconds = 0;
  uint32_t deltaMilliseconds = 10;
  uint32_t totalMilliseconds = 2000;

  double deltaT = static_cast<double>(deltaMilliseconds) / 1000.0;

  for (uint32_t timeMilliseconds = 0; timeMilliseconds < totalMilliseconds; timeMilliseconds += deltaMilliseconds)
  {

    uint32_t k = timeMilliseconds / deltaMilliseconds;
    double acceleration = 1.0;
    double velocity = 15.1354876;

    auto const &timestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(timeMilliseconds));

    std::string state;
    if ( timeMilliseconds >= 1300)
    {
      // Simulate a velocity jump to 200m/s
      velocity = 200;
    }

    object01.x = object01.x + velocity * deltaT + acceleration * deltaT * deltaT * static_cast<double>(k);


    std::vector<rv::tracking::TrackedObject> detectedObjects;

    // feed our simulated detected object
    detectedObjects.push_back(object01);

    objectTracker.track(detectedObjects, timestamp);
    trackedObjects = objectTracker.getTracks();

    //  || Init: Frame 1 - Unreliable: Frame 1 to N || Reliable: Frame N + 1 || with N=mMaxNumberOfUnreliableFrames
    if (k >= trackerConfig.mMaxNumberOfUnreliableFrames)
    {
      ASSERT_EQ(trackedObjects.size(), 1);
    }
  }
}

TEST(MultipleObjectTrackerTest, MultiCameraDetectionsFuseIntoOneTrack)
{
  // Same world object seen by two cameras with ~1.3 m projection disagreement.
  // Cross-camera birth clustering must fuse them into one track with averaged geometry.
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0; // reliable immediately for assertion
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 2.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject cam0;
  cam0.x = 7.11;
  cam0.y = 7.67;
  cam0.width = cam0.length = cam0.height = 0.5;

  rv::tracking::TrackedObject cam1 = cam0;
  cam1.x = 7.91;
  cam1.y = 6.69;

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cam0}, {cam1}},
                      timestamp,
                      rv::tracking::DistanceType::Euclidean,
                      2.0,
                      0.5);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U) << "cross-camera detections of one object must birth a single track";
  EXPECT_NEAR(tracks[0].x, 0.5 * (cam0.x + cam1.x), 1e-6);
  EXPECT_NEAR(tracks[0].y, 0.5 * (cam0.y + cam1.y), 1e-6);
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthClusteringWeightsCamerasEqually)
{
  // Pairwise averaging would give the last camera weight 1/2 and earlier cameras 1/4.
  auto tracker = makeFusionTracker();
  const Detections cameras = {makeBox(7.0, 7.0, 0.0, 0.5, 0.4, 1.5), makeBox(7.6, 7.3, 0.1, 0.6, 0.5, 1.8),
                              makeBox(8.2, 7.9, 0.3, 0.8, 0.6, 2.1)};

  tracker.track(DetectionsPerCamera{{cameras[0]}, {cameras[1]}, {cameras[2]}}, atMs(10));

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  expectSameState(tracks[0], averageOf(cameras));
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthKeepsDetectionsBeyondGateSeparate)
{
  auto tracker = makeFusionTracker();
  const auto near = makeBox(7.0, 7.0, 0.0, 0.5, 0.5, 1.7);
  const auto far = makeBox(7.0 + kFusionGate + 0.5, 7.0, 0.0, 0.5, 0.5, 1.7);

  tracker.track(DetectionsPerCamera{{near}, {far}}, atMs(10));

  const auto tracks = tracksSortedByX(tracker);
  ASSERT_EQ(tracks.size(), 2U);
  expectSameState(tracks[0], near);
  expectSameState(tracks[1], far);
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthPairsDetectionsOfSeveralObjects)
{
  // Two objects seen by three cameras (listed in different orders): each track averages only its own detections.
  auto tracker = makeFusionTracker();
  const Detections left = {makeBox(0.0, 0.0, 0.0, 0.5, 0.4, 1.6), makeBox(0.4, 0.3, 0.1, 0.6, 0.5, 1.8),
                           makeBox(-0.2, 0.4, 0.2, 0.7, 0.6, 1.7)};
  const Detections right = {makeBox(4.0, 0.0, 0.0, 0.9, 0.8, 1.5), makeBox(4.5, -0.2, 0.1, 1.0, 0.9, 1.6),
                            makeBox(3.8, 0.3, 0.3, 1.1, 1.0, 1.4)};

  tracker.track(DetectionsPerCamera{{left[0], right[0]}, {right[1], left[1]}, {left[2], right[2]}}, atMs(10));

  const auto tracks = tracksSortedByX(tracker);
  ASSERT_EQ(tracks.size(), 2U);
  expectSameState(tracks[0], averageOf(left));
  expectSameState(tracks[1], averageOf(right));
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthSeedsFromFirstMatchedCamera)
{
  // A new track keeps the non-geometry fields (e.g. the "info" detection id) of the first camera
  // in its cluster; track updates instead seed from the last matched camera.
  auto tracker = makeFusionTracker();
  Detections cameras = {makeBox(7.0, 7.0, 0.0, 0.5, 0.5, 1.7), makeBox(7.3, 7.1, 0.0, 0.5, 0.5, 1.7),
                        makeBox(7.6, 6.9, 0.0, 0.5, 0.5, 1.7)};
  for (size_t camera = 0; camera < cameras.size(); ++camera)
  {
    cameras[camera].attributes["info"] = "detection-" + std::to_string(camera);
  }

  tracker.track(DetectionsPerCamera{{cameras[0]}, {cameras[1]}, {cameras[2]}}, atMs(10));

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  ASSERT_EQ(tracks[0].attributes.count("info"), 1U);
  EXPECT_EQ(tracks[0].attributes.at("info"), "detection-0");
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateAveragesWorldPosition)
{
  // Continuing tracks must average all cameras that matched, not keep last-camera geometry.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto cam0 = makeBox(7.11, 7.67, 0.0, 0.5, 0.5, 0.5);
  const auto cam1 = makeBox(7.91, 6.69, 0.0, 0.5, 0.5, 0.5);

  for (int frame = 0; frame < 2; ++frame)
  {
    tracker.track(DetectionsPerCamera{{cam0}, {cam1}}, atMs(10 + 100 * frame));
    twin.track(DetectionsPerCamera{{averageOf({cam0, cam1})}}, atMs(10 + 100 * frame));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, MultiCameraMovingObjectMatchesPreAveragedSingleCamera)
{
  // Three cameras with a fixed per-camera bias on every geometry field, object moving diagonally.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const Detections bias = {makeBox(-0.3, 0.2, 0.0, 0.5, 0.4, 1.6), makeBox(0.4, -0.1, 0.1, 0.6, 0.5, 1.8),
                           makeBox(-0.1, -0.4, 0.2, 0.7, 0.6, 1.7)};

  for (int frame = 0; frame < 4; ++frame)
  {
    DetectionsPerCamera perCamera;
    Detections all;
    for (auto detection : bias)
    {
      detection.x += 7.0 + 0.15 * frame;
      detection.y += 7.0 + 0.1 * frame;
      perCamera.push_back({detection});
      all.push_back(detection);
    }
    tracker.track(perCamera, atMs(10 + 100 * frame));
    twin.track(DetectionsPerCamera{{averageOf(all)}}, atMs(10 + 100 * frame));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateUsesOnlyMatchedCameras)
{
  // A detection outside the gate is not averaged into the track; it births its own track instead.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto camA = makeBox(7.0, 7.0, 0.0, 0.5, 0.5, 1.7);
  const auto camB = makeBox(7.6, 7.3, 0.0, 0.5, 0.5, 1.9);
  tracker.track(DetectionsPerCamera{{camA}, {camB}}, atMs(10));
  twin.track(DetectionsPerCamera{{averageOf({camA, camB})}}, atMs(10));

  auto movedA = camA;
  movedA.x += 0.1;
  auto farB = camB;
  farB.x += 3.0 * kFusionGate;
  tracker.track(DetectionsPerCamera{{movedA}, {farB}}, atMs(110));
  twin.track(DetectionsPerCamera{{movedA}}, atMs(110));

  const auto tracks = tracksSortedByX(tracker);
  const auto twinTracks = twin.getTracks();
  ASSERT_EQ(tracks.size(), 2U);
  ASSERT_EQ(twinTracks.size(), 1U);
  expectSameState(tracks[0], twinTracks[0]);
  expectSameState(tracks[1], farB);
}

TEST(MultipleObjectTrackerTest, StreamingMultiCameraUpdatesAverageWorldPosition)
{
  // Immediate/streaming path: sequential single-camera track() calls must still
  // average geometry using recent per-camera measurements (camera_id attribute).
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto cam0 = makeBox(7.11, 7.67, 0.0, 0.5, 0.5, 0.5, "Cam_x1_0");
  const auto cam1 = makeBox(7.91, 6.69, 0.0, 0.5, 0.5, 0.5, "Cam_x2_0");

  for (int update = 0; update < 4; ++update)
  {
    tracker.track(Detections{(update % 2 == 0) ? cam0 : cam1}, atMs(10 + 50 * update));
    twin.track(Detections{update == 0 ? averageOf({cam0}) : averageOf({cam0, cam1})}, atMs(10 + 50 * update));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, StreamingMultiCameraFusesAllGeometryFields)
{
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto camA = makeBox(7.0, 7.0, 0.0, 0.5, 0.4, 1.6, "Cam_A");
  const auto camB = makeBox(7.6, 7.3, 0.2, 0.7, 0.6, 1.9, "Cam_B");

  tracker.track(Detections{camA}, atMs(10));
  tracker.track(Detections{camB}, atMs(60));
  twin.track(Detections{averageOf({camA})}, atMs(10));
  twin.track(Detections{averageOf({camA, camB})}, atMs(60));

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, StreamingThreeCamerasAverageLatestSamples)
{
  // Round-robin cameras: once all three have reported, every update averages the latest sample of each.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const Detections cameras = {makeBox(7.0, 7.0, 0.0, 0.5, 0.4, 1.5, "Cam_A"),
                              makeBox(7.6, 7.3, 0.1, 0.6, 0.5, 1.8, "Cam_B"),
                              makeBox(8.2, 7.9, 0.3, 0.8, 0.6, 2.1, "Cam_C")};
  const Detections expected = {averageOf({cameras[0]}), averageOf({cameras[0], cameras[1]}), averageOf(cameras),
                               averageOf(cameras), averageOf(cameras)};

  for (int update = 0; update < static_cast<int>(expected.size()); ++update)
  {
    tracker.track(Detections{cameras[update % cameras.size()]}, atMs(10 + 33 * update));
    twin.track(Detections{expected[update]}, atMs(10 + 33 * update));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, StreamingMultiCameraIgnoresSamplesOutsideHold)
{
  const auto camA = makeBox(7.0, 7.0, 0.0, 0.5, 0.5, 1.7, "Cam_A");
  const auto camB = makeBox(7.6, 7.3, 0.0, 0.5, 0.5, 1.9, "Cam_B");
  const int holdMs = static_cast<int>(rv::tracking::kStreamingMultiCamHold.count());

  for (const auto &[delayMs, fused] : {std::pair{holdMs - 10, true}, std::pair{holdMs + 10, false}})
  {
    SCOPED_TRACE("camera B delay " + std::to_string(delayMs) + " ms");
    auto tracker = makeFusionTracker();
    auto twin = makeFusionTracker();

    tracker.track(Detections{camA}, atMs(10));
    tracker.track(Detections{camB}, atMs(10 + delayMs));
    twin.track(Detections{averageOf({camA})}, atMs(10));
    twin.track(Detections{fused ? averageOf({camA, camB}) : averageOf({camB})}, atMs(10 + delayMs));

    expectSameSingleTrack(tracker, twin);
  }
}

TEST(MultipleObjectTrackerTest, StreamingMultiCameraUsesLatestSamplePerCamera)
{
  // A camera's newer detection replaces its cached one; the older sample is not averaged in again.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto camA = makeBox(7.0, 7.0, 0.0, 0.5, 0.5, 1.7, "Cam_A");
  auto movedA = camA;
  movedA.x += 0.4;
  const auto camB = makeBox(7.8, 7.3, 0.0, 0.5, 0.5, 1.9, "Cam_B");

  tracker.track(Detections{camA}, atMs(10));
  tracker.track(Detections{movedA}, atMs(30));
  tracker.track(Detections{camB}, atMs(50));
  twin.track(Detections{averageOf({camA})}, atMs(10));
  twin.track(Detections{averageOf({movedA})}, atMs(30));
  twin.track(Detections{averageOf({movedA, camB})}, atMs(50));

  expectSameSingleTrack(tracker, twin);
}

// Streaming path: camera B reports once, then stays silent while camera A keeps reporting
// within the hold window. B's cached detection must be averaged into A's updates only once;
// reusing it in every update double-counts it and pulls the track to the A/B midpoint.
TEST(MultipleObjectTrackerTest, StreamingMultiCameraDoesNotReuseCachedDetection)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0;
  trackerConfig.mMaxNumberOfUnreliableFrames = 0;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 5.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject camA;
  camA.x = 7.0;
  camA.y = 7.0;
  camA.width = camA.length = camA.height = 0.5;
  camA.attributes["camera_id"] = "Cam_A";

  rv::tracking::TrackedObject camB = camA;
  camB.x = 8.0;
  camB.attributes["camera_id"] = "Cam_B";

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<rv::tracking::TrackedObject>{camA}, timestamp,
                      rv::tracking::DistanceType::Euclidean, 5.0, 0.5);
  timestamp += std::chrono::milliseconds(20);
  objectTracker.track(std::vector<rv::tracking::TrackedObject>{camB}, timestamp,
                      rv::tracking::DistanceType::Euclidean, 5.0, 0.5);

  // Camera B stays silent while camera A keeps reporting inside the hold window.
  for (int i = 0; i < 11; ++i)
  {
    timestamp += std::chrono::milliseconds(20);
    objectTracker.track(std::vector<rv::tracking::TrackedObject>{camA}, timestamp,
                        rv::tracking::DistanceType::Euclidean, 5.0, 0.5);
  }

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  // One B detection among 13 updates: the track must sit closer to A than to the A/B midpoint.
  EXPECT_LT(tracks[0].x, 0.5 * (camA.x + 0.5 * (camA.x + camB.x)));
}
