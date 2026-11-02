// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <functional>
#include <numbers>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <opencv2/core.hpp>

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
  std::string_view category;
};

inline constexpr Box kCar{.length = 4.5, .width = 1.8, .height = 1.5, .category = "vehicle"};
inline constexpr Box kPerson{.length = 0.5, .width = 0.5, .height = 1.7, .category = "person"};

struct TruthSample
{
  double t = 0.0;
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double heading = 0.0;
  double speed = 0.0;
  double yawRate = 0.0;
  double acceleration = 0.0;
  double vz = 0.0;
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
  return makeDetection(sample.x, sample.y, sample.z, sample.box.length, sample.box.width, sample.box.height);
}

// Unicycle ground truth: segments of constant acceleration, turn rate, and vertical rate; speed never goes below 0, vz
// unrestricted.
class Trajectory
{
public:
  explicit Trajectory(TruthSample start)
    : mStart(start)
  {
  }

  Trajectory &straight(double seconds)
  {
    return segment(0.0, 0.0, 0.0, seconds);
  }
  Trajectory &accelerate(double acceleration, double seconds)
  {
    return segment(acceleration, 0.0, 0.0, seconds);
  }
  Trajectory &turn(double yawRate, double seconds)
  {
    return segment(0.0, yawRate, 0.0, seconds);
  }

  Trajectory &segment(double acceleration, double yawRate, double vz, double seconds)
  {
    return addSegment(acceleration, yawRate, vz, seconds);
  }

  Trajectory &climb(double vz, double seconds)
  {
    return segment(0.0, 0.0, vz, seconds);
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
          state.z += segment.vz * dt;
          state.speed = std::max(state.speed + segment.acceleration * dt, 0.0);
          state.heading += segment.yawRate * dt;
        }
        state.t = mStart.t + ++frame / fps;
        state.yawRate = segment.yawRate;
        state.vz = segment.vz;
        // Braking ends once the object stands still.
        state.acceleration = (state.speed > 0.0 || segment.acceleration > 0.0) ? segment.acceleration : 0.0;
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
    double vz;
    double seconds;
  };

  Trajectory &addSegment(double acceleration, double yawRate, double vz, double seconds)
  {
    mSegments.push_back({acceleration, yawRate, vz, seconds});
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

// The samples with a constant height and no vertical motion.
inline std::vector<TruthSample> atHeight(std::vector<TruthSample> samples, double z)
{
  for (auto &sample : samples)
  {
    sample.z = z;
    sample.vz = 0.0;
  }
  return samples;
}

// Vertical motion as segments of constant rate, to lay over any planar truth (see apply()).
class VerticalProfile
{
public:
  explicit VerticalProfile(double startHeight = 0.0)
    : mStartHeight(startHeight)
  {
  }

  VerticalProfile &climb(double vz, double seconds)
  {
    mSegments.push_back({vz, seconds});
    return *this;
  }

  VerticalProfile &level(double seconds)
  {
    return climb(0.0, seconds);
  }

  // Stays at the final height after the last segment.
  double heightAt(double seconds) const
  {
    double height = mStartHeight;
    double remaining = std::max(seconds, 0.0);
    for (const auto &segment : mSegments)
    {
      const double used = std::min(remaining, segment.seconds);
      height += segment.vz * used;
      remaining -= used;
    }
    return height;
  }

  // 0 after the last segment. On a boundary between two segments the later one counts.
  double rateAt(double seconds) const
  {
    double start = 0.0;
    const double time = std::max(seconds, 0.0);
    for (const auto &segment : mSegments)
    {
      if (time < start + segment.seconds)
      {
        return segment.vz;
      }
      start += segment.seconds;
    }
    return 0.0;
  }

  // Replaces z and vz of every sample, with times counted from the first one. Like Trajectory::sample(), sample 0 has
  // vz = 0 and a later sample carries the rate of the frame that ended there: the rate at the middle of that frame, so
  // a segment boundary inside a frame gives the frame the rate of the segment that holds its middle.
  std::vector<TruthSample> apply(std::vector<TruthSample> samples) const
  {
    for (size_t i = 0; i < samples.size(); ++i)
    {
      const double t = samples[i].t - samples.front().t;
      samples[i].z = heightAt(t);
      samples[i].vz = i == 0 ? 0.0 : rateAt(0.5 * ((samples[i - 1].t - samples.front().t) + t));
    }
    return samples;
  }

private:
  struct Segment
  {
    double vz;
    double seconds;
  };

  double mStartHeight;
  std::vector<Segment> mSegments;
};

// Horizontal distance between an estimate and the truth [m].
inline double positionError(const TrackedObject &state, const TruthSample &sample)
{
  return std::hypot(state.x - sample.x, state.y - sample.y);
}

// Vertical distance between an estimate and the truth [m].
inline double verticalError(const TrackedObject &state, const TruthSample &sample)
{
  return std::abs(state.z - sample.z);
}

// Position error of each state against its truth sample (states as returned by FilterRun::feed), for t >= from.
inline std::vector<double>
positionErrors(const std::vector<TruthSample> &truth, const std::vector<TrackedObject> &states, double from = 0.0)
{
  constexpr double kEpsilon = 1e-9;
  std::vector<double> errors;
  for (size_t i = 0; i < truth.size(); ++i)
  {
    if (truth[i].t > from - kEpsilon)
    {
      errors.push_back(positionError(states.at(i), truth[i]));
    }
  }
  return errors;
}

// Vertical error of each state against its truth sample (states as returned by FilterRun::feed), for t >= from.
inline std::vector<double>
verticalErrors(const std::vector<TruthSample> &truth, const std::vector<TrackedObject> &states, double from = 0.0)
{
  constexpr double kEpsilon = 1e-9;
  std::vector<double> errors;
  for (size_t i = 0; i < truth.size(); ++i)
  {
    if (truth[i].t > from - kEpsilon)
    {
      errors.push_back(verticalError(states.at(i), truth[i]));
    }
  }
  return errors;
}

inline double rms(const std::vector<double> &values)
{
  double sumSquares = 0.0;
  for (double value : values)
  {
    sumSquares += value * value;
  }
  return std::sqrt(sumSquares / static_cast<double>(values.size()));
}

// The true covariance of a sensor's position error, and the per-detection R the sensor reports with it.
struct PositionCovariance
{
  // Covariance of the position error [m^2] in world axes for a detection of `sample`. Built from the truth sample: a
  // production producer computes R from the noisy detection, which differs noticeably only close to the sensor.
  std::function<cv::Matx33d(const TruthSample &)> covariance;
  double reportedScale = 1.0; // position block of the reported R = reportedScale * covariance; != 1: wrong confidence
  bool reported = true;       // false: the same noise, but detections carry no R, so the tracker uses its default R
  bool zMeasured = false;     // sets TrackedObject::zMeasured, e.g. for a sensor that measures depth
  // Reported variance of every axis the sensor does not model (zero variance); keep it the tracker's
  // mDefaultMeasurementNoise, which also applies to detections without R.
  double defaultNoise = kProductionMeasurementNoise;
};

// The same covariance for every detection, e.g. anisotropic or correlated noise for filter-level tests.
inline PositionCovariance fixedCovariance(const cv::Matx33d &covariance)
{
  return {.covariance = [covariance](const TruthSample &) { return covariance; }};
}

// A camera at `position` (x, y and its height) that projects the object's ground point onto the ground plane, like the
// pixel-to-world Jacobian of the Tracker Service: an angular error of `angularSigma` [rad] gives
// angularSigma * (h^2 + d^2) / h along the ground range d and angularSigma * sqrt(h^2 + d^2) across it, h being the
// camera height above the object. Planar detections: z is exact.
inline PositionCovariance groundPlaneCamera(const cv::Vec3d &position, double angularSigma)
{
  return {.covariance = [position, angularSigma](const TruthSample &sample) {
    const double height = position[2] - sample.z;
    if (!(height > 0.0))
    {
      throw std::invalid_argument("groundPlaneCamera must be above the object");
    }
    const double dx = sample.x - position[0];
    const double dy = sample.y - position[1];
    const double range = std::hypot(dx, dy);
    const double slantSquared = height * height + range * range;
    const double alongSigma = angularSigma * slantSquared / height;
    const double acrossSigma = angularSigma * std::sqrt(slantSquared);
    // Below the camera both sigmas are equal, so any bearing will do.
    const cv::Vec2d bearing = range > 0.0 ? cv::Vec2d(dx / range, dy / range) : cv::Vec2d(1.0, 0.0);
    const cv::Matx22d along = bearing * bearing.t();
    const cv::Matx22d horizontal
      = alongSigma * alongSigma * along + acrossSigma * acrossSigma * (cv::Matx22d::eye() - along);
    return cv::Matx33d(horizontal(0, 0), horizontal(0, 1), 0.0, horizontal(1, 0), horizontal(1, 1), 0.0, 0.0, 0.0, 0.0);
  }};
}

// A camera at `position` that also estimates depth, like the frustum covariance of the Controller's observation
// pipeline: angularSigma * range across the viewing ray in both directions and depthFraction * range along it.
// Detections have measured z.
inline PositionCovariance depthCamera(const cv::Vec3d &position, double angularSigma, double depthFraction)
{
  return {.covariance =
            [position, angularSigma, depthFraction](const TruthSample &sample) {
              const cv::Vec3d ray = cv::Vec3d(sample.x, sample.y, sample.z) - position;
              const double range = cv::norm(ray);
              if (!(range > 0.0))
              {
                throw std::invalid_argument("depthCamera must not be at the object");
              }
              const cv::Vec3d direction = ray / range;
              const cv::Matx33d along = direction * direction.t();
              const double alongSigma = depthFraction * range;
              const double acrossSigma = angularSigma * range;
              return alongSigma * alongSigma * along + acrossSigma * acrossSigma * (cv::Matx33d::eye() - along);
            },
          .zMeasured = true};
}

struct Sensor
{
  std::string id = "camera";  // sensor id of its observations, e.g. "lidar"
  double positionNoise = 0.0; // standard deviation [m]
  double sizeNoise = 0.0;     // standard deviation of length, width and height [m]
  double yawNoise = 0.0;      // standard deviation [rad], orienting sensors only
  bool orienting = false;     // reports heading as yaw and sets has_orientation, like a LiDAR
  std::mt19937 rng{1};
  double zNoise = 0.0;  // standard deviation of z [m]; 0 keeps z exact
  std::mt19937 zRng{2}; // own generator so z noise never changes the x/y/size/yaw noise
  // Position noise drawn from a covariance, reported as the detection's R; replaces positionNoise and zNoise.
  std::optional<PositionCovariance> positionCovariance;
  std::mt19937 covarianceRng{3}; // own generator: the size and yaw noise match a sensor without positionCovariance
};

// Lets a test repeat a scenario with different noise; seed 1 reproduces the defaults.
inline Sensor seeded(Sensor sensor, unsigned seed)
{
  sensor.rng.seed(seed);
  sensor.zRng.seed(seed + 1);
  sensor.covarianceRng.seed(seed + 2);
  return sensor;
}

struct Observation
{
  double t;
  TrackedObject detection;
  std::string sensorId;
  int objectId = 1; // ground-truth object the detection comes from
  // Covariance the position error was drawn from (Sensor::positionCovariance); the R the tracker sees, which may
  // differ from it, is detection.measurementNoiseCov.
  std::optional<cv::Matx33d> trueCovariance = std::nullopt;
};

// Position error with the given covariance from three standard normal draws.
inline cv::Vec3d correlatedNoise(const cv::Matx33d &covariance, std::mt19937 &rng)
{
  if (!cv::checkRange(covariance))
  {
    throw std::invalid_argument("position covariance must be finite");
  }
  cv::Mat eigenvalues;
  cv::Mat eigenvectors;
  cv::eigen(0.5 * (covariance + covariance.t()), eigenvalues, eigenvectors);
  double minEigenvalue = 0.0;
  double maxEigenvalue = 0.0;
  cv::minMaxLoc(eigenvalues, &minEigenvalue, &maxEigenvalue);
  if (minEigenvalue < -1e-12 * std::max(maxEigenvalue, 1.0))
  {
    throw std::invalid_argument("position covariance must be positive semi-definite");
  }
  std::normal_distribution<double> normal(0.0, 1.0);
  cv::Vec3d error;
  for (int i = 0; i < 3; ++i)
  {
    const double draw = normal(rng);
    const double sigma = std::sqrt(std::max(eigenvalues.at<double>(i), 0.0));
    for (int axis = 0; axis < 3; ++axis)
    {
      error[axis] += sigma * draw * eigenvectors.at<double>(i, axis);
    }
  }
  return error;
}

// The R a sensor reports for a detection: its scaled position covariance, sizeNoise^2 and, from orienting sensors,
// yawNoise^2. Every axis without variance gets the default noise, so R stays positive definite.
inline TrackedObject::MeasurementMatrix
reportedMeasurementNoise(const Sensor &sensor, const PositionCovariance &model, const cv::Matx33d &covariance)
{
  TrackedObject::MeasurementMatrix noise;
  for (int row = 0; row < 3; ++row)
  {
    for (int col = 0; col < 3; ++col)
    {
      noise(MeasurementIndex::X + row, MeasurementIndex::X + col) = model.reportedScale * covariance(row, col);
    }
  }
  const double sizeVariance = sensor.sizeNoise * sensor.sizeNoise;
  for (const int index : {MeasurementIndex::LENGTH, MeasurementIndex::WIDTH, MeasurementIndex::HEIGHT})
  {
    noise(index, index) = sizeVariance;
  }
  noise(MeasurementIndex::YAW, MeasurementIndex::YAW) = sensor.orienting ? sensor.yawNoise * sensor.yawNoise : 0.0;

  for (int index = 0; index < TrackedObject::MeasurementSize; ++index)
  {
    if (noise(index, index) <= 0.0)
    {
      for (int other = 0; other < TrackedObject::MeasurementSize; ++other)
      {
        noise(index, other) = 0.0;
        noise(other, index) = 0.0;
      }
      noise(index, index) = model.defaultNoise;
    }
  }
  if (!(minEigenvalue(cv::Mat(noise)) > 0.0))
  {
    throw std::invalid_argument("reported measurement noise must be positive definite");
  }
  return noise;
}

inline std::vector<Observation> observe(const std::vector<TruthSample> &truth, Sensor &sensor, int objectId = 1)
{
  if (sensor.positionCovariance)
  {
    const auto &model = *sensor.positionCovariance;
    if (sensor.positionNoise > 0.0 || sensor.zNoise > 0.0)
    {
      throw std::invalid_argument("positionCovariance replaces positionNoise and zNoise");
    }
    if (!model.covariance || !(model.reportedScale > 0.0) || !(model.defaultNoise > 0.0))
    {
      throw std::invalid_argument(
        "positionCovariance needs a covariance and a positive reportedScale and defaultNoise");
    }
  }
  std::normal_distribution<double> noise(0.0, 1.0);
  std::normal_distribution<double> zNoiseDistribution(0.0, 1.0);
  std::vector<Observation> observations;
  for (const auto &sample : truth)
  {
    auto detection = makeDetection(sample);
    std::optional<cv::Matx33d> trueCovariance;
    if (sensor.positionCovariance)
    {
      trueCovariance = sensor.positionCovariance->covariance(sample);
      const cv::Vec3d error = correlatedNoise(*trueCovariance, sensor.covarianceRng);
      detection.x += error[0];
      detection.y += error[1];
      detection.z += error[2];
      detection.zMeasured = sensor.positionCovariance->zMeasured;
    }
    if (sensor.positionNoise > 0.0)
    {
      detection.x += sensor.positionNoise * noise(sensor.rng);
      detection.y += sensor.positionNoise * noise(sensor.rng);
    }
    if (sensor.zNoise > 0.0)
    {
      detection.z += sensor.zNoise * zNoiseDistribution(sensor.zRng);
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
    if (sensor.positionCovariance && sensor.positionCovariance->reported)
    {
      detection.measurementNoiseCov = reportedMeasurementNoise(sensor, *sensor.positionCovariance, *trueCovariance);
    }
    observations.push_back({sample.t, std::move(detection), sensor.id, objectId, trueCovariance});
  }
  return observations;
}

class FilterRun;

// Notified by FilterRun after initialize(), every track() and every coast(), e.g. by ScenarioRecorder.
class FilterRunObserver
{
public:
  virtual ~FilterRunObserver() = default;
  // `observation` is the one used by this step; std::nullopt for coast().
  virtual void filterStep(const FilterRun &run, const std::optional<Observation> &observation) = 0;
};

// Drives one MultiModelKalmanEstimator the way TrackManager does, without association or lifecycle.
// trackId names the estimate and its detections for an observer; use the ground-truth object id.
class FilterRun
{
public:
  explicit FilterRun(TrackManagerConfig config = productionConfig(),
                     FilterRunObserver *observer = nullptr,
                     int trackId = 1)
    : mConfig(std::move(config))
    , mObserver(observer)
    , mTrackId(trackId)
  {
  }

  // Initializes on the first observation, then predict + correct per observation. One state per observation.
  std::vector<TrackedObject> feed(const std::vector<Observation> &observations)
  {
    std::vector<TrackedObject> states;
    for (const auto &observation : observations)
    {
      if (mInitialized)
      {
        estimator.track(observation.detection, atSeconds(observation.t));
      }
      else
      {
        estimator.initialize(observation.detection,
                             atSeconds(observation.t),
                             mConfig.mDefaultProcessNoise,
                             mConfig.mDefaultMeasurementNoise,
                             mConfig.mInitStateCovariance,
                             mConfig.mMotionModels);
        mInitialized = true;
      }
      notify(observation);
      states.push_back(state());
    }
    return states;
  }

  void coast(double seconds)
  {
    estimator.predict(seconds);
    notify(std::nullopt);
  }

  TrackedObject state() const
  {
    return estimator.currentState();
  }

  const TrackManagerConfig &config() const
  {
    return mConfig;
  }

  int trackId() const
  {
    return mTrackId;
  }

  MultiModelKalmanEstimator estimator;

private:
  void notify(const std::optional<Observation> &observation) const
  {
    if (mObserver != nullptr)
    {
      mObserver->filterStep(*this, observation);
    }
  }

  TrackManagerConfig mConfig;
  FilterRunObserver *mObserver = nullptr;
  int mTrackId = 1;
  bool mInitialized = false;
};

inline const char *motionModelName(MotionModel model)
{
  switch (model)
  {
    case MotionModel::CV:
      return "CV";
    case MotionModel::CA:
      return "CA";
    case MotionModel::CTRV:
      return "CTRV";
    case MotionModel::CP:
      return "CP";
  }
  return "unknown";
}

struct RunOptions
{
  double warmUp = 2.0;                   // errors are measured from this time on [s]
  FilterRunObserver *observer = nullptr; // e.g. a ScenarioRecorder
  TrackManagerConfig config = productionConfig();
  int trackId = 1;
};

struct ScenarioMetrics
{
  double maxHorizontalError = 0.0; // [m] from warmUp on
  double rmsHorizontalError = 0.0;
  double maxVerticalError = 0.0;
  double rmsVerticalError = 0.0;
  double finalSpeedError = 0.0; // |horizontal speed estimate - truth speed| at the last step [m/s]
  double finalVzError = 0.0;    // |vz estimate - truth vz| at the last step [m/s]
};

struct ScenarioResult
{
  std::vector<TruthSample> truth;
  std::vector<TrackedObject> states;                   // estimate after each observation, in truth order
  std::vector<MotionModel> models;                     // order of the model probabilities
  std::vector<std::vector<double>> modelProbabilities; // after each observation
  double warmUp = 0.0;

  // Throws std::invalid_argument when no step is at or after warmUp.
  ScenarioMetrics metrics() const
  {
    const auto horizontal = positionErrors(truth, states, warmUp);
    if (horizontal.empty())
    {
      throw std::invalid_argument("no step at or after warmUp");
    }
    const auto vertical = verticalErrors(truth, states, warmUp);
    ScenarioMetrics result;
    result.maxHorizontalError = *std::ranges::max_element(horizontal);
    result.rmsHorizontalError = rms(horizontal);
    result.maxVerticalError = *std::ranges::max_element(vertical);
    result.rmsVerticalError = rms(vertical);
    result.finalSpeedError = std::abs(std::hypot(states.back().vx, states.back().vy) - truth.back().speed);
    result.finalVzError = std::abs(states.back().vz - truth.back().vz);
    return result;
  }

  // Mean over all steps; throws std::invalid_argument for a model not in `models` or a run without steps.
  double meanProbability(MotionModel model) const
  {
    const auto found = std::ranges::find(models, model);
    if (found == models.end())
    {
      throw std::invalid_argument(std::string("model not in the run: ") + motionModelName(model));
    }
    if (modelProbabilities.empty())
    {
      throw std::invalid_argument("run has no steps");
    }
    const auto index = static_cast<size_t>(found - models.begin());
    double sum = 0.0;
    for (const auto &probabilities : modelProbabilities)
    {
      sum += probabilities.at(index);
    }
    return sum / static_cast<double>(modelProbabilities.size());
  }

  // Estimate at the truth sample nearest to t (the earlier one on a tie); throws std::invalid_argument when the run is
  // empty.
  const TrackedObject &stateAt(double t) const
  {
    if (truth.empty() || states.size() != truth.size())
    {
      throw std::invalid_argument("run has no steps");
    }
    const auto nearest = std::ranges::min_element(
      truth, [t](const TruthSample &a, const TruthSample &b) { return std::abs(a.t - t) < std::abs(b.t - t); });
    return states[static_cast<size_t>(nearest - truth.begin())];
  }
};

// The sensor is taken by value: two runs given the same sensor see identical noise, which makes paired comparisons
// possible. Observations are fed one at a time.
inline ScenarioResult runScenario(const std::vector<TruthSample> &truth, Sensor sensor, const RunOptions &options = {})
{
  ScenarioResult result;
  result.truth = truth;
  result.warmUp = options.warmUp;
  result.models.assign(options.config.mMotionModels.begin(), options.config.mMotionModels.end());

  FilterRun run(options.config, options.observer, options.trackId);
  for (const auto &observation : observe(truth, sensor))
  {
    result.states.push_back(run.feed({observation}).front());
    const cv::Mat probability = run.estimator.getModelProbability();
    std::vector<double> row;
    for (int i = 0; i < probability.rows; ++i)
    {
      row.push_back(probability.at<double>(i, 0));
    }
    result.modelProbabilities.push_back(std::move(row));
  }
  return result;
}

// Largest absolute difference between two runs over all steps; for paired "same case with and without z" checks.
struct StateDifference
{
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double vx = 0.0;
  double vy = 0.0;
  double vz = 0.0;
  double yaw = 0.0;         // wrapped to [-pi, pi]
  double probability = 0.0; // over all models
};

// Throws std::invalid_argument when the runs differ in step count or models.
inline StateDifference maxDifference(const ScenarioResult &a, const ScenarioResult &b)
{
  if (a.states.size() != b.states.size() || a.modelProbabilities.size() != b.modelProbabilities.size()
      || a.models != b.models)
  {
    throw std::invalid_argument("runs differ in step count or models");
  }
  StateDifference diff;
  for (size_t i = 0; i < a.states.size(); ++i)
  {
    const auto &p = a.states[i];
    const auto &q = b.states[i];
    diff.x = std::max(diff.x, std::abs(p.x - q.x));
    diff.y = std::max(diff.y, std::abs(p.y - q.y));
    diff.z = std::max(diff.z, std::abs(p.z - q.z));
    diff.vx = std::max(diff.vx, std::abs(p.vx - q.vx));
    diff.vy = std::max(diff.vy, std::abs(p.vy - q.vy));
    diff.vz = std::max(diff.vz, std::abs(p.vz - q.vz));
    diff.yaw = std::max(diff.yaw, std::abs(std::remainder(p.yaw - q.yaw, 2.0 * std::numbers::pi)));
    const auto &pa = a.modelProbabilities[i];
    const auto &pb = b.modelProbabilities.at(i);
    for (size_t m = 0; m < pa.size(); ++m)
    {
      diff.probability = std::max(diff.probability, std::abs(pa[m] - pb.at(m)));
    }
  }
  return diff;
}

} // namespace rv::tracking::test
