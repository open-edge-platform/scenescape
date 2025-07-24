// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <Eigen/Dense>
#include <opencv2/core.hpp>
#include <string>
#include <unordered_map>
#include <memory>

#include "rv/tracking/Classification.hpp"

namespace rv {
namespace tracking {
using Id = int32_t;
constexpr Id InvalidObjectId = -1;

class TrackedObject
{
public:
  TrackedObject();

  static const int StateSize;
  static const int MeasurementSize;

  Id id = InvalidObjectId;

  // Position
  double x{0.};
  double y{0.};
  double z{0.};

  // Linear Velocity
  double vx{0.};
  double vy{0.};

  // Linear Acceleration
  double ax{0.};
  double ay{0.};

  // Orientation
  double yaw{0.};
  double previousYaw{0.};

  // Angular velocity
  double w{0.}; // Turn rate

  // Size
  double length{0.}; // along x
  double width{0.};  // along y
  double height{0.}; // along z

  bool corrected{false};

  std::string toString() const;

  // tracked object parameters
  cv::Mat predictedMeasurementMean;
  cv::Mat predictedMeasurementCov;
  cv::Mat predictedMeasurementCovInv;
  cv::Mat errorCovariance;

  Classification classification;

  std::unordered_map<std::string, std::string> attributes;

  bool isDynamic() const;

  Eigen::VectorXf getVectorXf() const;

  void setVectorXf(const Eigen::VectorXf &vector);

  /**
   * @brief Convert to a cv::Mat vector.
   */
  cv::Mat stateVector() const;

  /**
   * @brief Fill data from a cv::Mat vector.
   */
  void setStateVector(const cv::Mat &vector);

  /**
   * @brief Convert to a cv::Mat vector.
   */
  cv::Mat measurementVector() const;
};



} // namespace tracking
} // namespace rv
