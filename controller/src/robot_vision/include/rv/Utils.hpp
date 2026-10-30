// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <stdint.h>
#include <algorithm>
#include <stdexcept>

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

/**
 * @brief Chi-squared gate threshold for innovation gating (2 DOF position).
 *
 * For k=2: Q(p) = -2 * ln(1 - p).  E.g. p=0.99 -> ~9.21.
 */
inline double chi2Threshold(double gate_probability, int degrees_of_freedom = 2)
{
  gate_probability = clamp(gate_probability, 1e-9, 1.0 - 1e-9);
  if (degrees_of_freedom == 2)
  {
    return -2.0 * std::log(1.0 - gate_probability);
  }
  throw std::invalid_argument("chi2Threshold: only 2 degrees of freedom supported");
}

} // namespace rv
