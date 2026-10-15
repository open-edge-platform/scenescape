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
  Sensor lidar{.positionNoise = 0.05, .orienting = true};
  {
    ScenarioRecorder recorder("case one", mRoot);
    recorder.truth(truth);
    FilterRun run(productionConfig(), &recorder);
    run.feed(recorder.detections(observe(truth, lidar), "lidar"));
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

TEST_F(ScenarioRecorderTest, WithoutDirectoryRecordsNothing)
{
  const auto truth = Trajectory({.speed = 1.0, .box = kPerson}).straight(0.5).sample(10.0);
  Sensor camera;
  ScenarioRecorder recorder("off", std::filesystem::path());
  EXPECT_FALSE(recorder.enabled());
  recorder.truth(truth);
  const auto observations = recorder.detections(observe(truth, camera), "camera");
  FilterRun run(productionConfig(), &recorder);
  run.feed(observations);
  recorder.write();

  EXPECT_EQ(observations.front().detection.attributes.at("camera_id"), "camera");
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
