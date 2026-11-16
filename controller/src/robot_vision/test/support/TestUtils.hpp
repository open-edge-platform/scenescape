// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <algorithm>
#include <chrono>

#include <opencv2/core.hpp>

#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace rv::tracking::test {

// Positions in TrackedObject::stateVector().
namespace idx {
enum : int
{
  X = StateIndex::X,
  Y = StateIndex::Y,
  Vx = StateIndex::VX,
  Vy = StateIndex::VY,
  Ax = StateIndex::AX,
  Ay = StateIndex::AY,
  Z = StateIndex::Z,
  Vz = StateIndex::VZ,
  Length = StateIndex::LENGTH,
  Width = StateIndex::WIDTH,
  Height = StateIndex::HEIGHT,
  Yaw = StateIndex::YAW,
  YawRate = StateIndex::YAW_RATE
};
} // namespace idx

inline std::chrono::system_clock::time_point atMs(int milliseconds)
{
  return std::chrono::system_clock::time_point(std::chrono::milliseconds(milliseconds));
}

inline std::chrono::system_clock::time_point atSeconds(double seconds)
{
  return std::chrono::system_clock::time_point(
    std::chrono::duration_cast<std::chrono::system_clock::duration>(std::chrono::duration<double>(seconds)));
}

inline TrackManagerConfig productionConfig()
{
  TrackManagerConfig config;
  config.mDefaultProcessNoise = kProductionProcessNoise;
  config.mDefaultMeasurementNoise = kProductionMeasurementNoise;
  config.mInitStateCovariance = kProductionInitStateCovariance;
  config.mMotionModels = kProductionMotionModels;
  return config;
}

// Row of a motion model in getModelProbability() and currentStates() for productionConfig().
inline int modelIndex(MotionModel model)
{
  const auto &models = kProductionMotionModels;
  return static_cast<int>(std::ranges::find(models, model) - models.begin());
}

inline double minEigenvalue(const cv::Mat &matrix)
{
  cv::Mat eigenvalues;
  cv::eigen(0.5 * (matrix + matrix.t()), eigenvalues);
  double minValue = 0.0;
  cv::minMaxLoc(eigenvalues, &minValue);
  return minValue;
}

inline TrackedObject makeDetection(double x, double y, double z, double length, double width, double height)
{
  TrackedObject object;
  object.x = x;
  object.y = y;
  object.z = z;
  object.length = length;
  object.width = width;
  object.height = height;
  return object;
}

// Diagonal per-detection R with the given x/y/z variances and `rest` on length, width, height and yaw.
inline TrackedObject::MeasurementMatrix
diagonalMeasurementNoise(double varX, double varY, double varZ, double rest = 0.2)
{
  TrackedObject::MeasurementMatrix noise = TrackedObject::MeasurementMatrix::eye() * rest;
  noise(MeasurementIndex::X, MeasurementIndex::X) = varX;
  noise(MeasurementIndex::Y, MeasurementIndex::Y) = varY;
  noise(MeasurementIndex::Z, MeasurementIndex::Z) = varZ;
  return noise;
}

} // namespace rv::tracking::test
