// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cstdint>
#include <format>
#include <random>

namespace tracker {

/**
 * @brief Generate a random UUID v4 string (RFC 4122).
 *
 * Format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
 * where version=4 (bits 48-51) and variant=10 (bits 64-65).
 *
 * Uses thread_local std::mt19937_64 seeded from std::random_device
 * for high-quality randomness without external dependencies.
 *
 * @return UUID v4 string in lowercase hexadecimal with hyphens
 */
inline std::string generate_uuid_v4() {
    thread_local std::mt19937_64 rng{std::random_device{}()};

    std::uniform_int_distribution<uint64_t> dist;
    uint64_t hi = dist(rng);
    uint64_t lo = dist(rng);

    // Set version to 4 (bits 12-15 of hi): appears as leading nibble of 3rd group
    hi = (hi & ~(0xFULL << 12)) | (0x4ULL << 12);

    // Set variant to 10 (bits 64-65 of UUID = bits 0-1 of lo high byte):
    // clear top 2 bits of lo, set 10
    lo = (lo & ~(0x3ULL << 62)) | (0x2ULL << 62);

    // Format: 8-4-4-4-12
    return std::format("{:08x}-{:04x}-{:04x}-{:04x}-{:012x}",
                       static_cast<uint32_t>(hi >> 32),            // 8 hex digits
                       static_cast<uint16_t>((hi >> 16) & 0xFFFF), // 4 hex digits
                       static_cast<uint16_t>(hi & 0xFFFF), // 4 hex digits (contains version)
                       static_cast<uint16_t>(lo >> 48),    // 4 hex digits (contains variant)
                       lo & 0x0000FFFFFFFFFFFFULL          // 12 hex digits
    );
}

} // namespace tracker
