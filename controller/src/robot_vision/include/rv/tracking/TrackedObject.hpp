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

/// Indices into TrackedObject::stateVector() / UKF state.
/// Layout: [x, y, vx, vy, ax, ay, z, vz, length, width, height, yaw, yaw_rate]
struct StateIndex
{
  static constexpr int X = 0;
  static constexpr int Y = 1;
  static constexpr int VX = 2;
  static constexpr int VY = 3;
  static constexpr int AX = 4;
  static constexpr int AY = 5;
  static constexpr int Z = 6;
  static constexpr int VZ = 7;
  static constexpr int LENGTH = 8;
  static constexpr int WIDTH = 9;
  static constexpr int HEIGHT = 10;
  static constexpr int YAW = 11;
  static constexpr int YAW_RATE = 12;
};

/// Indices into TrackedObject::measurementVector() / UKF measurement.
/// Layout: [x, y, z, length, width, height, yaw]
struct MeasurementIndex
{
  static constexpr int X = 0;
  static constexpr int Y = 1;
  static constexpr int Z = 2;
  static constexpr int LENGTH = 3;
  static constexpr int WIDTH = 4;
  static constexpr int HEIGHT = 5;
  static constexpr int YAW = 6;
};

class TrackedObject
{
public:
  TrackedObject();

  static constexpr int StateSize = 13;
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
  double vz{0.};

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

  /// True when Z came from a measured 3D pose (translation / 3D OD), not ground-plane projection.
  /// Used by EuclideanBirth: XY-only if either side lacks measured Z; XYZ when both have it.
  bool zMeasured{false};

  std::string toString() const;

  // tracked object parameters; fixed-size matrices, so copies never share them
  MeasurementVector predictedMeasurementMean;
  MeasurementMatrix predictedMeasurementCov;
  MeasurementMatrix predictedMeasurementCovInv;
  StateMatrix errorCovariance;

  Classification classification;

  std::unordered_map<std::string, std::string> attributes;

  /// True when 3D speed squared exceeds 1 m²/s² (includes vertical motion).
  /// Affects track deletion / suspend aging (dynamic vs static coast timeouts).
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
   * @brief Convert to a fixed-size measurement vector (x, y, z, length, width, height, yaw).
   *
   * Converts to cv::Mat and cv::InputArray where those are needed.
   */
  MeasurementVector measurementVector() const;
};

static_assert(TrackedObject::StateSize == StateIndex::YAW_RATE + 1, "StateSize must match the StateIndex layout");
static_assert(TrackedObject::MeasurementSize == MeasurementIndex::YAW + 1,
              "MeasurementSize must match the MeasurementIndex layout");

} // namespace tracking
} // namespace rv
