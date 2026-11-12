// SPDX-FileCopyrightText: (C) 2020 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CAModel.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

void CAModel::stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1)
{
  cv::Mat vk = v_k.clone();

  /*
   * The time is considered the control input
   */
  double deltaT = u_k.at<double>(0, 0);

  double x = x_k.at<double>(StateIndex::X, 0);
  double y = x_k.at<double>(StateIndex::Y, 0);
  double vx = x_k.at<double>(StateIndex::VX, 0);
  double vy = x_k.at<double>(StateIndex::VY, 0);
  double ax = x_k.at<double>(StateIndex::AX, 0);
  double ay = x_k.at<double>(StateIndex::AY, 0);
  double z = x_k.at<double>(StateIndex::Z, 0);
  double vz = x_k.at<double>(StateIndex::VZ, 0);

  /*
   * The equations for the constant acceleration model are:
   * Vertical axis uses constant velocity (no az in state).
   */
  x_kplus1.at<double>(StateIndex::X, 0) = x + vx * deltaT + 0.5 * ax * deltaT * deltaT;
  x_kplus1.at<double>(StateIndex::Y, 0) = y + vy * deltaT + 0.5 * ay * deltaT * deltaT;
  x_kplus1.at<double>(StateIndex::VX, 0) = vx + ax * deltaT;
  x_kplus1.at<double>(StateIndex::VY, 0) = vy + ay * deltaT;
  x_kplus1.at<double>(StateIndex::AX, 0) = ax;
  x_kplus1.at<double>(StateIndex::AY, 0) = ay;
  x_kplus1.at<double>(StateIndex::Z, 0) = z + vz * deltaT;
  x_kplus1.at<double>(StateIndex::VZ, 0) = vz;
  x_kplus1.at<double>(StateIndex::LENGTH, 0) = x_k.at<double>(StateIndex::LENGTH, 0);
  x_kplus1.at<double>(StateIndex::WIDTH, 0) = x_k.at<double>(StateIndex::WIDTH, 0);
  x_kplus1.at<double>(StateIndex::HEIGHT, 0) = x_k.at<double>(StateIndex::HEIGHT, 0);
  x_kplus1.at<double>(StateIndex::YAW, 0) = x_k.at<double>(StateIndex::YAW, 0);
  x_kplus1.at<double>(StateIndex::YAW_RATE, 0) = 0;

  x_kplus1 += vk; // additive process noise
}

void CAModel::measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k)
{
  z_k.at<double>(MeasurementIndex::X, 0) = x_k.at<double>(StateIndex::X, 0);
  z_k.at<double>(MeasurementIndex::Y, 0) = x_k.at<double>(StateIndex::Y, 0);
  z_k.at<double>(MeasurementIndex::Z, 0) = x_k.at<double>(StateIndex::Z, 0);
  z_k.at<double>(MeasurementIndex::LENGTH, 0) = x_k.at<double>(StateIndex::LENGTH, 0);
  z_k.at<double>(MeasurementIndex::WIDTH, 0) = x_k.at<double>(StateIndex::WIDTH, 0);
  z_k.at<double>(MeasurementIndex::HEIGHT, 0) = x_k.at<double>(StateIndex::HEIGHT, 0);
  z_k.at<double>(MeasurementIndex::YAW, 0) = x_k.at<double>(StateIndex::YAW, 0);
  z_k += n_k; // additive measurement noise
}
} // namespace tracking
} // namespace rv
