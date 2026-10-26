// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

TrackedObject::TrackedObject()
{
  classification = Classification::Constant(1,1.0);

  predictedMeasurementMean = cv::Mat::zeros(TrackedObject::MeasurementSize, 1, CV_64F);
  predictedMeasurementCov = 1e-4 * cv::Mat::eye(TrackedObject::MeasurementSize, TrackedObject::MeasurementSize, CV_64F);
  predictedMeasurementCovInv = 1e4 * cv::Mat::eye(TrackedObject::MeasurementSize, TrackedObject::MeasurementSize, CV_64F);
  errorCovariance = 1e-4 * cv::Mat::eye(TrackedObject::StateSize, TrackedObject::StateSize, CV_64F);
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
  // 3D speed: vertical motion counts toward dynamic coast / deletion aging.
  return (vx * vx + vy * vy + vz * vz) > 1.0;
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
 * @brief Convert to a cv::Mat vector.
 */
cv::Mat TrackedObject::measurementVector() const
{
  cv::Mat vector(MeasurementSize, 1, CV_64F);
  vector.at<double>(MeasurementIndex::X, 0) = x;
  vector.at<double>(MeasurementIndex::Y, 0) = y;
  vector.at<double>(MeasurementIndex::Z, 0) = z;
  vector.at<double>(MeasurementIndex::LENGTH, 0) = length;
  vector.at<double>(MeasurementIndex::WIDTH, 0) = width;
  vector.at<double>(MeasurementIndex::HEIGHT, 0) = height;
  vector.at<double>(MeasurementIndex::YAW, 0) = yaw;

  return vector;
}




} // namespace tracking
} // namespace rv
