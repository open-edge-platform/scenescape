// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <string>
#include <unordered_map>
#include <vector>

#include <gtest/gtest.h>

#include <rv/tracking/Classification.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace {

rv::tracking::TrackedObject makeObject(double x, const std::unordered_map<std::string, std::string> &attributes)
{
  static const rv::tracking::ClassificationData classificationData({"object"});

  rv::tracking::TrackedObject object;
  object.x = x;
  object.width = 1.0;
  object.length = 1.0;
  object.height = 1.0;
  object.classification = classificationData.classification("object", 1.0);
  object.attributes = attributes;
  return object;
}

rv::tracking::MultipleObjectTracker makeTracker()
{
  rv::tracking::TrackManagerConfig config;
  config.mMaxNumberOfUnreliableFrames = 0;
  config.mDefaultProcessNoise = 1e-4;
  config.mDefaultMeasurementNoise = 1e-4;
  return rv::tracking::MultipleObjectTracker(config);
}

const auto InitialTimestamp = std::chrono::system_clock::time_point(std::chrono::milliseconds(10));

TEST(MetadataFusionPolicyTest, CoversEveryWinnerSelectionCase)
{
  struct Case
  {
    const char *name;
    bool winnerExists;
    std::optional<double> candidateConfidence;
    size_t candidateCameraIndex;
    std::optional<double> winnerConfidence;
    size_t winnerCameraIndex;
    bool expected;
  };

  const std::vector<Case> cases = {
    {"no winner without confidence", false, std::nullopt, 0, std::nullopt, 0, true},
    {"no winner with confidence", false, 0.5, 0, std::nullopt, 0, true},
    {"candidate confidence beats missing winner confidence", true, 0.5, 0, std::nullopt, 1, true},
    {"missing candidate confidence loses to winner confidence", true, std::nullopt, 1, 0.5, 0, false},
    {"higher confidence wins", true, 0.9, 0, 0.7, 1, true},
    {"lower confidence loses", true, 0.7, 1, 0.9, 0, false},
    {"equal confidence from later camera wins", true, 0.9, 1, 0.9, 0, true},
    {"equal confidence from same camera loses", true, 0.9, 0, 0.9, 0, false},
    {"equal confidence from earlier camera loses", true, 0.9, 0, 0.9, 1, false},
    {"no confidence from later camera wins", true, std::nullopt, 1, std::nullopt, 0, true},
    {"no confidence from same camera loses", true, std::nullopt, 0, std::nullopt, 0, false},
    {"no confidence from earlier camera loses", true, std::nullopt, 0, std::nullopt, 1, false},
  };

  for (const auto &testCase : cases)
  {
    SCOPED_TRACE(testCase.name);
    EXPECT_EQ(rv::tracking::metadata_fusion::shouldReplace(testCase.winnerExists,
                                                           testCase.candidateConfidence,
                                                           testCase.candidateCameraIndex,
                                                           testCase.winnerConfidence,
                                                           testCase.winnerCameraIndex),
              testCase.expected);
  }
}

TEST(MetadataFusionTest, HighestConfidenceWinsPerField)
{
  auto tracker = makeTracker();
  auto highConfidence = makeObject(
    0.0, {{"metadata.gender", R"({"label":"female","confidence":0.9})"}, {"metadata_confidence.gender", "0.9"}});
  auto lowConfidence = makeObject(
    0.0, {{"metadata.gender", R"({"label":"male","confidence":0.7})"}, {"metadata_confidence.gender", "0.7"}});

  tracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{highConfidence}, {lowConfidence}},
                InitialTimestamp,
                rv::tracking::DistanceType::Euclidean,
                2.0);

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1);
  EXPECT_EQ(tracks[0].attributes.at("metadata.gender"), R"({"label":"female","confidence":0.9})");
  EXPECT_EQ(tracks[0].attributes.at("metadata_confidence.gender"), "0.9");
}

TEST(MetadataFusionTest, MergesDisjointFields)
{
  auto tracker = makeTracker();
  auto plate = makeObject(0.0, {{"metadata.plate", R"({"label":"XYZ-789"})"}});
  auto gender = makeObject(0.0, {{"metadata.gender", R"({"label":"female"})"}});

  tracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{plate}, {gender}},
                InitialTimestamp,
                rv::tracking::DistanceType::Euclidean,
                2.0);

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1);
  EXPECT_EQ(tracks[0].attributes.at("metadata.plate"), R"({"label":"XYZ-789"})");
  EXPECT_EQ(tracks[0].attributes.at("metadata.gender"), R"({"label":"female"})");
}

TEST(MetadataFusionTest, LatestCameraWinsWithoutConfidence)
{
  auto tracker = makeTracker();
  auto earlier = makeObject(0.0, {{"metadata.age", R"({"label":"adult"})"}});
  auto latest = makeObject(0.0, {{"metadata.age", R"({"label":"senior"})"}});

  tracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{earlier}, {latest}},
                InitialTimestamp,
                rv::tracking::DistanceType::Euclidean,
                2.0);

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1);
  EXPECT_EQ(tracks[0].attributes.at("metadata.age"), R"({"label":"senior"})");
}

TEST(MetadataFusionTest, CurrentSingleCameraMeasurementClearsPreviousFusion)
{
  auto tracker = makeTracker();
  auto plate = makeObject(0.0, {{"metadata.plate", R"({"label":"XYZ-789"})"}});
  auto gender = makeObject(0.0, {{"metadata.gender", R"({"label":"female"})"}});
  tracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{plate}, {gender}},
                InitialTimestamp,
                rv::tracking::DistanceType::Euclidean,
                2.0);

  auto current = makeObject(0.1, {{"metadata.gender", R"({"label":"male"})"}});
  tracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{current}},
                InitialTimestamp + std::chrono::milliseconds(100),
                rv::tracking::DistanceType::Euclidean,
                2.0);

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1);
  EXPECT_EQ(tracks[0].attributes.at("metadata.gender"), R"({"label":"male"})");
  EXPECT_EQ(tracks[0].attributes.count("metadata.plate"), 0);
}

TEST(MetadataFusionTest, MetadataDoesNotBypassSingleCameraCorrection)
{
  auto tracker = makeTracker();
  auto initial = makeObject(0.0, {{"metadata.gender", R"({"label":"female"})"}});
  tracker.track(
    std::vector<rv::tracking::TrackedObject>{initial}, InitialTimestamp, rv::tracking::DistanceType::Euclidean, 2.0);

  auto current = makeObject(0.5, {{"metadata.gender", R"({"label":"female"})"}});
  tracker.track(std::vector<rv::tracking::TrackedObject>{current},
                InitialTimestamp + std::chrono::milliseconds(100),
                rv::tracking::DistanceType::Euclidean,
                2.0);

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1);
  EXPECT_TRUE(tracks[0].corrected);
  EXPECT_GT(tracks[0].x, 0.0);
}

} // namespace