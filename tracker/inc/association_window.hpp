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
 * Position Mahalanobis → χ² (df=3) ellipse of the XY block of S_pred, with each semi-axis
 * clipped to max_radius_m so the drawn region stays inside the hard association ceiling.
 * Matching gates in 3D (df=3); the published window is the XY projection of that gate.
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
    const double s00 = track.predictedMeasurementCov(0, 0);
    const double s01 = track.predictedMeasurementCov(0, 1);
    const double s11 = track.predictedMeasurementCov(1, 1);

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
    // An ellipse with both semi-axes ≤ R lies inside the disk of radius R used as the hard gate.
    window.semi_major_m = std::min(std::sqrt(chi2 * lambda_major), config.max_radius_m);
    window.semi_minor_m = std::min(std::sqrt(chi2 * lambda_minor), config.max_radius_m);
    window.angle_rad = std::atan2(vy, vx);
    return window;
}

} // namespace tracker
