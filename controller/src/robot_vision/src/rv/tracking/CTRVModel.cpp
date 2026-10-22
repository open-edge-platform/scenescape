// SPDX-FileCopyrightText: 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/CTRVModel.hpp"
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

void CTRVModel::stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1)
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
  double w = x_k.at<double>(StateIndex::YAW_RATE, 0);
  double yaw = x_k.at<double>(StateIndex::YAW, 0);

  double v = sqrt(vx * vx + vy * vy);
  double velocityYaw = atan2(vy, vx);     // Velocity yaw

  double nextYaw = velocityYaw + w * deltaT; // Velocity yaw for the next time iteration
  // Attitude yaw integrates turn rate (CTRV). Previously this state was frozen
  // on predict, so camera-only curves left published orientation stuck after a
  // sticky LiDAR observation while XY followed the path.
  double nextAttitudeYaw = yaw + w * deltaT;

  double cosNextYaw = cos(nextYaw);
  double sinNextYaw = sin(nextYaw);


  if (fabs(w) >= 1e-3)
  {
    x_kplus1.at<double>(StateIndex::X, 0) = x + v / w * (sinNextYaw - sin(velocityYaw));
    x_kplus1.at<double>(StateIndex::Y, 0) = y + v / w * (cos(velocityYaw) - cosNextYaw);
  }
  else
  {
    // as the turn rate converges to zero, the equations are:
    x_kplus1.at<double>(StateIndex::X, 0) = x + v * cosNextYaw * deltaT;
    x_kplus1.at<double>(StateIndex::Y, 0) = y + v * sinNextYaw * deltaT;
  }

  x_kplus1.at<double>(StateIndex::VX, 0) = v * cosNextYaw;
  x_kplus1.at<double>(StateIndex::VY, 0) = v * sinNextYaw;
  x_kplus1.at<double>(StateIndex::AX, 0) = 0.;
  x_kplus1.at<double>(StateIndex::AY, 0) = 0.;
  x_kplus1.at<double>(StateIndex::Z, 0) = z + vz * deltaT;
  x_kplus1.at<double>(StateIndex::VZ, 0) = vz;
  x_kplus1.at<double>(StateIndex::LENGTH, 0) = x_k.at<double>(StateIndex::LENGTH, 0);
  x_kplus1.at<double>(StateIndex::WIDTH, 0) = x_k.at<double>(StateIndex::WIDTH, 0);
  x_kplus1.at<double>(StateIndex::HEIGHT, 0) = x_k.at<double>(StateIndex::HEIGHT, 0);
  x_kplus1.at<double>(StateIndex::YAW, 0) = nextAttitudeYaw;
  x_kplus1.at<double>(StateIndex::YAW_RATE, 0) = w;

  x_kplus1 += vk; // additive process noise
}

void CTRVModel::measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k)
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
