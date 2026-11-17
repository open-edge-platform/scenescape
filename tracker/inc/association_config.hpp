// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/Utils.hpp>

#include <stdexcept>
#include <string>

namespace tracker {

constexpr double kDefaultAssociationGateProbability = 0.99;
/// Default association distance (m) for euclidean, the legacy meter gate.
constexpr double kDefaultAssociationMaxRadiusM = 2.0;
/// Default hard ceiling (m) for position_mahalanobis.
constexpr double kDefaultAssociationMaxRadiusCeilingM = 10.0;

enum class AssociationMethod {
    Euclidean,
    PositionMahalanobis
};

/// max_radius_m when the config omits it: the legacy 2 m gate for euclidean, the 10 m ceiling
/// otherwise.
[[nodiscard]] constexpr double defaultMaxRadiusM(AssociationMethod method) {
    return method == AssociationMethod::Euclidean ? kDefaultAssociationMaxRadiusM
                                                  : kDefaultAssociationMaxRadiusCeilingM;
}

/**
 * @brief Kalman filter settings shared with the Scene Controller (global, read at startup).
 *
 * The defaults are robot_vision's production constants, so a config without a filter block runs the
 * production filter bit for bit.
 */
struct FilterConfig {
    /// Process noise scale q: scales all process noise (see the robot_vision README).
    double process_noise = rv::tracking::kProductionProcessNoise;
    /// Measurement noise r: R of every measured component and the initial variance of the measured
    /// states; the default R of detections without their own.
    double base_measurement_noise = rv::tracking::kProductionMeasurementNoise;
    /// P0: the initial velocity variance (also caps the initial acceleration, yaw and yaw-rate
    /// variances).
    double init_state_covariance = rv::tracking::kProductionInitStateCovariance;
};

/**
 * @brief Data association configuration (ADR-0019 Phase 1).
 */
struct AssociationConfig {
    AssociationMethod method = AssociationMethod::PositionMahalanobis;
    double gate_probability = kDefaultAssociationGateProbability;
    /// Euclidean: association distance threshold (m). Mahalanobis: hard ceiling (m).
    double max_radius_m = kDefaultAssociationMaxRadiusCeilingM;
    /// Euclidean radius (m) that groups new detections of one object seen by different cameras;
    /// independent of method and max_radius_m.
    double birth_cluster_radius_m = rv::tracking::kDefaultBirthClusterRadiusM;

    /// χ² gate for (x,y,z) PositionMahalanobis matching (3 DOF).
    [[nodiscard]] double chi2Threshold() const { return rv::chi2Threshold(gate_probability, 3); }

    [[nodiscard]] rv::tracking::DistanceType distanceType() const {
        switch (method) {
            case AssociationMethod::PositionMahalanobis:
                return rv::tracking::DistanceType::PositionMahalanobis;
            case AssociationMethod::Euclidean:
            default:
                return rv::tracking::DistanceType::Euclidean;
        }
    }

    [[nodiscard]] double costThreshold() const {
        if (method == AssociationMethod::PositionMahalanobis) {
            return chi2Threshold();
        }
        return max_radius_m;
    }
};

inline AssociationMethod parseAssociationMethod(const std::string& method) {
    if (method == "position_mahalanobis") {
        return AssociationMethod::PositionMahalanobis;
    }
    if (method == "euclidean") {
        return AssociationMethod::Euclidean;
    }
    throw std::runtime_error("Invalid association method: " + method +
                             " (expected 'euclidean' or 'position_mahalanobis')");
}

inline std::string associationMethodToString(AssociationMethod method) {
    switch (method) {
        case AssociationMethod::Euclidean:
            return "euclidean";
        case AssociationMethod::PositionMahalanobis:
        default:
            return "position_mahalanobis";
    }
}

} // namespace tracker
