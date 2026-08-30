// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>
#include <chrono>
#include <iostream>
#include <rv/Utils.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/Classification.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/TrackedObject.hpp>
#include <rv/tracking/TrackManager.hpp>

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
    for (auto & object: objects)
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

TEST(ObjectMatchingTest, Chi2ThresholdMatchesExpectedQuantile)
{
  EXPECT_NEAR(rv::chi2Threshold(0.99, 2), 9.21034, 1e-3);
}

TEST(ObjectMatchingTest, PositionMahalanobisPrefersAlongTrackAxis)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  rv::tracking::TrackManager trackManager(trackerConfig);

  rv::tracking::TrackedObject seed;
  seed.x = 0.0;
  seed.y = 0.0;
  seed.vx = 5.0;
  seed.vy = 0.0;
  seed.length = 0.5;
  seed.width = 0.5;
  seed.height = 0.5;

  auto timestamp = std::chrono::system_clock::now();
  auto trackId = trackManager.createTrack(seed, timestamp);

  for (int i = 0; i < 10; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    seed.x += 0.5;
    trackManager.setMeasurement(trackId, seed);
    trackManager.predict(timestamp);
    trackManager.correct();
    seed = trackManager.getTrack(trackId);
  }

  timestamp += std::chrono::milliseconds(1000);
  trackManager.predict(timestamp);
  auto track = trackManager.getTrack(trackId);

  const double s00 = track.predictedMeasurementCov.at<double>(0, 0);
  const double s11 = track.predictedMeasurementCov.at<double>(1, 1);
  EXPECT_GT(s00, 1.5 * s11) << "expected along-track (x) uncertainty to dominate after +x motion coast";

  const double pred_x = track.predictedMeasurementMean.at<double>(0, 0);
  const double pred_y = track.predictedMeasurementMean.at<double>(1, 0);

  rv::tracking::TrackedObject ahead = seed;
  ahead.x = pred_x + 2.0;
  ahead.y = pred_y;

  rv::tracking::TrackedObject lateral = seed;
  lateral.x = pred_x;
  lateral.y = pred_y + 2.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 2);
  const double max_radius = 10.0;

  std::vector<rv::tracking::TrackedObject> tracks = {track};
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  // Equal Euclidean distance: matcher must prefer the along-track detection.
  rv::tracking::match(tracks, {ahead, lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].first, 0U);
  EXPECT_EQ(assignments[0].second, 0U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  rv::tracking::match(tracks, {lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  // Lateral-only may still pass the chi2 gate; cost must still exceed along-track cost.
  const double dx = 2.0;
  const double dy = 2.0;
  const double det = s00 * s11;
  ASSERT_GT(det, 0.0);
  const double d2_ahead = (dx * dx) * s11 / det;
  const double d2_lateral = (dy * dy) * s00 / det;
  EXPECT_LT(d2_ahead, d2_lateral);
}

TEST(MultipleObjectTrackerTest, PositionMahalanobisFusesMultiCameraDetectionsIntoOneTrack)
{
  // Same world object seen by two cameras with ~1.3 m projection disagreement.
  // Track association uses PositionMahalanobis; cross-camera birth clustering
  // must still fuse in meters so we do not create duplicate frozen tracks.
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0; // reliable immediately for assertion
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  const double chi2_gate = rv::chi2Threshold(0.99, 2);
  rv::tracking::MultipleObjectTracker objectTracker(
    trackerConfig, rv::tracking::DistanceType::PositionMahalanobis, chi2_gate);
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
                      rv::tracking::DistanceType::PositionMahalanobis,
                      chi2_gate,
                      0.5,
                      10.0);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U) << "cross-camera detections of one object must birth a single track";
  EXPECT_NEAR(tracks[0].x, 0.5 * (cam0.x + cam1.x), 1e-6);
  EXPECT_NEAR(tracks[0].y, 0.5 * (cam0.y + cam1.y), 1e-6);
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateAveragesWorldPosition)
{
  // Continuing tracks must not keep last-camera geometry when both cameras match.
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0;
  trackerConfig.mMaxNumberOfUnreliableFrames = 0;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 5.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject cam0;
  cam0.x = 7.11;
  cam0.y = 7.67;
  cam0.width = cam0.length = cam0.height = 0.5;

  rv::tracking::TrackedObject cam1 = cam0;
  cam1.x = 7.91;
  cam1.y = 6.69;

  const double midX = 0.5 * (cam0.x + cam1.x);
  const double midY = 0.5 * (cam0.y + cam1.y);
  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cam0}, {cam1}},
                      timestamp,
                      rv::tracking::DistanceType::Euclidean,
                      5.0,
                      0.5,
                      10.0);

  timestamp += std::chrono::milliseconds(100);
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cam0}, {cam1}},
                      timestamp,
                      rv::tracking::DistanceType::Euclidean,
                      5.0,
                      0.5,
                      10.0);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  // After a correct step the filter should sit near the averaged measurement, not last-camera.
  EXPECT_NEAR(tracks[0].x, midX, 0.15);
  EXPECT_NEAR(tracks[0].y, midY, 0.15);
}
