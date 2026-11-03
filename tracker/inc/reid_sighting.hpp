// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstddef>
#include <string>
#include <unordered_map>
#include <vector>

#include <rapidjson/document.h>
#include <rv/tracking/MetadataFusion.hpp>

#include "tracking_types.hpp"

namespace tracker {

inline const std::string kReidValueKey =
    std::string(rv::tracking::metadata_fusion::ValuePrefix) + "reid";
inline const std::string kReidConfidenceKey =
    std::string(rv::tracking::metadata_fusion::ConfidencePrefix) + "reid";
inline const std::string kReidProvenanceKey =
    std::string(rv::tracking::metadata_fusion::ProvenancePrefix) + "reid";
inline const std::string kReidTransientKey =
    std::string(rv::tracking::metadata_fusion::TransientPrefix) + "reid";

void parse_detection_metadata(const rapidjson::Value& metadata, Detection& detection);

struct ReidSightingContext {
    const DetectionBatch& batch;
    const std::string& chunk_id;
    size_t index_offset;

    /// Called in parallel for a pixel-box detection in the validated batch span.
    void tag(size_t detection_index,
             std::unordered_map<std::string, std::string>& attributes) const;
};

/// References are valid only until the owning process_chunk's Chunk is destroyed.
class ReidSightingIndex {
public:
    void reset(std::string chunk_id);
    ReidSightingContext add_batch(const DetectionBatch& batch);
    std::string take(const std::unordered_map<std::string, std::string>& attributes);
    void clear();

private:
    struct Entry {
        const DetectionBatch* batch;
        const Detection* detection;
    };
    std::string chunk_id_;
    std::vector<Entry> entries_;
};

} // namespace tracker
