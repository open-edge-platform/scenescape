// SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <benchmark/benchmark.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "rv/tracking/MultipleObjectTracker.hpp"
#include "rv/tracking/ObjectMatching.hpp"
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

struct WorkloadConfig
{
  std::vector<int> people_counts{50};
  std::vector<int> camera_counts{1, 2};
  std::vector<int> overlap_modes{0, 1};
  // Euclidean radius used by Scene Controller (DEFAULT_TRACKING_RADIUS) and Tracker Service.
  double distance_threshold = 2.0;
};

WorkloadConfig g_workload;

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
    // No Kalman matrices: like Scene Controller detections, and copies would alias the tracker's buffers.
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

// immediate=false: one batched track() per frame (time-chunking, Tracker Service).
// immediate=true: one track() per camera message (Scene Controller Immediate mode).
void runTrack(::benchmark::State &state, bool immediate)
{
  const int numPeople = static_cast<int>(state.range(0));
  const int numCameras = static_cast<int>(state.range(1));
  const bool overlap = state.range(2) != 0;
  PeopleTrackingBenchmarkFixture fixture;
  fixture.resetPeople(static_cast<size_t>(numPeople));
  auto tracker = std::make_unique<MultipleObjectTracker>();
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
        tracker->track(std::move(perCamera[static_cast<size_t>(camera)]),
                       timestamp + offset,
                       DistanceType::Euclidean,
                       g_workload.distance_threshold,
                       kScoreThreshold);
      }
    }
    else
    {
      tracker->track(
        std::move(perCamera), timestamp, DistanceType::Euclidean, g_workload.distance_threshold, kScoreThreshold);
    }

    fixture.advancePeople(kFrameTimeS);
    if (++frameCount >= kFramesPerTrackerReset)
    {
      frameCount = 0;
      fixture.resetPeople(static_cast<size_t>(numPeople));
      tracker = std::make_unique<MultipleObjectTracker>();
    }
  }

  // iterations / total_seconds => scene frames (all cameras) per second => peak FPS.
  state.counters["peak_fps"]
    = ::benchmark::Counter(static_cast<double>(state.iterations()), ::benchmark::Counter::kIsRate);
  state.SetItemsProcessed(detections);
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
  std::cerr << "Usage: " << argv0
            << " [--people N[,N...]] [--cameras N[,N...]] [--overlap 0|1[,...]] [--distance-threshold M] "
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
    else if (arg == "--distance-threshold")
    {
      g_workload.distance_threshold = std::stod(requireValue("--distance-threshold"));
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
