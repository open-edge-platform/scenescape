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
 * for world projection (`shift_type`, footprint sizes) plus `rotation_from_velocity`.
 */
struct ObjectClassConfig {
    static constexpr int kShiftType1 = 1;
    static constexpr int kShiftType2 = 2;

    int shift_type = kShiftType1;
    /// Camloc bearing offset half-size in metres (Controller mean([x,y])/2).
    /// Empty (category has no asset) → fall back to half the projected bbox width.
    std::optional<double> footprint_half;
    /// Derive track orientation from velocity heading (with hysteresis).
    bool rotation_from_velocity = false;
};

/// Asset name → projection config.
using ObjectClassMap = std::unordered_map<std::string, ObjectClassConfig>;

/**
 * @brief Parse Manager assets list JSON into an object-class map.
 *
 * Expects a Manager list payload:
 * `{"results":[{"name","shift_type","x_size","y_size","rotation_from_velocity",...},...]}`
 * or a bare JSON array of asset objects. Entries without `name` are skipped.
 */
ObjectClassMap parseObjectClassesFromAssets(std::string_view json);

/**
 * @brief Look up projection config for a detection category (exact match).
 *
 * Returns TYPE_1 with no fixed footprint and velocity rotation disabled when the
 * category is unknown.
 */
ObjectClassConfig lookupObjectClass(const ObjectClassMap& object_classes,
                                    std::string_view category);

} // namespace tracker
