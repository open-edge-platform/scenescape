// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "observation_processor.hpp"

#include "json_utils.hpp"

#include <charconv>
#include <stdexcept>

#include <omp.h>
#include <rapidjson/document.h>
#include <rv/tracking/MetadataFusion.hpp>

namespace tracker {

namespace {

constexpr int kMinIterationsForOpenMpParallelism = 32;

void addMetadataAttributes(const Detection& detection,
                           std::unordered_map<std::string, std::string>& attributes) {
    rapidjson::Document metadata;
    if (detection.metadata_json.find('\0') != std::string::npos ||
        metadata.Parse(detection.metadata_json.data(), detection.metadata_json.size())
            .HasParseError() ||
        !metadata.IsObject()) {
        return;
    }

    for (auto member = metadata.MemberBegin(); member != metadata.MemberEnd(); ++member) {
        const std::string field(member->name.GetString(), member->name.GetStringLength());
        attributes[std::string(rv::tracking::metadata_fusion::ValuePrefix) + field] =
            detail::to_json_string(member->value);

        if (!member->value.IsObject() || !member->value.HasMember("confidence") ||
            !member->value["confidence"].IsNumber()) {
            continue;
        }

        char confidence_buffer[32];
        const auto confidence = member->value["confidence"].GetDouble();
        auto [ptr, ec] = std::to_chars(confidence_buffer,
                                       confidence_buffer + sizeof(confidence_buffer), confidence);
        if (ec == std::errc{}) {
            attributes[std::string(rv::tracking::metadata_fusion::ConfidencePrefix) + field] =
                std::string(confidence_buffer, ptr);
        }
    }
}

void addDetectionAttributes(const Detection& detection, rv::tracking::TrackedObject& object) {
    if (!detection.metadata_json.empty()) {
        addMetadataAttributes(detection, object.attributes);
    }
    if (detection.confidence.has_value()) {
        char buffer[32];
        auto [ptr, ec] = std::to_chars(buffer, buffer + sizeof(buffer), *detection.confidence);
        if (ec == std::errc{}) {
            object.attributes["confidence"] = std::string(buffer, ptr);
        }
    }
}

} // namespace

CameraModelProcessor::CameraModelProcessor(const std::unordered_map<std::string, Camera>& cameras,
                                           const ObjectClassConfig& object_class) {
    for (const auto& [camera_id, camera] : cameras) {
        transformers_.emplace(camera_id, CoordinateTransformer(camera.intrinsics, camera.extrinsics,
                                                               object_class.shift_type,
                                                               object_class.footprint_half));
    }
}

std::vector<std::optional<ProcessedObservations>>
CameraModelProcessor::process(std::span<const DetectionBatch> batches) {
    std::vector<std::optional<ProcessedObservations>> processed;
    processed.reserve(batches.size());
    for (const auto& batch : batches) {
        const auto transformer = transformers_.find(batch.camera_id);
        if (transformer == transformers_.end()) {
            processed.emplace_back();
            continue;
        }
        processed.emplace_back(transformer->second.transformDetections(batch.detections));
    }
    return processed;
}

std::vector<rv::tracking::TrackedObject>
toTrackerInputs(std::span<const Detection> detections, ProcessedObservations processed,
                const std::optional<ReidSightingContext>& sightings) {
    const auto n = detections.size();
    if (!processed.covers(n)) {
        throw std::invalid_argument("Processed geometry must have one entry per detection");
    }
    if (sightings && (sightings->batch.detections.size() != n ||
                      sightings->batch.detections.data() != detections.data())) {
        throw std::invalid_argument("ReID sighting context must reference the detection span");
    }

#pragma omp parallel for schedule(static) if (n >= kMinIterationsForOpenMpParallelism)
    for (int i = 0; i < static_cast<int>(n); ++i) {
        const auto index = static_cast<size_t>(i);
        if (!processed.has_geometry[index]) {
            continue;
        }
        const auto& detection = detections[index];
        auto& object = processed.objects[index];
        object.id = detection.id.value_or(rv::tracking::InvalidObjectId);
        addDetectionAttributes(detection, object);
        // A sighting records the detection's pixel box, so translation detections get none.
        if (sightings && !detection.translation) {
            sightings->tag(index, object.attributes);
        }
    }

    // Compact in place: remove detections without geometry, preserving order.
    size_t write = 0;
    for (size_t read = 0; read < n; ++read) {
        if (processed.has_geometry[read]) {
            if (write != read) {
                processed.objects[write] = std::move(processed.objects[read]);
            }
            ++write;
        }
    }
    processed.objects.resize(write);
    return std::move(processed.objects);
}

} // namespace tracker
