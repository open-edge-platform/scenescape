// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "object_class.hpp"

#include <stdexcept>

#include <rapidjson/document.h>

namespace tracker {
namespace {

// Controller moving_object.DEFAULT_EDGE_LENGTH
constexpr double kDefaultEdgeLength = 1.0;

double readNumber(const rapidjson::Value& obj, const char* key, double fallback) {
    if (!obj.HasMember(key) || !obj[key].IsNumber()) {
        return fallback;
    }
    return obj[key].GetDouble();
}

ObjectClassConfig parseAssetObject(const rapidjson::Value& asset) {
    ObjectClassConfig config;
    // Controller camLoc: only shift_type == 2 (2.0 too) selects TYPE_2.
    config.shift_type = readNumber(asset, "shift_type", ObjectClassConfig::kShiftType1) ==
                                ObjectClassConfig::kShiftType2
                            ? ObjectClassConfig::kShiftType2
                            : ObjectClassConfig::kShiftType1;

    // Controller: mean([x_size, y_size]) / 2, zero sizes included.
    config.footprint_half_m = (readNumber(asset, "x_size", kDefaultEdgeLength) +
                               readNumber(asset, "y_size", kDefaultEdgeLength)) /
                              4.0;
    return config;
}

void ingestResultsArray(const rapidjson::Value& results, ObjectClassMap& out) {
    if (!results.IsArray()) {
        return;
    }
    for (const auto& asset : results.GetArray()) {
        if (!asset.IsObject() || !asset.HasMember("name") || !asset["name"].IsString()) {
            continue;
        }
        out[asset["name"].GetString()] = parseAssetObject(asset);
    }
}

} // namespace

ObjectClassMap parseObjectClassesFromAssets(std::string_view json) {
    rapidjson::Document doc;
    if (doc.Parse(json.data(), json.size()).HasParseError()) {
        throw std::runtime_error("Failed to parse Manager assets JSON");
    }

    ObjectClassMap object_classes;
    if (doc.IsObject() && doc.HasMember("results")) {
        ingestResultsArray(doc["results"], object_classes);
    } else if (doc.IsArray()) {
        ingestResultsArray(doc, object_classes);
    } else {
        throw std::runtime_error("Manager assets JSON missing 'results' array");
    }
    return object_classes;
}

ObjectClassConfig lookupObjectClass(const ObjectClassMap& object_classes,
                                    std::string_view category) {
    const auto it = object_classes.find(std::string(category));
    if (it == object_classes.end()) {
        return {};
    }
    return it->second;
}

} // namespace tracker
