// SPDX-FileCopyrightText: 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <stdint.h>
#include <algorithm>
#include <numbers>
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
 * @brief CDF of χ² with 3 degrees of freedom.
 *
 * F(x) = erf(√(x/2)) - √(2x/π)·exp(-x/2).
 */
inline double chi2Cdf3(double x)
{
  if (x <= 0.0)
  {
    return 0.0;
  }
  const double s = std::sqrt(x / 2.0);
  return std::erf(s) - std::sqrt(2.0 * x / std::numbers::pi) * std::exp(-x / 2.0);
}

/**
 * @brief Chi-squared gate threshold for innovation gating.
 *
 * For k=2: Q(p) = -2 * ln(1 - p).  E.g. p=0.99 -> ~9.21.
 * For k=3: numerical inverse of the χ²(3) CDF.  E.g. p=0.99 -> ~11.34.
 *      The last result is cached per thread, since callers pass the same probability every frame.
 */
inline double chi2Threshold(double gate_probability, int degrees_of_freedom = 2)
{
  gate_probability = clamp(gate_probability, 1e-9, 1.0 - 1e-9);
  if (degrees_of_freedom == 2)
  {
    return -2.0 * std::log(1.0 - gate_probability);
  }
  if (degrees_of_freedom == 3)
  {
    thread_local double cachedProbability = -1.0;
    thread_local double cachedThreshold = 0.0;
    if (gate_probability == cachedProbability)
    {
      return cachedThreshold;
    }
    double lo = 0.0;
    double hi = 1.0;
    while (chi2Cdf3(hi) < gate_probability)
    {
      hi *= 2.0;
    }
    for (int i = 0; i < 64; ++i)
    {
      const double mid = 0.5 * (lo + hi);
      if (chi2Cdf3(mid) < gate_probability)
      {
        lo = mid;
      }
      else
      {
        hi = mid;
      }
    }
    cachedProbability = gate_probability;
    cachedThreshold = 0.5 * (lo + hi);
    return cachedThreshold;
  }
  throw std::invalid_argument("chi2Threshold: only 2 or 3 degrees of freedom supported");
}

} // namespace rv
