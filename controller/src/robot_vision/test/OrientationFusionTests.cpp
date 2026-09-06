// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <cmath>
#include <string>
#include <unordered_map>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/Classification.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace {

rv::tracking::TrackedObject makeDetection(double x, double y, double yaw, bool hasOrientation,
                                          double confidence = 1.0)
{
  static const rv::tracking::ClassificationData classificationData({"vehicle"});

  rv::tracking::TrackedObject object;
  object.x = x;
  object.y = y;
  object.z = 0.0;
  object.yaw = yaw;
  object.width = 1.5;
  object.length = 4.0;
  object.height = 1.5;
  object.classification = classificationData.classification("vehicle", confidence);
  object.attributes = {{"info", "det"}};
  if (hasOrientation)
  {
    rv::tracking::orientation::setHasOrientation(object, true);
  }
  return object;
}

rv::tracking::MultipleObjectTracker makeTracker()
{
  rv::tracking::TrackManagerConfig config;
  config.mMaxNumberOfUnreliableFrames = 0;
  config.mNonMeasurementFramesDynamic = 20;
  config.mNonMeasurementFramesStatic = 20;
  config.mDefaultProcessNoise = 1e-4;
  config.mDefaultMeasurementNoise = 1e-4;
  return rv::tracking::MultipleObjectTracker(config);
}

std::chrono::system_clock::time_point atMs(int milliseconds)
{
  return std::chrono::system_clock::time_point(std::chrono::milliseconds(milliseconds));
}

} // namespace

TEST(OrientationFusionTest, CameraUpdateDoesNotPullYawToZero)
{
  auto tracker = makeTracker();
  const double lidarYaw = 1.2;

  tracker.track({makeDetection(0.0, 0.0, lidarYaw, true)}, atMs(10));
  auto tracks = tracker.getReliableTracks();
  ASSERT_EQ(tracks.size(), 1u);
  EXPECT_NEAR(tracks[0].yaw, lidarYaw, 0.15);
  EXPECT_TRUE(rv::tracking::orientation::orientationObserved(tracks[0]));

  // Camera-only update at nearly the same place with identity yaw.
  tracker.track({makeDetection(0.05, 0.0, 0.0, false)}, atMs(110));
  tracks = tracker.getReliableTracks();
  ASSERT_EQ(tracks.size(), 1u);
  EXPECT_NEAR(tracks[0].yaw, lidarYaw, 0.25);
  EXPECT_TRUE(rv::tracking::orientation::orientationObserved(tracks[0]));
  EXPECT_FALSE(rv::tracking::orientation::hasOrientation(tracks[0]));
}

TEST(OrientationFusionTest, BatchedFusePrefersOrientingYawOverLastCamera)
{
  auto tracker = makeTracker();
  const double initialYaw = 0.8;
  const double lidarYaw = 1.5;

  tracker.track({makeDetection(0.0, 0.0, initialYaw, true)}, atMs(10));
  ASSERT_EQ(tracker.getReliableTracks().size(), 1u);

  // Camera listed last so last-match geometry would otherwise win with yaw=0.
  std::vector<std::vector<rv::tracking::TrackedObject>> batch = {
    {makeDetection(0.02, 0.0, lidarYaw, true, 0.95)},
    {makeDetection(0.02, 0.0, 0.0, false, 0.99)},
  };
  tracker.track(batch, atMs(110));

  auto tracks = tracker.getReliableTracks();
  ASSERT_EQ(tracks.size(), 1u);
  EXPECT_NEAR(tracks[0].yaw, lidarYaw, 0.25);
  EXPECT_TRUE(rv::tracking::orientation::orientationObserved(tracks[0]));
}

TEST(OrientationFusionTest, OrientationAttributeHelpers)
{
  rv::tracking::TrackedObject object;
  EXPECT_FALSE(rv::tracking::orientation::hasOrientation(object));
  EXPECT_FALSE(rv::tracking::orientation::orientationObserved(object));

  rv::tracking::orientation::setHasOrientation(object, true);
  EXPECT_TRUE(rv::tracking::orientation::hasOrientation(object));
  EXPECT_TRUE(rv::tracking::orientation::orientationObserved(object));

  rv::tracking::TrackedObject prior;
  rv::tracking::orientation::markOrientationObserved(prior);
  rv::tracking::TrackedObject measurement;
  rv::tracking::TrackedObject out;
  out.attributes = measurement.attributes;
  rv::tracking::orientation::mergeOrientationAttributes(prior, measurement, out);
  EXPECT_TRUE(rv::tracking::orientation::orientationObserved(out));
  EXPECT_FALSE(rv::tracking::orientation::hasOrientation(out));
}
