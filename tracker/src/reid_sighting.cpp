// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "reid_sighting.hpp"

#include <charconv>
#include <cmath>
#include <string_view>

#include "json_utils.hpp"
#include "logger.hpp"

namespace tracker {

void parse_detection_metadata(const rapidjson::Value& metadata, Detection& detection) {
    detection.reid_json.clear();
    detection.reid_confidence.reset();
    rapidjson::Document semantic;
    semantic.SetObject();
    auto& allocator = semantic.GetAllocator();
    for (const auto& member : metadata.GetObject()) {
        if (std::string_view(member.name.GetString(), member.name.GetStringLength()) != "reid") {
            semantic.AddMember(rapidjson::Value(member.name, allocator),
                               rapidjson::Value(member.value, allocator), allocator);
        }
    }
    const auto reid = metadata.FindMember("reid");
    if (reid != metadata.MemberEnd()) {
        const auto& value = reid->value;
        if (value.IsObject()) {
            detection.reid_json = detail::to_json_string(value);
            if (value.HasMember("confidence") && value["confidence"].IsNumber()) {
                detection.reid_confidence = value["confidence"].GetDouble();
            }
        } else if (value.IsArray() || value.IsString()) {
            detection.reid_json = "{\"embedding_vector\":" + detail::to_json_string(value) + "}";
        }
    }
    detection.metadata_json = detail::to_json_string(semantic);
}

void ReidSightingContext::tag(size_t detection_index,
                              std::unordered_map<std::string, std::string>& attributes) const {
    const auto& detection = batch.detections[detection_index];
    if (detection.reid_json.empty() || batch.camera_id.empty() || batch.timestamp_iso.empty() ||
        chunk_id.empty()) {
        return;
    }
    attributes[kReidValueKey] = chunk_id + ":" + std::to_string(index_offset + detection_index);
    attributes[kReidProvenanceKey] = chunk_id;
    attributes[kReidTransientKey] = "1";
    if (detection.reid_confidence && std::isfinite(*detection.reid_confidence)) {
        char buffer[32];
        const auto [end, error] =
            std::to_chars(buffer, buffer + sizeof(buffer), *detection.reid_confidence);
        if (error == std::errc{}) {
            attributes[kReidConfidenceKey] = std::string(buffer, end);
        }
    }
}

void ReidSightingIndex::reset(std::string chunk_id) {
    clear();
    chunk_id_ = std::move(chunk_id);
}

ReidSightingContext ReidSightingIndex::add_batch(const DetectionBatch& batch) {
    const auto offset = entries_.size();
    for (const auto& detection : batch.detections) {
        entries_.push_back({&batch, &detection});
    }
    return {batch, chunk_id_, offset};
}

std::string
ReidSightingIndex::take(const std::unordered_map<std::string, std::string>& attributes) {
    const auto token = attributes.find(kReidValueKey);
    const auto provenance = attributes.find(kReidProvenanceKey);
    if (token == attributes.end() || provenance == attributes.end() ||
        provenance->second != chunk_id_) {
        return {};
    }
    const std::string prefix = chunk_id_ + ":";
    const std::string_view value = token->second;
    size_t index = 0;
    if (!value.starts_with(prefix)) {
        LOG_WARN("Invalid current-chunk ReID sighting token");
        return {};
    }
    const auto [end, error] =
        std::from_chars(value.data() + prefix.size(), value.data() + value.size(), index);
    if (error != std::errc{} || end != value.data() + value.size() || index >= entries_.size()) {
        LOG_WARN("Invalid current-chunk ReID sighting index");
        return {};
    }
    auto& entry = entries_[index];
    if (!entry.detection) {
        return {};
    }
    const auto& detection = *entry.detection;
    const auto& batch = *entry.batch;
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    writer.StartObject();
    writer.Key("camera_id");
    writer.String(batch.camera_id.data(), static_cast<rapidjson::SizeType>(batch.camera_id.size()));
    writer.Key("timestamp");
    writer.String(batch.timestamp_iso.data(),
                  static_cast<rapidjson::SizeType>(batch.timestamp_iso.size()));
    writer.Key("bounding_box_px");
    writer.StartObject();
    writer.Key("x");
    writer.Double(detection.bounding_box_px.x);
    writer.Key("y");
    writer.Double(detection.bounding_box_px.y);
    writer.Key("width");
    writer.Double(detection.bounding_box_px.width);
    writer.Key("height");
    writer.Double(detection.bounding_box_px.height);
    writer.EndObject();
    writer.Key("reid");
    writer.RawValue(detection.reid_json.data(), detection.reid_json.size(), rapidjson::kObjectType);
    writer.EndObject();
    entry.detection = nullptr;
    return {buffer.GetString(), buffer.GetSize()};
}

void ReidSightingIndex::clear() {
    entries_.clear();
    chunk_id_.clear();
}

} // namespace tracker
