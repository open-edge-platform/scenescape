// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "rv/tracking/TrackedObject.hpp"

namespace rv {
namespace tracking {
namespace metadata_fusion {

inline constexpr char ValuePrefix[] = "metadata.";
inline constexpr char ConfidencePrefix[] = "metadata_confidence.";
inline constexpr char ProvenancePrefix[] = "metadata_provenance.";
inline constexpr char TransientPrefix[] = "metadata_transient.";

/// Prefer confidence, then later camera order; missing confidence loses to present confidence.
bool shouldReplace(bool winnerExists,
                   const std::optional<double> &candidateConfidence,
                   size_t candidateCameraIndex,
                   const std::optional<double> &winnerConfidence,
                   size_t winnerCameraIndex);

void fuseMetadata(const std::vector<std::pair<size_t, size_t>> &matches,
                  const std::vector<std::vector<TrackedObject>> &objectsPerCamera,
                  TrackedObject &measurement);
void mergeHistoricalMetadata(const TrackedObject &track, TrackedObject &measurement);

} // namespace metadata_fusion
} // namespace tracking
} // namespace rv