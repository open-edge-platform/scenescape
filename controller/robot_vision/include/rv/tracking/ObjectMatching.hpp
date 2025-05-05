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
  MCEMahalanobis
};

void match(const std::vector<TrackedObject> &tracks,
            const std::vector<TrackedObject> &measurements,
            std::vector<std::pair<size_t, size_t>> &assignments,
            std::vector<size_t> &unassignedTracks,
            std::vector<size_t> &unassignedMeasurements,
            const DistanceType &distanceType, double threshold);

} // namespace tracking
} // namespace rv
