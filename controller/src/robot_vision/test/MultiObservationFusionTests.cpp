// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/Classification.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace {

rv::tracking::TrackedObject makeObjectAt(double x, double y)
{
  static const rv::tracking::ClassificationData classificationData({"object"});

  rv::tracking::TrackedObject object;
  object.x = x;
  object.y = y;
  object.width = 1.0;
  object.length = 1.0;
  object.height = 1.0;
  object.classification = classificationData.classification("object", 1.0);
  return object;
}

rv::tracking::TrackManagerConfig fusionConfig()
{
  rv::tracking::TrackManagerConfig config;
  config.mMaxNumberOfUnreliableFrames = 0;
  config.mDefaultProcessNoise = 1e-4;
  config.mDefaultMeasurementNoise = 1e-2;
  return config;
}

const auto InitialTimestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(0));
const auto NextTimestamp = InitialTimestamp + std::chrono::milliseconds(100);

} // namespace

// A track matched by two cameras must be corrected by both observations, not only the last one.
TEST(MultiObservationFusionTest, TrackFusesAllMatchedObservationsNotOnlyLast)
{
  rv::tracking::MultipleObjectTracker trackerBoth(fusionConfig());
  rv::tracking::MultipleObjectTracker trackerLastOnly(fusionConfig());

  // Establish an identical reliable track in both trackers.
  trackerBoth.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{makeObjectAt(0.5, 0.0)}},
                    InitialTimestamp,
                    rv::tracking::DistanceType::Euclidean,
                    3.0);
  trackerLastOnly.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{makeObjectAt(0.5, 0.0)}},
                        InitialTimestamp,
                        rv::tracking::DistanceType::Euclidean,
                        3.0);

  // Two cameras observe the object at different X; camera 1 (x=1.0) is the last match.
  const auto cameraZero = makeObjectAt(0.0, 0.0);
  const auto cameraOne = makeObjectAt(1.0, 0.0);

  // Both observations are fused into the track.
  trackerBoth.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cameraZero}, {cameraOne}},
                    NextTimestamp,
                    rv::tracking::DistanceType::Euclidean,
                    3.0);
  // Only the last camera observation is fed, matching the previous single-observation behavior.
  trackerLastOnly.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cameraOne}},
                        NextTimestamp,
                        rv::tracking::DistanceType::Euclidean,
                        3.0);

  const auto both = trackerBoth.getReliableTracks();
  const auto lastOnly = trackerLastOnly.getReliableTracks();
  ASSERT_EQ(both.size(), 1);
  ASSERT_EQ(lastOnly.size(), 1);

  // Fusing camera 0 (x=0.0) pulls the estimate toward smaller X than using camera 1 (x=1.0) alone.
  EXPECT_LT(both[0].x, lastOnly[0].x);
  // The fused estimate stays between the two observations, so both contributed.
  EXPECT_GT(both[0].x, 0.0);
  EXPECT_LT(both[0].x, 1.0);
}

// A track matched by a single camera behaves exactly as the single-object tracking path.
TEST(MultiObservationFusionTest, SingleCameraMatchMatchesSingleObjectPath)
{
  rv::tracking::MultipleObjectTracker trackerBatched(fusionConfig());
  rv::tracking::MultipleObjectTracker trackerSingle(fusionConfig());

  trackerBatched.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{makeObjectAt(0.0, 0.0)}},
                       InitialTimestamp,
                       rv::tracking::DistanceType::Euclidean,
                       3.0);
  trackerSingle.track(std::vector<rv::tracking::TrackedObject>{makeObjectAt(0.0, 0.0)},
                      InitialTimestamp,
                      rv::tracking::DistanceType::Euclidean,
                      3.0);

  trackerBatched.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{makeObjectAt(0.5, 0.25)}},
                       NextTimestamp,
                       rv::tracking::DistanceType::Euclidean,
                       3.0);
  trackerSingle.track(std::vector<rv::tracking::TrackedObject>{makeObjectAt(0.5, 0.25)},
                      NextTimestamp,
                      rv::tracking::DistanceType::Euclidean,
                      3.0);

  const auto batched = trackerBatched.getReliableTracks();
  const auto single = trackerSingle.getReliableTracks();
  ASSERT_EQ(batched.size(), 1);
  ASSERT_EQ(single.size(), 1);

  EXPECT_NEAR(batched[0].x, single[0].x, 1e-9);
  EXPECT_NEAR(batched[0].y, single[0].y, 1e-9);
}
