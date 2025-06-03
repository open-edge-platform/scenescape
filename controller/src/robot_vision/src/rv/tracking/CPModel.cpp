// ----------------- BEGIN LICENSE BLOCK ---------------------------------
//
// INTEL CONFIDENTIAL
//
// Copyright (c) 2019-2020 Intel Corporation
//
// This software and the related documents are Intel copyrighted materials, and
// your use of them is governed by the express license under which they were
// provided to you (License). Unless the License provides otherwise, you may not
// use, modify, copy, publish, distribute, disclose or transmit this software or
// the related documents without Intel's prior written permission.
//
// This software and the related documents are provided as is, with no express or
// implied warranties, other than those that are expressly stated in the License.
//
// ----------------- END LICENSE BLOCK -----------------------------------

#include <rv/tracking/CPModel.hpp>

namespace rv {
namespace tracking {

void CPModel::stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1)
{
  cv::Mat vk = v_k.clone();

  /*
   * The time is considered the control input
   */
  double deltaT = u_k.at<double>(0, 0);

  x_kplus1.at<double>(0, 0) = x_k.at<double>(0, 0);  // Position in X
  x_kplus1.at<double>(1, 0) = x_k.at<double>(1, 0);  // Position in Y
  x_kplus1.at<double>(2, 0) = 0;                     // Velocity in X
  x_kplus1.at<double>(3, 0) = 0;                     // Velocity in Y
  x_kplus1.at<double>(4, 0) = 0.;                     // Acceleration in X
  x_kplus1.at<double>(5, 0) = 0.;                     // Acceleration in Y
  x_kplus1.at<double>(6, 0) = x_k.at<double>(6, 0);   // Position in Z
  x_kplus1.at<double>(7, 0) = x_k.at<double>(7, 0);   // Length
  x_kplus1.at<double>(8, 0) = x_k.at<double>(8, 0);   // Width
  x_kplus1.at<double>(9, 0) = x_k.at<double>(9, 0);   // Height
  x_kplus1.at<double>(10, 0) = x_k.at<double>(10, 0); // Yaw
  x_kplus1.at<double>(11, 0) = 0.;                    // Yaw Rate

  x_kplus1 += vk; // additive process noise
}

void CPModel::measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k)
{
  z_k.at<double>(0, 0) = x_k.at<double>(0, 0);  // Position in X
  z_k.at<double>(1, 0) = x_k.at<double>(1, 0);  // Position in Y
  z_k.at<double>(2, 0) = x_k.at<double>(6, 0);  // Position in Z
  z_k.at<double>(3, 0) = x_k.at<double>(7, 0);  // Length
  z_k.at<double>(4, 0) = x_k.at<double>(8, 0);  // Width
  z_k.at<double>(5, 0) = x_k.at<double>(9, 0);  // Height
  z_k.at<double>(6, 0) = x_k.at<double>(10, 0); // Yaw
  z_k += n_k;                                   // additive measurement noise
}
} // namespace tracking
} // namespace rv
