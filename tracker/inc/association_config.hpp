// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <rv/Utils.hpp>
#include <rv/tracking/ObjectMatching.hpp>

#include <stdexcept>
#include <string>

namespace tracker {

constexpr double kDefaultAssociationGateProbability = 0.99;
/// Legacy Euclidean association / birth-cluster meter gate (rollback).
constexpr double kDefaultAssociationMaxRadiusM = 2.0;
/// Default when association.max_radius_m is omitted (Mahalanobis ceiling).
constexpr double kDefaultAssociationMaxRadiusCeilingM = 10.0;

enum class AssociationMethod { Euclidean, PositionMahalanobis };

/**
 * @brief Data association configuration (ADR-0017 Phase 1).
 */
struct AssociationConfig {
    AssociationMethod method = AssociationMethod::PositionMahalanobis;
    double gate_probability = kDefaultAssociationGateProbability;
    /// Euclidean: association distance threshold (m). Mahalanobis: hard ceiling (m).
    double max_radius_m = kDefaultAssociationMaxRadiusCeilingM;

    [[nodiscard]] double chi2Threshold() const {
        return rv::chi2Threshold(gate_probability, 2);
    }

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

} // namespace tracker
