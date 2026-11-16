// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/TrackedObject.hpp"

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

TrackedObject::MeasurementMatrix validatedMeasurementNoiseCov(const TrackedObject::MeasurementMatrix &noise)
{
  if (!cv::checkRange(noise))
  {
    throw std::invalid_argument("measurement_noise_covariance must be finite");
  }
  const TrackedObject::MeasurementMatrix symmetric = 0.5 * (noise + noise.t());
  cv::Mat eigenvalues;
  cv::eigen(symmetric, eigenvalues);
  double minEigenvalue = 0.0;
  cv::minMaxLoc(eigenvalues, &minEigenvalue);
  if (!(minEigenvalue > 0.0))
  {
    throw std::invalid_argument("measurement_noise_covariance must be positive definite");
  }
  return symmetric;
}

void ensureValidMeasurementNoiseCov(TrackedObject &object)
{
  if (object.measurementNoiseCov)
  {
    object.measurementNoiseCov = validatedMeasurementNoiseCov(*object.measurementNoiseCov);
  }
}

void clearInvalidMeasurementNoiseCov(TrackedObject &object)
{
  if (!object.measurementNoiseCov)
  {
    return;
  }
  try
  {
    object.measurementNoiseCov = validatedMeasurementNoiseCov(*object.measurementNoiseCov);
  }
  catch (const std::invalid_argument &)
  {
    object.measurementNoiseCov.reset();
  }
}

} // namespace tracking
} // namespace rv
