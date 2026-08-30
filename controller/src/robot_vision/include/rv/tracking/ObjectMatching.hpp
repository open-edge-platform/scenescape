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

enum class DistanceType
{
  MultiClassEuclidean,
  Euclidean,
  Mahalanobis,
  MCEMahalanobis,
  PositionMahalanobis
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
