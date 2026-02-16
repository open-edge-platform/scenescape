// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "uuid.hpp"

#include <cstdint>
#include <functional>
#include <span>
#include <unordered_map>

namespace tracker {

using UuidGenerator = std::function<std::string()>;

/**
 * @brief Update the RobotVision ID -> UUID mapping for active tracks.
 *
 * Builds a new map containing only the given active IDs.
 * Existing UUIDs are preserved; new IDs get fresh UUIDs from the generator.
 *
 * @param old_map Previous mapping (may contain stale entries)
 * @param active_ids Currently active RobotVision track IDs
 * @param gen UUID generator function (defaults to generate_uuid_v4)
 * @return New map with only active IDs mapped to UUIDs
 */
inline std::unordered_map<int32_t, std::string>
update_id_map(const std::unordered_map<int32_t, std::string>& old_map,
              std::span<const int32_t> active_ids, const UuidGenerator& gen = generate_uuid_v4) {
    std::unordered_map<int32_t, std::string> new_map;
    new_map.reserve(active_ids.size());
    for (const auto id : active_ids) {
        if (!new_map.contains(id)) {
            new_map.emplace(id, old_map.contains(id) ? old_map.at(id) : gen());
        }
    }
    return new_map;
}

} // namespace tracker
