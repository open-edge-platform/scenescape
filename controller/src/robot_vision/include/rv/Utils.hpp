// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <stdint.h>
#include <algorithm>

namespace rv {
// clamp function available in c++17
template <typename T> inline T clamp(const T &value, const T &lower, const T &upper)
{
  return std::max(lower, std::min(value, upper));
}

// convert chrono duration object to its equivalent in seconds as double precision floating point
double inline toSeconds(std::chrono::duration<double> const &duration)
{
  return duration.count();
}

inline std::chrono::system_clock::time_point addSecondsToTimestamp(const std::chrono::system_clock::time_point &timestamp, std::chrono::duration<double> const &duration)
{
  return timestamp + std::chrono::duration_cast<std::chrono::system_clock::duration>(duration);
}

// calculates the difference between two angles, wraps the angles to any multiple of 2*pi
double inline angleDifference(double theta1, double theta2)
{
  auto ax = std::cos(theta1);
  auto ay = std::sin(theta1);

  auto bx = std::cos(theta2);
  auto by = std::sin(theta2);

  auto cx = ax * bx + ay * by;
  auto cy = ax * by - ay * bx;

  return std::atan2(cy, cx);
}

// calculate the difference between two angles, considering possible jumps of M_PI
// this means that if theta1 = theta2  then  theta1 + M_PI = theta2
double inline deltaTheta(double theta1, double theta2)
{
  auto angleA = angleDifference(theta1, theta2);
  auto angleB = angleDifference(theta1 + M_PI, theta2); // consider the case where there is a M_PI jump

  if (fabs(angleA) < fabs(angleB))
  {
    return angleA;
  }
  else
  {
    return angleB;
  }
}

} // namespace rv
