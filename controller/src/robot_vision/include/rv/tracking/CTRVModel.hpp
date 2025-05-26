// ----------------- BEGIN LICENSE BLOCK ---------------------------------
//
// INTEL CONFIDENTIAL
//
// Copyright (c) 2019-2023 Intel Corporation
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
