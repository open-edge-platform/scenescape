// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <numbers>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include "support/ScenarioRecorder.hpp"

namespace {

using namespace rv::tracking::test;

std::vector<std::string> readLines(const std::filesystem::path &path)
{
  std::vector<std::string> lines;
  std::ifstream file(path);
  for (std::string line; std::getline(file, line);)
  {
    lines.push_back(line);
  }
  return lines;
}

size_t countContaining(const std::vector<std::string> &lines, std::string_view text)
{
  return static_cast<size_t>(std::count_if(
    lines.begin(), lines.end(), [text](const std::string &line) { return line.find(text) != std::string::npos; }));
}

std::vector<double> numbersAfter(const std::string &line, std::string_view key)
{
  std::vector<double> result;
  std::string keyPattern = "\"" + std::string(key) + "\":[";
  size_t keyPos = line.find(keyPattern);
  if (keyPos == std::string::npos)
  {
    return result;
  }
  size_t start = keyPos + keyPattern.length();
  size_t end = line.find("]", start);
  if (end == std::string::npos)
  {
    return result;
  }
  std::string content = line.substr(start, end - start);

  // Parse comma-separated numbers
  size_t pos = 0;
  while (pos < content.length())
  {
    size_t commaPos = content.find(',', pos);
    if (commaPos == std::string::npos)
    {
      commaPos = content.length();
    }
    std::string numStr = content.substr(pos, commaPos - pos);
    // Trim whitespace
    size_t firstChar = numStr.find_first_not_of(" \t\n\r");
    size_t lastChar = numStr.find_last_not_of(" \t\n\r");
    if (firstChar != std::string::npos)
    {
      numStr = numStr.substr(firstChar, lastChar - firstChar + 1);
      try
      {
        result.push_back(std::stod(numStr));
      }
      catch (const std::exception &)
      {
        // Skip invalid numbers
      }
    }
    pos = commaPos + 1;
  }
  return result;
}

class ScenarioRecorderTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    mRoot = std::filesystem::path(::testing::TempDir()) / "rv_scenario_recorder"
      / ::testing::UnitTest::GetInstance()->current_test_info()->name();
    std::filesystem::remove_all(mRoot);
  }

  void TearDown() override
  {
    std::filesystem::remove_all(mRoot);
  }

  std::filesystem::path mRoot;
};

} // namespace

TEST(ScenarioRecorderJsonTest, WritesCompactJson)
{
  JsonWriter json;
  json.beginObject();
  json.key("a").value(0.1);
  json.key("b").value(2.0);
  json.key("c").value(std::numeric_limits<double>::quiet_NaN());
  json.key("d").value(-3);
  json.key("e").value("q\"\\\n\x01");
  json.key("f").value(cv::Mat(cv::Matx21d(1.5, -2.0)));
  json.key("g").value(cv::Mat(cv::Matx22d(1.0, 2.0, 3.0, 4.0)));
  json.key("h").value(cv::Mat());
  json.key("i").beginArray().endArray();
  json.key("j").value(cv::Matx22d(1.0, 0.5, 0.5, 2.0));
  json.endObject();

  EXPECT_EQ(
    json.str(),
    R"({"a":0.1,"b":2,"c":null,"d":-3,"e":"q\"\\\n\u0001","f":[1.5,-2],"g":[[1,2],[3,4]],"h":null,"i":[],"j":[[1,0.5],[0.5,2]]})");
}

TEST(ScenarioRecorderJsonTest, FormatsTimestampsAndYaw)
{
  EXPECT_EQ(isoTimestamp(toMicroseconds(0.1)), "1970-01-01T00:00:00.100000Z");
  EXPECT_EQ(isoTimestamp(toMicroseconds(86400.0 + 3661.5)), "1970-01-02T01:01:01.500000Z");

  const auto quaternion = yawQuaternion(std::numbers::pi / 2.0);
  EXPECT_DOUBLE_EQ(quaternion[2], std::sqrt(0.5));
  EXPECT_DOUBLE_EQ(quaternion[3], std::sqrt(0.5));
}

TEST_F(ScenarioRecorderTest, RecordsScenarioFiles)
{
  const auto truth = Trajectory({.speed = 2.0, .box = kCar}).straight(1.0).sample(10.0);
  Sensor lidar{.id = "lidar", .positionNoise = 0.05, .orienting = true};
  {
    ScenarioRecorder recorder("case one", mRoot);
    recorder.truth(truth);
    FilterRun run(productionConfig(), &recorder);
    run.feed(observe(truth, lidar));
    run.coast(0.5);
  }

  const auto directory = mRoot / "ScenarioRecorderTest.RecordsScenarioFiles" / "case_one";
  const auto groundTruth = readLines(directory / "groundtruth.jsonl");
  ASSERT_EQ(groundTruth.size(), truth.size());
  EXPECT_EQ(groundTruth.front(),
            R"({"timestamp":"1970-01-01T00:00:00.000000Z","objects":[{"id":1,"category":"vehicle",)"
            R"("translation":[0,0,0],"size":[4.5,1.8,1.5],"rotation":[0,0,0,1],"velocity":[2,0,0],)"
            R"("truth":{"speed":2,"yaw_rate":0,"acceleration":0}}]})");

  const auto detections = readLines(directory / "detections.jsonl");
  ASSERT_EQ(detections.size(), truth.size());
  EXPECT_TRUE(detections.front().starts_with(
    R"({"id":"lidar","timestamp":"1970-01-01T00:00:00.000000Z","objects":{"vehicle":[{"id":1,"translation":[)"));
  EXPECT_EQ(countContaining(detections, R"("rotation":[)"), truth.size());

  // Init, ten corrections and the coast.
  const auto tracks = readLines(directory / "tracks.jsonl");
  ASSERT_EQ(tracks.size(), truth.size() + 1);
  EXPECT_TRUE(tracks.front().starts_with(R"({"id":"ScenarioRecorderTest.RecordsScenarioFiles/case_one",)"
                                         R"("name":"ScenarioRecorderTest.RecordsScenarioFiles/case_one",)"
                                         R"("timestamp":"1970-01-01T00:00:00.000000Z",)"
                                         R"("objects":[{"id":"1","category":"vehicle","translation":[)"));
  EXPECT_NE(tracks.back().find(R"("timestamp":"1970-01-01T00:00:01.500000Z")"), std::string::npos);

  // Config, init, ten updates and the coast.
  const auto estimator = readLines(directory / "estimator.jsonl");
  ASSERT_EQ(estimator.size(), 1 + truth.size() + 1);
  EXPECT_TRUE(estimator.front().starts_with(R"({"type":"config","track_id":"1","motion_models":["CV","CA","CTRV"],)"));
  EXPECT_TRUE(estimator[1].starts_with(
    R"({"type":"step","track_id":"1","timestamp":"1970-01-01T00:00:00.000000Z","mu":[0.3333333333333333,)"));
  EXPECT_TRUE(estimator[1].ends_with(R"("z_pred":null,"S":null})"));
  EXPECT_EQ(countContaining(estimator, R"("z_pred":[)"), truth.size());
  EXPECT_NE(estimator.back().find(R"("timestamp":"1970-01-01T00:00:01.500000Z")"), std::string::npos);
}

TEST_F(ScenarioRecorderTest, RecordsTrackerRun)
{
  constexpr double kFps = 10.0;
  const auto car = Trajectory({.speed = 2.0, .box = kCar}).straight(1.5).sample(kFps);
  const auto person = Trajectory({.y = 10.0, .speed = 1.0, .box = kPerson}).straight(1.5).sample(kFps);
  Sensor camera;
  {
    ScenarioRecorder recorder("tracker", mRoot);
    recorder.truth(car, 1);
    recorder.truth(person, 2);
    auto observations = observe(car, camera, 1);
    const auto personObservations = observe(person, camera, 2);
    observations.insert(observations.end(), personObservations.begin(), personObservations.end());
    TrackerRun run(positionMahalanobisAssociation(), kFps, productionTrackerConfig(), &recorder);
    run.play(sampleTimes(car), observations);
  }

  const auto directory = mRoot / "ScenarioRecorderTest.RecordsTrackerRun" / "tracker";
  const auto groundTruth = readLines(directory / "groundtruth.jsonl");
  ASSERT_EQ(groundTruth.size(), car.size());
  EXPECT_EQ(countContaining(groundTruth, R"("id":2,"category":"person")"), car.size());

  // One frame per timestamp, detections grouped by the category of their object.
  const auto detections = readLines(directory / "detections.jsonl");
  ASSERT_EQ(detections.size(), car.size());
  EXPECT_NE(detections.front().find(R"("objects":{"person":[{"id":2,)"), std::string::npos);
  EXPECT_NE(detections.front().find(R"("vehicle":[{"id":1,)"), std::string::npos);

  // Tracks are published once reliable: corrected in 10 frames (1 s), i.e. from 1.0 s to 1.5 s.
  const auto tracks = readLines(directory / "tracks.jsonl");
  ASSERT_EQ(tracks.size(), 6U);
  EXPECT_NE(tracks.front().find(R"("timestamp":"1970-01-01T00:00:01.000000Z")"), std::string::npos);
  EXPECT_EQ(countContaining(tracks, R"({"id":"1","category":"vehicle",)"), tracks.size());
  EXPECT_EQ(countContaining(tracks, R"({"id":"2","category":"person",)"), tracks.size());

  // A config per track with the association gate, then one predicted step per track and published frame.
  const auto estimator = readLines(directory / "estimator.jsonl");
  ASSERT_EQ(estimator.size(), 2 + 2 * tracks.size());
  EXPECT_TRUE(estimator.front().ends_with(
    R"("association":{"method":"position_mahalanobis","gate_probability":0.99,"max_radius_m":10}})"));
  EXPECT_EQ(countContaining(estimator, R"("z_pred":[)"), 2 * tracks.size());
}

TEST_F(ScenarioRecorderTest, WithoutDirectoryRecordsNothing)
{
  const auto truth = Trajectory({.speed = 1.0, .box = kPerson}).straight(0.5).sample(10.0);
  Sensor camera;
  ScenarioRecorder recorder("off", std::filesystem::path());
  EXPECT_FALSE(recorder.enabled());
  recorder.truth(truth);
  FilterRun run(productionConfig(), &recorder);
  run.feed(observe(truth, camera));
  recorder.write();

  EXPECT_FALSE(std::filesystem::exists(mRoot));
}

TEST_F(ScenarioRecorderTest, DirectoryComesFromEnvironment)
{
  const char *saved = std::getenv(ScenarioRecorder::kEnvironmentVariable);
  const std::optional<std::string> previous = saved != nullptr ? std::optional<std::string>(saved) : std::nullopt;

  setenv(ScenarioRecorder::kEnvironmentVariable, mRoot.c_str(), 1);
  const ScenarioRecorder enabled("../case");
  unsetenv(ScenarioRecorder::kEnvironmentVariable);
  const ScenarioRecorder disabled("case");
  if (previous)
  {
    setenv(ScenarioRecorder::kEnvironmentVariable, previous->c_str(), 1);
  }

  EXPECT_EQ(enabled.directory(), mRoot / "ScenarioRecorderTest.DirectoryComesFromEnvironment" / "___case");
  EXPECT_FALSE(disabled.enabled());
}

// Records vertical motion data
TEST_F(ScenarioRecorderTest, RecordsVerticalMotion)
{
  // Verify that climbing truth and estimated vertical states are recorded correctly.
  const auto climbingTruth
    = Trajectory({.speed = 1.0, .box = kCar}).straight(1.0).climb(0.5, 2.0).straight(1.0).sample(10.0);

  Sensor camera{.positionNoise = 0.05};
  {
    ScenarioRecorder recorder("vertical motion", mRoot);
    recorder.truth(climbingTruth);
    FilterRun run(productionConfig(), &recorder);
    run.feed(observe(climbingTruth, camera));
  }

  const auto directory = mRoot / "ScenarioRecorderTest.RecordsVerticalMotion" / "vertical_motion";

  // groundtruth.jsonl: find a line with translation[2] (z) > 0.5 and velocity[2] (vz) == 0.5
  const auto groundTruth = readLines(directory / "groundtruth.jsonl");
  ASSERT_GT(groundTruth.size(), 0U);

  bool foundNonZeroZ = false;
  bool foundNonZeroVz = false;
  for (const auto &line : groundTruth)
  {
    auto translation = numbersAfter(line, "translation");
    if (translation.size() >= 3 && translation[2] > 0.5)
    {
      foundNonZeroZ = true;
    }
    auto velocity = numbersAfter(line, "velocity");
    if (velocity.size() >= 3 && std::fabs(velocity[2] - 0.5) < 1e-9)
    {
      foundNonZeroVz = true;
    }
  }
  EXPECT_TRUE(foundNonZeroZ) << "groundtruth.jsonl should contain translation[2] > 0.5";
  EXPECT_TRUE(foundNonZeroVz) << "groundtruth.jsonl should contain velocity[2] == 0.5";

  // detections.jsonl: check that it has translation arrays (detections recorded)
  const auto detections = readLines(directory / "detections.jsonl");
  ASSERT_GT(detections.size(), 0U);
  EXPECT_TRUE(detections.front().find("\"translation\":[") != std::string::npos);

  // estimator.jsonl: check config line has state_names with "z","vz" substring
  // and check that step lines have x array with 13 entries (StateSize)
  const auto estimator = readLines(directory / "estimator.jsonl");
  ASSERT_GT(estimator.size(), 0U);

  // First line is config and should contain "z","vz" substring
  EXPECT_TRUE(estimator.front().find("\"z\",\"vz\"") != std::string::npos)
    << "estimator config should have state_names containing z and vz in sequence";

  // Check state lines have x array with 13 entries (TrackedObject::StateSize)
  bool foundValidStateArray = false;
  for (size_t i = 1; i < estimator.size(); ++i)
  {
    if (estimator[i].find("\"type\":\"step\"") != std::string::npos)
    {
      auto xArray = numbersAfter(estimator[i], "x");
      if (xArray.size() == 13)
      {
        foundValidStateArray = true;
        break;
      }
    }
  }
  EXPECT_TRUE(foundValidStateArray) << "estimator.jsonl should have step entries with x array of 13 elements";

  // tracks.jsonl: find a late line (last line) with velocity[2] (vz) with |third| > 0.05
  const auto tracks = readLines(directory / "tracks.jsonl");
  ASSERT_GT(tracks.size(), 1U); // Should have at least init + one track update

  bool foundTrackWithVerticalVelocity = false;
  // Check from near the end (late in the run)
  for (int i = static_cast<int>(tracks.size()) - 1; i >= static_cast<int>(tracks.size()) - 5 && i >= 1; --i)
  {
    auto velocity = numbersAfter(tracks[i], "velocity");
    if (velocity.size() >= 3 && std::fabs(velocity[2]) > 0.05)
    {
      foundTrackWithVerticalVelocity = true;
      break;
    }
  }
  EXPECT_TRUE(foundTrackWithVerticalVelocity)
    << "tracks.jsonl should have late entries with velocity[2] (vz) with |third| > 0.05";
}
