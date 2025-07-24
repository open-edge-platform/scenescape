// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <opencv2/imgproc/imgproc.hpp>
#include <opencv2/tracking/kalman_filters.hpp>

namespace rv {
namespace tracking {

/**
 * @brief CTRVModel: Implements a cv::detail::tracking::UkfSystemModel
 *
 * The CTRVModel is a UkfSystemModel which overrides the state conversion and measurement functions
 * The CTRVModel refers to the Constant turn rate and velocity model which is commonly
 * used in the literature to track the state of a moving vehicle.
 *
 * See "Comparison and evaluation of advanced motion models for vehicle tracking".
 */
class CTRVModel : public cv::detail::tracking::UkfSystemModel
{
public:
  /**
   * @brief State transition function for the Constant turn rate and velocity model
   */
  void stateConversionFunction(const cv::Mat &x_k, const cv::Mat &u_k, const cv::Mat &v_k, cv::Mat &x_kplus1) override;

  /**
    * @brief State measurement function for the Constant turn rate and velocity model
    */
  void measurementFunction(const cv::Mat &x_k, const cv::Mat &n_k, cv::Mat &z_k) override;
};
} // namespace tracking
} // namespace rv
