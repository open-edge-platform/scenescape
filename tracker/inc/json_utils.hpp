// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <optional>
#include <stdexcept>
#include <string>

#include <rapidjson/pointer.h>
#include <rapidjson/rapidjson.h>

namespace tracker::detail {

/**
 * @brief Get optional value from JSON using pointer path.
 * @tparam T Expected value type (std::string or double)
 * @param doc The JSON value to query
 * @param pointer JSON pointer path (e.g., "/intrinsics/fx")
 * @return Optional containing value if found and correct type, nullopt otherwise
 */
template <typename T>
std::optional<T> get_value(const rapidjson::Value& doc, const char* pointer) {
    rapidjson::Pointer ptr(pointer);
    if (auto* val = ptr.Get(doc)) {
        if constexpr (std::is_same_v<T, std::string>) {
            if (val->IsString()) {
                return std::string(val->GetString());
            }
        } else if constexpr (std::is_same_v<T, double>) {
            if (val->IsNumber()) {
                return val->GetDouble();
            }
        }
    }
    return std::nullopt;
}

/**
 * @brief Get required value from JSON using pointer path.
 * @tparam T Expected value type (std::string or double)
 * @param doc The JSON value to query
 * @param pointer JSON pointer path (e.g., "/uid")
 * @param context Context string for error messages (e.g., "scene", "camera")
 * @return Value if found and correct type
 * @throws std::runtime_error if value missing or wrong type
 */
template <typename T>
T require_value(const rapidjson::Value& doc, const char* pointer, const char* context) {
    auto result = get_value<T>(doc, pointer);
    if (!result.has_value()) {
        throw std::runtime_error(std::string(context) + " missing required '" + (pointer + 1) +
                                 "' field");
    }
    return result.value();
}

} // namespace tracker::detail
