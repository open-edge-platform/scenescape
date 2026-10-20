// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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

  static constexpr int StateSize = 12;
  static constexpr int MeasurementSize = 7;

  using MeasurementVector = cv::Matx<double, MeasurementSize, 1>;
  using MeasurementMatrix = cv::Matx<double, MeasurementSize, MeasurementSize>;
  using StateMatrix = cv::Matx<double, StateSize, StateSize>;

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

  // tracked object parameters; fixed-size matrices, so copies never share them
  MeasurementVector predictedMeasurementMean;
  MeasurementMatrix predictedMeasurementCov;
  MeasurementMatrix predictedMeasurementCovInv;
  StateMatrix errorCovariance;

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
