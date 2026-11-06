// SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <benchmark/benchmark.h>
#include <opencv2/core/persistence.hpp>

#include <chrono>
#include <cmath>
#include <cstdlib>
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
#include "rv/tracking/TrackManager.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {
namespace benchmark {
namespace {

constexpr double kScoreThreshold = 0.7;
constexpr double kFrameTimeS = 0.033;
constexpr int kFramesPerTrackerReset = 100;
// Per-camera ground-plane projection disagreement in the overlap layout.
constexpr double kCameraNoiseStdM = 0.1;

// Filter and track lifecycle settings of the Scene Controller and Tracker Service default configs.
TrackManagerConfig productionTrackerConfig()
{
  TrackManagerConfig config;
  config.mDefaultProcessNoise = kProductionProcessNoise;
  config.mDefaultMeasurementNoise = kProductionMeasurementNoise;
  config.mInitStateCovariance = kProductionInitStateCovariance;
  config.mMotionModels = kProductionMotionModels;
  config.mMaxUnreliableTime = 1.0;
  config.mNonMeasurementTimeDynamic = 0.8;
  config.mNonMeasurementTimeStatic = 1.6;
  return config;
}

// Lifecycle times are converted to frames at the benchmark's frame rate, as the services do at theirs.
std::unique_ptr<MultipleObjectTracker> makeTracker()
{
  auto tracker = std::make_unique<MultipleObjectTracker>(productionTrackerConfig());
  tracker->updateTrackerParams(static_cast<int>(std::lround(1.0 / kFrameTimeS)));
  return tracker;
}

struct AssociationParams
{
  DistanceType distance_type = DistanceType::PositionMahalanobis;
  double distance_threshold = 0.0;
  double max_radius_m = 0.0;
  std::string label;
};

struct WorkloadConfig
{
  std::vector<int> people_counts{50};
  std::vector<int> camera_counts{1, 2};
  std::vector<int> overlap_modes{0, 1};
  // Set by parseWorkloadArgs: --association-config, or position_mahalanobis (the services' default without a config).
  std::optional<AssociationParams> association;
};

WorkloadConfig g_workload;

// Association parameters as the Scene Controller and the Tracker Service derive them from their association config,
// with the same defaults: method position_mahalanobis, gate_probability 0.99, max_radius_m 2 m for euclidean and
// 10 m for position_mahalanobis.
AssociationParams makeAssociationParams(const std::string &method,
                                        std::optional<double> gate_probability,
                                        std::optional<double> max_radius_m)
{
  AssociationParams params;
  if (method == "euclidean")
  {
    params.distance_type = DistanceType::Euclidean;
    params.max_radius_m = max_radius_m.value_or(2.0);
    params.distance_threshold = params.max_radius_m;
    params.label = "euclidean_r" + std::to_string(params.max_radius_m);
  }
  else if (method == "position_mahalanobis")
  {
    const double probability = gate_probability.value_or(0.99);
    params.distance_type = DistanceType::PositionMahalanobis;
    params.max_radius_m = max_radius_m.value_or(10.0);
    params.distance_threshold = rv::chi2Threshold(probability, 2);
    params.label = "position_mahalanobis_p" + std::to_string(probability) + "_r" +
                   std::to_string(params.max_radius_m);
  }
  else
  {
    throw std::runtime_error("Unsupported association method: " + method);
  }
  return params;
}

// A JSON object with top-level "method" (string), "gate_probability" and "max_radius_m" (numbers); a missing key gets
// the service default, other keys are ignored. OpenCV's JSON reader does not accept null.
AssociationParams loadAssociationConfig(const std::string &path)
{
  cv::FileStorage config;
  try
  {
    config.open(path, cv::FileStorage::READ | cv::FileStorage::FORMAT_JSON);
  }
  catch (const cv::Exception &error)
  {
    throw std::runtime_error("Invalid association config " + path + ": " + error.what());
  }
  if (!config.isOpened())
  {
    throw std::runtime_error("Failed to open association config: " + path);
  }
  if (!config.root().isMap())
  {
    throw std::runtime_error("Association config must be a JSON object: " + path);
  }
  const auto present = [&](const char *key) -> std::optional<cv::FileNode> {
    const cv::FileNode node = config[key];
    if (node.empty())
    {
      return std::nullopt;
    }
    return node;
  };
  const auto wrongType = [&](const char *key) {
    return std::runtime_error("Association config " + std::string(key) + " has the wrong type: " + path);
  };
  const auto number = [&](const char *key) -> std::optional<double> {
    const auto node = present(key);
    if (!node)
    {
      return std::nullopt;
    }
    if (!node->isReal() && !node->isInt())
    {
      throw wrongType(key);
    }
    return node->real();
  };

  std::string method = "position_mahalanobis";
  if (const auto node = present("method"))
  {
    if (!node->isString())
    {
      throw wrongType("method");
    }
    method = node->string();
  }
  return makeAssociationParams(method, number("gate_probability"), number("max_radius_m"));
}

class PeopleTrackingBenchmarkFixture
{
public:
  PeopleTrackingBenchmarkFixture()
    : gen(42)
    , pos_dist(-25.0, 25.0)
    , walking_speed_dist(0.5, 2.0)
    , heading_noise(0.0, 0.1)
    , camera_noise(0.0, kCameraNoiseStdM)
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
    // No Kalman matrices, like Scene Controller and Tracker Service detections.
    return person;
  }

  void resetPeople(size_t numPeople)
  {
    people.clear();
    people.reserve(numPeople);
    for (size_t i = 0; i < numPeople; ++i)
    {
      people.push_back(generateRandomPerson(static_cast<Id>(i + 1)));
    }
  }

  void advancePeople(double deltaTime)
  {
    for (auto &person : people)
    {
      person.x += person.vx * deltaTime;
      person.y += person.vy * deltaTime;
      person.yaw += heading_noise(gen);
      const double speed = std::hypot(person.vx, person.vy);
      person.vx = speed * std::cos(person.yaw);
      person.vy = speed * std::sin(person.yaw);
    }
  }

  // split: each person seen by one camera (round-robin); overlap: every camera sees every person.
  std::vector<std::vector<TrackedObject>> cameraViews(int numCameras, bool overlap)
  {
    const size_t cameras = static_cast<size_t>(std::max(1, numCameras));
    while (cameraIds.size() < cameras)
    {
      cameraIds.push_back("camera_" + std::to_string(cameraIds.size()));
    }
    std::vector<std::vector<TrackedObject>> perCamera(cameras);
    for (size_t i = 0; i < people.size(); ++i)
    {
      for (size_t camera = 0; camera < cameras; ++camera)
      {
        if (!overlap && i % cameras != camera)
        {
          continue;
        }
        auto detection = people[i];
        detection.attributes["camera_id"] = cameraIds[camera];
        if (overlap && cameras > 1)
        {
          detection.x += camera_noise(gen);
          detection.y += camera_noise(gen);
        }
        perCamera[camera].push_back(std::move(detection));
      }
    }
    return perCamera;
  }

  std::chrono::system_clock::time_point getTimestamp(int frameNumber = 0)
  {
    return baseTimestamp + std::chrono::milliseconds(frameNumber * 33);
  }

private:
  std::mt19937 gen;
  std::uniform_real_distribution<double> pos_dist;
  std::uniform_real_distribution<double> walking_speed_dist;
  std::normal_distribution<double> heading_noise;
  std::normal_distribution<double> camera_noise;
  std::chrono::system_clock::time_point baseTimestamp;
  std::vector<TrackedObject> people;
  std::vector<std::string> cameraIds;
};

// Objects is either one camera's detections or the per-camera batch; both overloads share this signature.
template <typename Objects>
void callTrack(MultipleObjectTracker &tracker,
               Objects objects,
               const std::chrono::system_clock::time_point &timestamp,
               const AssociationParams &association)
{
  tracker.track(std::move(objects), timestamp, association.distance_type,
                association.distance_threshold, kScoreThreshold, association.max_radius_m);
}

// immediate=false: one batched track() per frame (time-chunking, Tracker Service).
// immediate=true: one track() per camera message (Scene Controller Immediate mode).
void runTrack(::benchmark::State &state, bool immediate)
{
  const int numPeople = static_cast<int>(state.range(0));
  const int numCameras = static_cast<int>(state.range(1));
  const bool overlap = state.range(2) != 0;
  PeopleTrackingBenchmarkFixture fixture;
  fixture.resetPeople(static_cast<size_t>(numPeople));
  auto tracker = makeTracker();
  int frameCount = 0;
  int64_t detections = 0;

  for (auto _ : state)
  {
    auto perCamera = fixture.cameraViews(numCameras, overlap);
    const auto timestamp = fixture.getTimestamp(frameCount);
    for (const auto &cameraObjects : perCamera)
    {
      detections += static_cast<int64_t>(cameraObjects.size());
    }

    if (immediate)
    {
      const int cameras = static_cast<int>(perCamera.size());
      for (int camera = 0; camera < cameras; ++camera)
      {
        // Cameras publish staggered within the frame period.
        const auto offset = std::chrono::milliseconds(33 * camera / cameras);
        callTrack(*tracker, std::move(perCamera[static_cast<size_t>(camera)]), timestamp + offset,
                  *g_workload.association);
      }
    }
    else
    {
      callTrack(*tracker, std::move(perCamera), timestamp, *g_workload.association);
    }

    fixture.advancePeople(kFrameTimeS);
    if (++frameCount >= kFramesPerTrackerReset)
    {
      frameCount = 0;
      fixture.resetPeople(static_cast<size_t>(numPeople));
      tracker = makeTracker();
    }
  }

  // iterations / total_seconds => scene frames (all cameras) per second => peak FPS.
  state.counters["peak_fps"] =
    ::benchmark::Counter(static_cast<double>(state.iterations()), ::benchmark::Counter::kIsRate);
  state.SetItemsProcessed(detections);
  state.SetLabel(g_workload.association->label);
}

void registerBenchmarks()
{
  for (const bool immediate : {false, true})
  {
    for (int people : g_workload.people_counts)
    {
      for (int cameras : g_workload.camera_counts)
      {
        for (int overlap : g_workload.overlap_modes)
        {
          if (cameras <= 1 && overlap != 0)
          {
            continue;
          }
          ::benchmark::RegisterBenchmark(immediate ? "BM_Immediate" : "BM_TimeChunking",
                                         [immediate](::benchmark::State &state) { runTrack(state, immediate); })
            ->Args({people, cameras, overlap})
            ->ArgNames({"people", "cameras", "overlap"})
            ->Unit(::benchmark::kMillisecond)
            ->UseRealTime();
        }
      }
    }
  }
}

void printUsage(const char *argv0)
{
  std::cerr
    << "Usage: " << argv0
    << " [--people N[,N...]] [--cameras N[,N...]] [--overlap 0|1[,...]] [--association-config path.json] "
       "[google-benchmark flags...]\n"
    << "  BM_TimeChunking: one batched track() per frame; BM_Immediate: one track() per camera.\n"
    << "  peak_fps counter = scene frames (all cameras) per second (real time).\n";
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
    else if (arg == "--overlap")
    {
      g_workload.overlap_modes = parseIntList(requireValue("--overlap"));
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
  if (!g_workload.association)
  {
    g_workload.association = makeAssociationParams("position_mahalanobis", std::nullopt, std::nullopt);
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
