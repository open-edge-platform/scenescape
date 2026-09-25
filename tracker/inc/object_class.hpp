// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>

namespace tracker {

/**
 * @brief Per-category projection settings from Manager `/api/v1/assets`.
 *
 * Mirrors Controller `Tracking.updateObjectClasses` / `createObject` fields used
 * for world projection: `shift_type` and footprint sizes.
 */
struct ObjectClassConfig {
    static constexpr int kShiftType1 = 1;
    static constexpr int kShiftType2 = 2;

    int shift_type = kShiftType1;
    /// Camloc bearing offset half-size in metres (Controller mean([x,y])/2).
    /// Empty → fall back to half the projected bbox width.
    std::optional<double> footprint_half_m;
};

/// Category name (lowercased) → projection config.
using ObjectClassMap = std::unordered_map<std::string, ObjectClassConfig>;

/**
 * @brief Parse Manager assets list JSON into an object-class map.
 *
 * Expects a Manager list payload: `{"results":[{"name","shift_type","x_size","y_size",...},...]}`
 * or a bare JSON array of asset objects. Entries without `name` are skipped.
 */
ObjectClassMap parseObjectClassesFromAssetsJson(std::string_view json);

/**
 * @brief Look up projection config for a detection category (case-insensitive).
 *
 * Returns TYPE_1 with no fixed footprint when the category is unknown.
 */
ObjectClassConfig lookupObjectClass(const ObjectClassMap& object_classes,
                                    std::string_view category);

} // namespace tracker
