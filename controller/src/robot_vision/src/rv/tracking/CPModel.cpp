// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <rv/tracking/CPModel.hpp>
#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {

void CPModel::stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1)
{
  cv::Mat vk = v_k.clone();

  (void)u_k;

  x_kplus1.at<double>(StateIndex::X, 0) = x_k.at<double>(StateIndex::X, 0);
  x_kplus1.at<double>(StateIndex::Y, 0) = x_k.at<double>(StateIndex::Y, 0);
  x_kplus1.at<double>(StateIndex::VX, 0) = 0;
  x_kplus1.at<double>(StateIndex::VY, 0) = 0;
  x_kplus1.at<double>(StateIndex::AX, 0) = 0.;
  x_kplus1.at<double>(StateIndex::AY, 0) = 0.;
  x_kplus1.at<double>(StateIndex::Z, 0) = x_k.at<double>(StateIndex::Z, 0);
  x_kplus1.at<double>(StateIndex::VZ, 0) = 0.;
  x_kplus1.at<double>(StateIndex::LENGTH, 0) = x_k.at<double>(StateIndex::LENGTH, 0);
  x_kplus1.at<double>(StateIndex::WIDTH, 0) = x_k.at<double>(StateIndex::WIDTH, 0);
  x_kplus1.at<double>(StateIndex::HEIGHT, 0) = x_k.at<double>(StateIndex::HEIGHT, 0);
  x_kplus1.at<double>(StateIndex::YAW, 0) = x_k.at<double>(StateIndex::YAW, 0);
  x_kplus1.at<double>(StateIndex::YAW_RATE, 0) = 0.;

  x_kplus1 += vk; // additive process noise
}

void CPModel::measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k)
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
