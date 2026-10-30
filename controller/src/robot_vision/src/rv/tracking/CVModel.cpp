// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CVModel.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

void CVModel::stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1)
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
  double z = x_k.at<double>(StateIndex::Z, 0);
  double vz = x_k.at<double>(StateIndex::VZ, 0);
  /*
   * The equations for the constant velocity model are:
   */
  x_kplus1.at<double>(StateIndex::X, 0) = x + vx * deltaT;
  x_kplus1.at<double>(StateIndex::Y, 0) = y + vy * deltaT;
  x_kplus1.at<double>(StateIndex::VX, 0) = vx;
  x_kplus1.at<double>(StateIndex::VY, 0) = vy;
  x_kplus1.at<double>(StateIndex::AX, 0) = 0.;
  x_kplus1.at<double>(StateIndex::AY, 0) = 0.;
  x_kplus1.at<double>(StateIndex::Z, 0) = z + vz * deltaT;
  x_kplus1.at<double>(StateIndex::VZ, 0) = vz;
  x_kplus1.at<double>(StateIndex::LENGTH, 0) = x_k.at<double>(StateIndex::LENGTH, 0);
  x_kplus1.at<double>(StateIndex::WIDTH, 0) = x_k.at<double>(StateIndex::WIDTH, 0);
  x_kplus1.at<double>(StateIndex::HEIGHT, 0) = x_k.at<double>(StateIndex::HEIGHT, 0);
  x_kplus1.at<double>(StateIndex::YAW, 0) = x_k.at<double>(StateIndex::YAW, 0);
  x_kplus1.at<double>(StateIndex::YAW_RATE, 0) = 0.;

  x_kplus1 += vk; // additive process noise
}

void CVModel::measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k)
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
