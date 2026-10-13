// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <string>

#include <opencv2/core.hpp>

#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

namespace rv::tracking::test {

// Positions in TrackedObject::stateVector().
namespace idx {
enum : int
{
  X,
  Y,
  Vx,
  Vy,
  Ax,
  Ay,
  Z,
  Length,
  Width,
  Height,
  Yaw,
  YawRate
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

inline double minEigenvalue(const cv::Mat &matrix)
{
  cv::Mat eigenvalues;
  cv::eigen(0.5 * (matrix + matrix.t()), eigenvalues);
  double minValue = 0.0;
  cv::minMaxLoc(eigenvalues, &minValue);
  return minValue;
}

inline TrackedObject
makeBox(double x, double y, double z, double length, double width, double height, const std::string &cameraId = {})
{
  TrackedObject object;
  object.x = x;
  object.y = y;
  object.z = z;
  object.length = length;
  object.width = width;
  object.height = height;
  if (!cameraId.empty())
  {
    object.attributes["camera_id"] = cameraId;
  }
  return object;
}

} // namespace rv::tracking::test
