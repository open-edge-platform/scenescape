// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

const int TrackedObject::StateSize = 12;
const int TrackedObject::MeasurementSize = 7;

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
    + std::to_string(ay) + ", z:" + std::to_string(z) + ", l:" + std::to_string(length) + ", w:"
    + std::to_string(width) + ", h:" + std::to_string(height) + ", yaw:" + std::to_string(yaw) + ", yaw_rate:"
    + std::to_string(w) + ")";
}

bool TrackedObject::isDynamic() const
{
  return (vx * vx + vy * vy) > 1.0;
}

Eigen::VectorXf TrackedObject::getVectorXf() const
{
  Eigen::VectorXf vector(StateSize);
  vector(0) = x;
  vector(1) = y;
  vector(2) = vx;
  vector(3) = vy;
  vector(4) = ax;
  vector(5) = ay;
  vector(6) = z;
  vector(7) = length;
  vector(8) = width;
  vector(9) = height;
  vector(10) = yaw;
  vector(11) = w;

  return vector;
}

void TrackedObject::setVectorXf(const Eigen::VectorXf &vector)
{
  x = vector(0);
  y = vector(1);
  vx = vector(2);
  vy = vector(3);
  ax = vector(4);
  ay = vector(5);
  z = vector(6);
  length = vector(7);
  width = vector(8);
  height = vector(9);
  yaw = vector(10);
  w = vector(11);
}

/**
 * @brief Convert to a cv::Mat vector.
 */
cv::Mat TrackedObject::stateVector() const
{
  cv::Mat vector(StateSize, 1, CV_64F);
  vector.at<double>(0, 0) = x;
  vector.at<double>(1, 0) = y;
  vector.at<double>(2, 0) = vx;
  vector.at<double>(3, 0) = vy;
  vector.at<double>(4, 0) = ax;
  vector.at<double>(5, 0) = ay;
  vector.at<double>(6, 0) = z;
  vector.at<double>(7, 0) = length;
  vector.at<double>(8, 0) = width;
  vector.at<double>(9, 0) = height;
  vector.at<double>(10, 0) = yaw;
  vector.at<double>(11, 0) = w;

  return vector;
}

/**
 * @brief Fill data from a cv::Mat vector.
 */
void TrackedObject::setStateVector(const cv::Mat &vector)
{
  x = vector.at<double>(0, 0);
  y = vector.at<double>(1, 0);
  vx = vector.at<double>(2, 0);
  vy = vector.at<double>(3, 0);
  ax = vector.at<double>(4, 0);
  ay = vector.at<double>(5, 0);
  z = vector.at<double>(6, 0);
  length = vector.at<double>(7, 0);
  width = vector.at<double>(8, 0);
  height = vector.at<double>(9, 0);
  yaw = vector.at<double>(10, 0);
  w = vector.at<double>(11, 0);
}

/**
 * @brief Convert to a cv::Mat vector.
 */
cv::Mat TrackedObject::measurementVector() const
{
  cv::Mat vector(MeasurementSize, 1, CV_64F);
  vector.at<double>(0, 0) = x;
  vector.at<double>(1, 0) = y;
  vector.at<double>(2, 0) = z;
  vector.at<double>(3, 0) = length;
  vector.at<double>(4, 0) = width;
  vector.at<double>(5, 0) = height;
  vector.at<double>(6, 0) = yaw;

  return vector;
}




} // namespace tracking
} // namespace rv
