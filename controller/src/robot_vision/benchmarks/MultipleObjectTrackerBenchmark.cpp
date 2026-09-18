// SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <benchmark/benchmark.h>

#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "rv/Utils.hpp"
#include "rv/tracking/MultipleObjectTracker.hpp"
#include "rv/tracking/ObjectMatching.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {
namespace benchmark {
namespace {

struct AssociationParams
{
  bool configured = false;
  DistanceType distance_type = DistanceType::Euclidean;
  double distance_threshold = 2.0;
  double max_radius_m = 2.0;
  std::string label = "default_track_path";
};

struct WorkloadConfig
{
  std::vector<int> people_counts{50};
  std::vector<int> camera_counts{1, 2};
  AssociationParams association;
};

WorkloadConfig g_workload;

std::optional<std::string> jsonStringField(const std::string &json, const std::string &key)
{
  const std::string pattern = "\"" + key + "\"";
  const auto key_pos = json.find(pattern);
  if (key_pos == std::string::npos)
  {
    return std::nullopt;
  }
  const auto colon = json.find(':', key_pos + pattern.size());
  if (colon == std::string::npos)
  {
    return std::nullopt;
  }
  const auto first_quote = json.find('"', colon + 1);
  if (first_quote == std::string::npos)
  {
    return std::nullopt;
  }
  const auto second_quote = json.find('"', first_quote + 1);
  if (second_quote == std::string::npos)
  {
    return std::nullopt;
  }
  return json.substr(first_quote + 1, second_quote - first_quote - 1);
}

std::optional<double> jsonNumberField(const std::string &json, const std::string &key)
{
  const std::string pattern = "\"" + key + "\"";
  const auto key_pos = json.find(pattern);
  if (key_pos == std::string::npos)
  {
    return std::nullopt;
  }
  const auto colon = json.find(':', key_pos + pattern.size());
  if (colon == std::string::npos)
  {
    return std::nullopt;
  }
  size_t i = colon + 1;
  while (i < json.size() && (json[i] == ' ' || json[i] == '\t' || json[i] == '\n' || json[i] == '\r'))
  {
    ++i;
  }
  size_t j = i;
  while (j < json.size() && (std::isdigit(static_cast<unsigned char>(json[j])) || json[j] == '.' || json[j] == '-' ||
                             json[j] == '+' || json[j] == 'e' || json[j] == 'E'))
  {
    ++j;
  }
  if (j == i)
  {
    return std::nullopt;
  }
  return std::stod(json.substr(i, j - i));
}

AssociationParams loadAssociationConfig(const std::string &path)
{
  std::ifstream in(path);
  if (!in)
  {
    throw std::runtime_error("Failed to open association config: " + path);
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  const std::string json = ss.str();

  AssociationParams params;
  params.configured = true;

  const auto method = jsonStringField(json, "method").value_or("euclidean");
  const double gate_probability = jsonNumberField(json, "gate_probability").value_or(0.99);
  params.max_radius_m = jsonNumberField(json, "max_radius_m").value_or(2.0);

  if (method == "euclidean")
  {
    params.distance_type = DistanceType::Euclidean;
    params.distance_threshold = params.max_radius_m;
    params.label = "euclidean_r" + std::to_string(params.max_radius_m);
  }
  else if (method == "position_mahalanobis")
  {
#ifndef RV_HAS_POSITION_MAHALANOBIS
    throw std::runtime_error(
      "association method position_mahalanobis is not available in this robot_vision build");
#else
    params.distance_type = DistanceType::PositionMahalanobis;
    params.distance_threshold = rv::chi2Threshold(gate_probability, 2);
    params.label = "position_mahalanobis_p" + std::to_string(gate_probability) + "_r" +
                   std::to_string(params.max_radius_m);
#endif
  }
  else
  {
    throw std::runtime_error("Unsupported association method: " + method);
  }
  return params;
}

class PeopleTrackingBenchmarkFixture
{
public:
  PeopleTrackingBenchmarkFixture() : gen(42), pos_dist(-25.0, 25.0), walking_speed_dist(0.5, 2.0)
  {
    baseTimestamp = std::chrono::system_clock::now();
  }

  TrackedObject generateRandomPerson(Id personId = InvalidObjectId)
  {
    TrackedObject person;
    person.id = personId;
    person.x = pos_dist(gen);
    person.y = pos_dist(gen);
    person.z = 0.0;

    person.width = 0.4 + std::abs(pos_dist(gen)) / 150.0;
    person.height = 1.6 + std::abs(pos_dist(gen)) / 100.0;
    person.length = 0.3 + std::abs(pos_dist(gen)) / 200.0;

    double speed = walking_speed_dist(gen);
    double direction = std::uniform_real_distribution<double>(0, 2 * M_PI)(gen);
    person.vx = speed * std::cos(direction);
    person.vy = speed * std::sin(direction);

    person.yaw = direction;
    person.previousYaw = direction;

    person.classification = Eigen::VectorXd::Zero(5);
    person.classification[0] = 0.8 + 0.15 * std::uniform_real_distribution<double>(0, 1)(gen);
    person.classification[1] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);
    person.classification[2] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);
    person.classification[3] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);
    person.classification[4] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);
    person.classification.normalize();

    person.predictedMeasurementMean = cv::Mat::zeros(7, 1, CV_64F);
    person.predictedMeasurementMean.at<double>(0, 0) = person.x;
    person.predictedMeasurementMean.at<double>(1, 0) = person.y;
    person.predictedMeasurementMean.at<double>(2, 0) = person.width;
    person.predictedMeasurementMean.at<double>(3, 0) = person.height;
    person.predictedMeasurementMean.at<double>(4, 0) = person.vx;
    person.predictedMeasurementMean.at<double>(5, 0) = person.vy;
    person.predictedMeasurementMean.at<double>(6, 0) = person.yaw;

    person.predictedMeasurementCov = cv::Mat::eye(7, 7, CV_64F) * 0.2;
    cv::invert(person.predictedMeasurementCov, person.predictedMeasurementCovInv);
    person.errorCovariance = cv::Mat::eye(7, 7, CV_64F) * 0.1;
    return person;
  }

  std::vector<TrackedObject> generateMovingPeopleScenario(size_t numPeople, double deltaTime = 0.0)
  {
    std::vector<TrackedObject> people;
    people.reserve(numPeople);
    for (size_t i = 0; i < numPeople; ++i)
    {
      auto person = generateRandomPerson(static_cast<Id>(i + 1));
      if (deltaTime > 0.0)
      {
        person.x += person.vx * deltaTime;
        person.y += person.vy * deltaTime;
        double direction_change = std::normal_distribution<double>(0.0, 0.1)(gen);
        person.yaw += direction_change;
        const double speed = std::sqrt(person.vx * person.vx + person.vy * person.vy);
        person.vx = speed * std::cos(person.yaw);
        person.vy = speed * std::sin(person.yaw);
        person.predictedMeasurementMean.at<double>(0, 0) = person.x;
        person.predictedMeasurementMean.at<double>(1, 0) = person.y;
        person.predictedMeasurementMean.at<double>(4, 0) = person.vx;
        person.predictedMeasurementMean.at<double>(5, 0) = person.vy;
        person.predictedMeasurementMean.at<double>(6, 0) = person.yaw;
      }
      people.push_back(std::move(person));
    }
    return people;
  }

  std::vector<std::vector<TrackedObject>> splitAcrossCameras(std::vector<TrackedObject> people,
                                                             int numCameras)
  {
    std::vector<std::vector<TrackedObject>> per_camera(static_cast<size_t>(std::max(1, numCameras)));
    if (numCameras <= 1)
    {
      per_camera[0] = std::move(people);
      return per_camera;
    }
    for (size_t i = 0; i < people.size(); ++i)
    {
      per_camera[i % static_cast<size_t>(numCameras)].push_back(std::move(people[i]));
    }
    return per_camera;
  }

  std::unique_ptr<MultipleObjectTracker> createPeopleTracker()
  {
    return std::make_unique<MultipleObjectTracker>();
  }

  std::chrono::system_clock::time_point getTimestamp(int frameNumber = 0)
  {
    return baseTimestamp + std::chrono::milliseconds(frameNumber * 33);
  }

private:
  std::mt19937 gen;
  std::uniform_real_distribution<double> pos_dist;
  std::uniform_real_distribution<double> walking_speed_dist;
  std::chrono::system_clock::time_point baseTimestamp;
};

void callTrack(MultipleObjectTracker &tracker,
               std::vector<std::vector<TrackedObject>> objectsPerCamera,
               const std::chrono::system_clock::time_point &timestamp,
               const AssociationParams &association)
{
  constexpr double kScoreThreshold = 0.7;
  if (!association.configured)
  {
    tracker.track(std::move(objectsPerCamera), timestamp, kScoreThreshold);
    return;
  }
#ifdef RV_HAS_ASSOCIATION_MAX_RADIUS
  tracker.track(std::move(objectsPerCamera), timestamp, association.distance_type,
                association.distance_threshold, kScoreThreshold, association.max_radius_m);
#else
  tracker.track(std::move(objectsPerCamera), timestamp, association.distance_type,
                association.distance_threshold, kScoreThreshold);
#endif
}

static void BM_Track(::benchmark::State &state)
{
  const int numPeople = static_cast<int>(state.range(0));
  const int numCameras = static_cast<int>(state.range(1));
  PeopleTrackingBenchmarkFixture fixture;
  auto tracker = fixture.createPeopleTracker();
  const double frameTime = 0.033;
  int frameCount = 0;
  auto timestamp = fixture.getTimestamp();

  for (auto _ : state)
  {
    auto people = fixture.generateMovingPeopleScenario(static_cast<size_t>(numPeople),
                                                       frameCount * frameTime);
    auto per_camera = fixture.splitAcrossCameras(std::move(people), numCameras);
    callTrack(*tracker, std::move(per_camera), timestamp, g_workload.association);

    frameCount++;
    timestamp = fixture.getTimestamp(frameCount);
    if (frameCount >= 100)
    {
      frameCount = 0;
      tracker = fixture.createPeopleTracker();
    }
  }

  // iterations / total_seconds => 1 / mean_seconds_per_track => peak FPS.
  state.counters["peak_fps"] =
    ::benchmark::Counter(static_cast<double>(state.iterations()), ::benchmark::Counter::kIsRate);
  state.SetItemsProcessed(state.iterations() * numPeople);
  state.SetLabel(g_workload.association.label + " people=" + std::to_string(numPeople) +
                 " cameras=" + std::to_string(numCameras));
}

void registerBenchmarks()
{
  for (int people : g_workload.people_counts)
  {
    for (int cameras : g_workload.camera_counts)
    {
      ::benchmark::RegisterBenchmark("BM_Track", BM_Track)
        ->Args({people, cameras})
        ->Unit(::benchmark::kMillisecond)
        ->UseRealTime();
    }
  }
}

void printUsage(const char *argv0)
{
  std::cerr
    << "Usage: " << argv0
    << " [--people N[,N...]] [--cameras N[,N...]] [--association-config path.json] "
       "[google-benchmark flags...]\n"
    << "  peak_fps counter = 1 / mean seconds per track() call (real time).\n";
}

std::vector<int> parseIntList(const std::string &value)
{
  std::vector<int> out;
  std::stringstream ss(value);
  std::string item;
  while (std::getline(ss, item, ','))
  {
    if (!item.empty())
    {
      out.push_back(std::stoi(item));
    }
  }
  if (out.empty())
  {
    throw std::runtime_error("Expected at least one integer in list: " + value);
  }
  return out;
}

bool parseWorkloadArgs(int &argc, char **argv)
{
  std::vector<char *> kept;
  kept.push_back(argv[0]);
  for (int i = 1; i < argc; ++i)
  {
    const std::string arg = argv[i];
    auto requireValue = [&](const char *name) -> std::string {
      if (i + 1 >= argc)
      {
        throw std::runtime_error(std::string(name) + " requires a value");
      }
      return argv[++i];
    };
    if (arg == "--help" || arg == "-h")
    {
      printUsage(argv[0]);
      return false;
    }
    if (arg == "--people")
    {
      g_workload.people_counts = parseIntList(requireValue("--people"));
    }
    else if (arg == "--cameras")
    {
      g_workload.camera_counts = parseIntList(requireValue("--cameras"));
    }
    else if (arg == "--association-config")
    {
      g_workload.association = loadAssociationConfig(requireValue("--association-config"));
    }
    else
    {
      kept.push_back(argv[i]);
    }
  }
  argc = static_cast<int>(kept.size());
  for (int i = 0; i < argc; ++i)
  {
    argv[i] = kept[static_cast<size_t>(i)];
  }
  argv[argc] = nullptr;
  return true;
}

} // namespace
} // namespace benchmark
} // namespace tracking
} // namespace rv

int main(int argc, char **argv)
{
  try
  {
    if (!rv::tracking::benchmark::parseWorkloadArgs(argc, argv))
    {
      return 0;
    }
  }
  catch (const std::exception &ex)
  {
    std::cerr << "Error: " << ex.what() << "\n";
    rv::tracking::benchmark::printUsage(argv[0]);
    return 1;
  }

  rv::tracking::benchmark::registerBenchmarks();
  ::benchmark::Initialize(&argc, argv);
  if (::benchmark::ReportUnrecognizedArguments(argc, argv))
  {
    return 1;
  }
  ::benchmark::RunSpecifiedBenchmarks();
  ::benchmark::Shutdown();
  return 0;
}
