// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <limits>
#include <memory>
#include <vector>

#include "rv/tracking/TrackedObject.hpp"

namespace apollo {
namespace perception {
namespace lidar {
class BaseBipartiteGraphMatcher;
}
}
}

namespace rv {
namespace tracking {

/// Association cost. The Controller and the Tracker Service use Euclidean or PositionMahalanobis (their
/// ``association.method``); the others are legacy, used only by MultipleObjectTracker's defaults and tests.
enum class DistanceType
{
  MultiClassEuclidean, ///< Legacy, MultipleObjectTracker's default: x/y distance scaled by the class conflict.
  Euclidean,           ///< x/y distance up to max_radius_m; ``association.method: euclidean`` and birth clustering.
  Mahalanobis,         ///< Legacy: 0.5 * sqrt(d^2) over the measurement vector; not chi-squared calibrated.
  MCEMahalanobis,      ///< Legacy: average of MultiClassEuclidean and Mahalanobis.
  PositionMahalanobis  ///< d^2 on the x/y block of S up to max_radius_m; ``association.method: position_mahalanobis``.
};

void match(const std::vector<TrackedObject> &tracks,
            const std::vector<TrackedObject> &measurements,
            std::vector<std::pair<size_t, size_t>> &assignments,
            std::vector<size_t> &unassignedTracks,
            std::vector<size_t> &unassignedMeasurements,
            const DistanceType &distanceType, double threshold,
            double max_radius_m = std::numeric_limits<double>::infinity());

} // namespace tracking
} // namespace rv
