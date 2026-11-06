// SPDX-FileCopyrightText: (C) 2019 - 2026 Intel Corporation
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
/// ``association.method``) and EuclideanBirth for birth clustering; the others are legacy, used only by
/// MultipleObjectTracker's defaults and tests.
enum class DistanceType
{
  MultiClassEuclidean, ///< Legacy, MultipleObjectTracker's default: x/y/z distance scaled by the class conflict.
  Euclidean,           ///< x/y/z distance up to max_radius_m; ``association.method: euclidean``.
  Mahalanobis,         ///< Legacy: 0.5 * sqrt(d^2) over the measurement vector; not chi-squared calibrated.
  MCEMahalanobis,      ///< Legacy: average of MultiClassEuclidean and Mahalanobis.
  PositionMahalanobis, ///< d^2 on the x/y/z block of S up to max_radius_m; ``association.method: position_mahalanobis``.
  EuclideanBirth       ///< Birth clustering: x/y distance, x/y/z when both detections have ``zMeasured``.
};

/// Assigns measurements to tracks on costs below threshold, which is capped at 1000, the cost of a pair beyond
/// max_radius_m or with a degenerate covariance.
void match(const std::vector<TrackedObject> &tracks,
            const std::vector<TrackedObject> &measurements,
            std::vector<std::pair<size_t, size_t>> &assignments,
            std::vector<size_t> &unassignedTracks,
            std::vector<size_t> &unassignedMeasurements,
            const DistanceType &distanceType, double threshold,
            double max_radius_m = std::numeric_limits<double>::infinity());

} // namespace tracking
} // namespace rv
