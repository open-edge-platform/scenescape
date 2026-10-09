// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "association_config.hpp"

#include <cmath>
#include <optional>
#include <string>

#include <opencv2/core.hpp>
#include <rv/tracking/TrackedObject.hpp>
#include <rv/Utils.hpp>

namespace tracker {

/**
 * @brief Association gate geometry for UI visualization (MQTT association_window).
 *
 * Euclidean → circle of radius max_radius_m.
 * Position Mahalanobis → χ² ellipse of the XY block of S_pred.
 */
struct AssociationWindow {
    std::string method;
    std::string shape; ///< "circle" or "ellipse"
    std::optional<double> radius_m;
    std::optional<double> semi_major_m;
    std::optional<double> semi_minor_m;
    std::optional<double> angle_rad;
};

inline AssociationWindow buildAssociationWindow(const AssociationConfig& config,
                                                const rv::tracking::TrackedObject& track) {
    AssociationWindow window;
    window.method = associationMethodToString(config.method);

    if (config.method == AssociationMethod::Euclidean) {
        window.shape = "circle";
        window.radius_m = config.max_radius_m;
        return window;
    }

    const double chi2 = config.chi2Threshold();
    const double s00 = track.predictedMeasurementCov.at<double>(0, 0);
    const double s01 = track.predictedMeasurementCov.at<double>(0, 1);
    const double s11 = track.predictedMeasurementCov.at<double>(1, 1);

    cv::Matx22d s_xy(s00, s01, s01, s11);
    cv::Mat eigenvalues;
    cv::Mat eigenvectors;
    cv::eigen(cv::Mat(s_xy), eigenvalues, eigenvectors);

    // cv::eigen returns eigenvalues in descending order; row 0 is the major axis.
    const double lambda_major = std::max(eigenvalues.at<double>(0), 0.0);
    const double lambda_minor = std::max(eigenvalues.at<double>(1), 0.0);
    const double vx = eigenvectors.at<double>(0, 0);
    const double vy = eigenvectors.at<double>(0, 1);

    window.shape = "ellipse";
    window.semi_major_m = std::sqrt(chi2 * lambda_major);
    window.semi_minor_m = std::sqrt(chi2 * lambda_minor);
    window.angle_rad = std::atan2(vy, vx);
    return window;
}

} // namespace tracker
