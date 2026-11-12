// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string_view>

namespace tracker::ptz {

inline constexpr int64_t kNsPerS = 1'000'000'000;

/**
 * @brief Parse an ISO-8601 timestamp with an explicit timezone into integer ns since the epoch.
 *
 * Accepts `YYYY-MM-DD[T| ]HH:MM:SS[.fraction](Z|z|+HH:MM|-HH:MM)`. The fraction is truncated
 * to microseconds, matching `scene_common.positioning_dwell.parse_timestamp_ns`, so boundary
 * comparisons are identical in the Controller and the Tracker.
 *
 * @return Nanoseconds since the Unix epoch, or nullopt when the text is not a valid timestamp
 */
[[nodiscard]] std::optional<int64_t> parseIsoTimestampNs(std::string_view text);

/**
 * @brief Seconds to integer ns, rounding half to even like Python's `int(round(x * 1e9))`.
 */
[[nodiscard]] int64_t secondsToNs(double seconds);

[[nodiscard]] inline int64_t toNs(std::chrono::system_clock::time_point time_point) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(time_point.time_since_epoch())
        .count();
}

} // namespace tracker::ptz
