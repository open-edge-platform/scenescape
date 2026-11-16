// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/TrackedObject.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iterator>
#include <stdexcept>

namespace rv {
namespace tracking {

TrackedObject::TrackedObject()
  : predictedMeasurementCov(1e-4 * MeasurementMatrix::eye())
  , errorCovariance(1e-4 * StateMatrix::eye())
{
  classification = Classification::Constant(1,1.0);
}

std::string TrackedObject::toString() const
{
  return "TrackedObject( id: " + std::to_string(id) + ", x:" + std::to_string(x) + ", y:" + std::to_string(y)
    + ", vx:" + std::to_string(vx) + ", vy:" + std::to_string(vy) + ", ax:" + std::to_string(ax) + ", ay:"
    + std::to_string(ay) + ", z:" + std::to_string(z) + ", vz:" + std::to_string(vz) + ", l:"
    + std::to_string(length) + ", w:" + std::to_string(width) + ", h:" + std::to_string(height)
    + ", yaw:" + std::to_string(yaw) + ", yaw_rate:" + std::to_string(w) + ")";
}

bool TrackedObject::isDynamic() const
{
  // Horizontal always counts. vz only when height was measured: otherwise process noise on an
  // unobserved z can invent |vz| > 1 and cut coast lifetime on the dynamic timeout.
  const double horizontal = vx * vx + vy * vy;
  if (!z_measured)
  {
    return horizontal > 1.0;
  }
  return (horizontal + vz * vz) > 1.0;
}

Eigen::VectorXf TrackedObject::getVectorXf() const
{
  Eigen::VectorXf vector(StateSize);
  vector(StateIndex::X) = x;
  vector(StateIndex::Y) = y;
  vector(StateIndex::VX) = vx;
  vector(StateIndex::VY) = vy;
  vector(StateIndex::AX) = ax;
  vector(StateIndex::AY) = ay;
  vector(StateIndex::Z) = z;
  vector(StateIndex::VZ) = vz;
  vector(StateIndex::LENGTH) = length;
  vector(StateIndex::WIDTH) = width;
  vector(StateIndex::HEIGHT) = height;
  vector(StateIndex::YAW) = yaw;
  vector(StateIndex::YAW_RATE) = w;

  return vector;
}

void TrackedObject::setVectorXf(const Eigen::VectorXf &vector)
{
  x = vector(StateIndex::X);
  y = vector(StateIndex::Y);
  vx = vector(StateIndex::VX);
  vy = vector(StateIndex::VY);
  ax = vector(StateIndex::AX);
  ay = vector(StateIndex::AY);
  z = vector(StateIndex::Z);
  vz = vector(StateIndex::VZ);
  length = vector(StateIndex::LENGTH);
  width = vector(StateIndex::WIDTH);
  height = vector(StateIndex::HEIGHT);
  yaw = vector(StateIndex::YAW);
  w = vector(StateIndex::YAW_RATE);
}

/**
 * @brief Convert to a cv::Mat vector.
 */
cv::Mat TrackedObject::stateVector() const
{
  cv::Mat vector(StateSize, 1, CV_64F);
  vector.at<double>(StateIndex::X, 0) = x;
  vector.at<double>(StateIndex::Y, 0) = y;
  vector.at<double>(StateIndex::VX, 0) = vx;
  vector.at<double>(StateIndex::VY, 0) = vy;
  vector.at<double>(StateIndex::AX, 0) = ax;
  vector.at<double>(StateIndex::AY, 0) = ay;
  vector.at<double>(StateIndex::Z, 0) = z;
  vector.at<double>(StateIndex::VZ, 0) = vz;
  vector.at<double>(StateIndex::LENGTH, 0) = length;
  vector.at<double>(StateIndex::WIDTH, 0) = width;
  vector.at<double>(StateIndex::HEIGHT, 0) = height;
  vector.at<double>(StateIndex::YAW, 0) = yaw;
  vector.at<double>(StateIndex::YAW_RATE, 0) = w;

  return vector;
}

/**
 * @brief Fill data from a cv::Mat vector.
 */
void TrackedObject::setStateVector(const cv::Mat &vector)
{
  x = vector.at<double>(StateIndex::X, 0);
  y = vector.at<double>(StateIndex::Y, 0);
  vx = vector.at<double>(StateIndex::VX, 0);
  vy = vector.at<double>(StateIndex::VY, 0);
  ax = vector.at<double>(StateIndex::AX, 0);
  ay = vector.at<double>(StateIndex::AY, 0);
  z = vector.at<double>(StateIndex::Z, 0);
  vz = vector.at<double>(StateIndex::VZ, 0);
  length = vector.at<double>(StateIndex::LENGTH, 0);
  width = vector.at<double>(StateIndex::WIDTH, 0);
  height = vector.at<double>(StateIndex::HEIGHT, 0);
  yaw = vector.at<double>(StateIndex::YAW, 0);
  w = vector.at<double>(StateIndex::YAW_RATE, 0);
}

/**
 * @brief Convert to a fixed-size measurement vector.
 */
TrackedObject::MeasurementVector TrackedObject::measurementVector() const
{
  MeasurementVector vector;
  vector(MeasurementIndex::X) = x;
  vector(MeasurementIndex::Y) = y;
  vector(MeasurementIndex::Z) = z;
  vector(MeasurementIndex::LENGTH) = length;
  vector(MeasurementIndex::WIDTH) = width;
  vector(MeasurementIndex::HEIGHT) = height;
  vector(MeasurementIndex::YAW) = yaw;

  return vector;
}

namespace {

bool allFinite(const TrackedObject::MeasurementMatrix &matrix)
{
  return std::all_of(std::begin(matrix.val), std::end(matrix.val), [](double value) { return std::isfinite(value); });
}

} // namespace

std::optional<TrackedObject::MeasurementMatrix>
validMeasurementNoiseCov(const TrackedObject::MeasurementMatrix &noise) noexcept
{
  constexpr int n = TrackedObject::MeasurementSize;
  const TrackedObject::MeasurementMatrix symmetric = 0.5 * (noise + noise.t());
  // Checked after symmetrizing, so a non-finite entry and an overflowing sum are both caught.
  if (!allFinite(symmetric))
  {
    return std::nullopt;
  }
  // LDL^T without pivoting: symmetric is positive definite iff every pivot is positive.
  std::array<std::array<double, n>, n> lower{};
  std::array<double, n> pivots{};
  for (int j = 0; j < n; ++j)
  {
    double pivot = symmetric(j, j);
    for (int k = 0; k < j; ++k)
    {
      pivot -= lower[j][k] * lower[j][k] * pivots[k];
    }
    if (!(pivot > 0.0))
    {
      return std::nullopt;
    }
    pivots[j] = pivot;
    for (int i = j + 1; i < n; ++i)
    {
      double value = symmetric(i, j);
      for (int k = 0; k < j; ++k)
      {
        value -= lower[i][k] * lower[j][k] * pivots[k];
      }
      lower[i][j] = value / pivot;
    }
  }
  return symmetric;
}

TrackedObject::MeasurementMatrix validatedMeasurementNoiseCov(const TrackedObject::MeasurementMatrix &noise)
{
  if (!allFinite(noise))
  {
    throw std::invalid_argument("measurement_noise_covariance must be finite");
  }
  const auto valid = validMeasurementNoiseCov(noise);
  if (!valid)
  {
    throw std::invalid_argument("measurement_noise_covariance must be positive definite");
  }
  return *valid;
}

void clearInvalidMeasurementNoiseCov(TrackedObject &object) noexcept
{
  if (object.measurementNoiseCov)
  {
    object.measurementNoiseCov = validMeasurementNoiseCov(*object.measurementNoiseCov);
  }
}

} // namespace tracking
} // namespace rv
