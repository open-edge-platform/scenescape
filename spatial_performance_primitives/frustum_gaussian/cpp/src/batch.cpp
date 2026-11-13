// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// TBB compatibility shim: support both oneTBB (2021+) and classic TBB.
#if __has_include(<oneapi/tbb/parallel_for.h>)
#  include <oneapi/tbb/parallel_for.h>
#  include <oneapi/tbb/blocked_range.h>
namespace tbb__ = oneapi::tbb;
#else
#  include <tbb/parallel_for.h>
#  include <tbb/blocked_range.h>
namespace tbb__ = tbb;
#endif

#include "frustum_gaussian/frustum.hpp"

namespace fg {

void project_frustum_batch(const BoundingBox*       boxes,
                           const Intrinsics&        K,
                           const ShapePrior*        priors,
                           const DetectorNoise&     noise,
                           FrustumObservation*      out,
                           const size_t             n,
                           const float*             ranges,
                           const RangeSensorConfig& sensor) noexcept {
    if (n == 0) return;

    // For very small batches (< 16 detections) the TBB overhead exceeds the
    // benefit — run serially.
    constexpr size_t PARALLEL_THRESHOLD = 64;

    auto process_one = [&](size_t i) {
        if (ranges) {
            out[i] = project_frustum(boxes[i], K, priors[i], noise,
                                     ranges[i], sensor);
        } else {
            out[i] = project_frustum(boxes[i], K, priors[i], noise);
        }
    };

    if (n < PARALLEL_THRESHOLD) {
        for (size_t i = 0; i < n; ++i)
            process_one(i);
        return;
    }

    // TBB blocked_range parallelises over detections.  Each detection is an
    // independent ≈4 µs chunk of work — a grain size of 8 keeps scheduler
    // overhead below 5% while giving good load balance for N up to ~1000.
    constexpr size_t GRAIN = 8;

    tbb__::parallel_for(
        tbb__::blocked_range<size_t>(0, n, GRAIN),
        [&](const tbb__::blocked_range<size_t>& r) {
            for (size_t i = r.begin(); i < r.end(); ++i)
                process_one(i);
        });
}

} // namespace fg
