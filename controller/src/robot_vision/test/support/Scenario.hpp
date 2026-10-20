// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <algorithm>
#include <cmath>
#include <numbers>
#include <random>
#include <utility>
#include <vector>

#include <rv/tracking/MultiModelKalmanEstimator.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "TestUtils.hpp"

namespace rv::tracking::test {

struct Box
{
  double length = 0.0;
  double width = 0.0;
  double height = 0.0;
};

inline constexpr Box kCar{.length = 4.5, .width = 1.8, .height = 1.5};
inline constexpr Box kPerson{.length = 0.5, .width = 0.5, .height = 1.7};

struct TruthSample
{
  double t = 0.0;
  double x = 0.0;
  double y = 0.0;
  double heading = 0.0;
  double speed = 0.0;
  double yawRate = 0.0;
  Box box;

  double vx() const
  {
    return speed * std::cos(heading);
  }
  double vy() const
  {
    return speed * std::sin(heading);
  }
};

inline TrackedObject makeDetection(const TruthSample &sample)
{
  return makeDetection(sample.x, sample.y, 0.0, sample.box.length, sample.box.width, sample.box.height);
}

// Unicycle ground truth: segments of constant acceleration and turn rate; speed never goes below 0.
class Trajectory
{
public:
  explicit Trajectory(TruthSample start)
    : mStart(start)
  {
  }

  Trajectory &straight(double seconds)
  {
    return addSegment(0.0, 0.0, seconds);
  }
  Trajectory &accelerate(double acceleration, double seconds)
  {
    return addSegment(acceleration, 0.0, seconds);
  }
  Trajectory &turn(double yawRate, double seconds)
  {
    return addSegment(0.0, yawRate, seconds);
  }

  // Segment durations are rounded to whole frames.
  std::vector<TruthSample> sample(double fps) const
  {
    constexpr int kSubSteps = 100;
    const double dt = 1.0 / (fps * kSubSteps);
    TruthSample state = mStart;
    std::vector<TruthSample> samples{state};
    int frame = 0;
    for (const auto &segment : mSegments)
    {
      const long frames = std::lround(segment.seconds * fps);
      for (long i = 0; i < frames; ++i)
      {
        for (int step = 0; step < kSubSteps; ++step)
        {
          const double midSpeed = std::max(state.speed + 0.5 * segment.acceleration * dt, 0.0);
          const double midHeading = state.heading + 0.5 * segment.yawRate * dt;
          state.x += midSpeed * std::cos(midHeading) * dt;
          state.y += midSpeed * std::sin(midHeading) * dt;
          state.speed = std::max(state.speed + segment.acceleration * dt, 0.0);
          state.heading += segment.yawRate * dt;
        }
        state.t = mStart.t + ++frame / fps;
        state.yawRate = segment.yawRate;
        samples.push_back(state);
      }
    }
    return samples;
  }

private:
  struct Segment
  {
    double acceleration;
    double yawRate;
    double seconds;
  };

  Trajectory &addSegment(double acceleration, double yawRate, double seconds)
  {
    mSegments.push_back({acceleration, yawRate, seconds});
    return *this;
  }

  TruthSample mStart;
  std::vector<Segment> mSegments;
};

// Samples with from <= t < to.
inline std::vector<TruthSample> between(const std::vector<TruthSample> &samples, double from, double to)
{
  constexpr double kEpsilon = 1e-9;
  std::vector<TruthSample> slice;
  for (const auto &sample : samples)
  {
    if (sample.t > from - kEpsilon && sample.t < to - kEpsilon)
    {
      slice.push_back(sample);
    }
  }
  return slice;
}

struct Sensor
{
  double positionNoise = 0.0; // standard deviation [m]
  double sizeNoise = 0.0;     // standard deviation of length, width and height [m]
  double yawNoise = 0.0;      // standard deviation [rad], orienting sensors only
  bool orienting = false;     // reports heading as yaw and sets has_orientation, like a LiDAR
  std::mt19937 rng{1};
};

struct Observation
{
  double t;
  TrackedObject detection;
};

inline std::vector<Observation> observe(const std::vector<TruthSample> &truth, Sensor &sensor)
{
  std::normal_distribution<double> noise(0.0, 1.0);
  std::vector<Observation> observations;
  for (const auto &sample : truth)
  {
    auto detection = makeDetection(sample);
    if (sensor.positionNoise > 0.0)
    {
      detection.x += sensor.positionNoise * noise(sensor.rng);
      detection.y += sensor.positionNoise * noise(sensor.rng);
    }
    if (sensor.sizeNoise > 0.0)
    {
      detection.length += sensor.sizeNoise * noise(sensor.rng);
      detection.width += sensor.sizeNoise * noise(sensor.rng);
      detection.height += sensor.sizeNoise * noise(sensor.rng);
    }
    if (sensor.orienting)
    {
      const double yawError = sensor.yawNoise > 0.0 ? sensor.yawNoise * noise(sensor.rng) : 0.0;
      detection.yaw = std::remainder(sample.heading + yawError, 2.0 * std::numbers::pi);
      orientation::setHasOrientation(detection, true);
    }
    observations.push_back({sample.t, std::move(detection)});
  }
  return observations;
}

// Drives one MultiModelKalmanEstimator the way TrackManager does, without association or lifecycle.
class FilterRun
{
public:
  explicit FilterRun(TrackManagerConfig config = productionConfig())
    : mConfig(std::move(config))
  {
  }

  // Initializes on the first observation, then predict + correct per observation. One state per observation.
  std::vector<TrackedObject> feed(const std::vector<Observation> &observations)
  {
    std::vector<TrackedObject> states;
    for (const auto &[t, detection] : observations)
    {
      if (mInitialized)
      {
        estimator.track(detection, atSeconds(t));
      }
      else
      {
        estimator.initialize(detection,
                             atSeconds(t),
                             mConfig.mDefaultProcessNoise,
                             mConfig.mDefaultMeasurementNoise,
                             mConfig.mInitStateCovariance,
                             mConfig.mMotionModels);
        mInitialized = true;
      }
      states.push_back(state());
    }
    return states;
  }

  void coast(double seconds)
  {
    estimator.predict(seconds);
  }

  TrackedObject state() const
  {
    return estimator.currentState();
  }

  MultiModelKalmanEstimator estimator;

private:
  TrackManagerConfig mConfig;
  bool mInitialized = false;
};

} // namespace rv::tracking::test
