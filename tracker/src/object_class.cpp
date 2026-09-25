// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "object_class.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>

#include <rapidjson/document.h>

namespace tracker {
namespace {

std::string toLower(std::string_view value) {
    std::string lower(value);
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return lower;
}

double readNumber(const rapidjson::Value& obj, const char* key, double fallback) {
    if (!obj.HasMember(key) || !obj[key].IsNumber()) {
        return fallback;
    }
    return obj[key].GetDouble();
}

int readShiftType(const rapidjson::Value& obj) {
    if (!obj.HasMember("shift_type") || !obj["shift_type"].IsNumber()) {
        return ObjectClassConfig::kShiftType1;
    }
    const int value = obj["shift_type"].GetInt();
    return value == ObjectClassConfig::kShiftType2 ? ObjectClassConfig::kShiftType2
                                                   : ObjectClassConfig::kShiftType1;
}

ObjectClassConfig parseAssetObject(const rapidjson::Value& asset) {
    ObjectClassConfig config;
    config.shift_type = readShiftType(asset);

    const double x_size = readNumber(asset, "x_size", 0.0);
    const double y_size = readNumber(asset, "y_size", 0.0);
    // Controller: mean([x_size, y_size]) / 2. Only pin a fixed offset when sizes
    // are configured; otherwise keep projected-bbox half-width behavior.
    if (x_size > 0.0 || y_size > 0.0) {
        config.footprint_half_m = (x_size + y_size) / 4.0;
    }
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
        out[toLower(asset["name"].GetString())] = parseAssetObject(asset);
    }
}

} // namespace

ObjectClassMap parseObjectClassesFromAssetsJson(std::string_view json) {
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
    const auto it = object_classes.find(toLower(category));
    if (it == object_classes.end()) {
        return {};
    }
    return it->second;
}

} // namespace tracker
