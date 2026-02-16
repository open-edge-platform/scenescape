// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <optional>
#include <string>

namespace tracker {

/**
 * @brief Parse ISO 8601 UTC timestamp to system_clock time_point.
 *
 * Expected format: "YYYY-MM-DDTHH:MM:SS[.fff]Z"
 *   - 'T' separator between date and time (required)
 *   - Optional fractional seconds (up to millisecond precision)
 *   - 'Z' suffix indicates UTC timezone (required)
 *
 * Uses sscanf for compact parsing and C++20 chrono calendar types for
 * portable date validation and UTC conversion.
 *
 * @param timestamp_iso ISO 8601 timestamp string
 * @return Parsed time_point with millisecond precision, or nullopt on failure
 */
std::optional<std::chrono::sys_time<std::chrono::milliseconds>>
parseTimestamp(const std::string& timestamp_iso);

/**
 * @brief Format system_clock time_point as ISO 8601 UTC string.
 *
 * Output format: "YYYY-MM-DDTHH:MM:SS.fffZ" (millisecond precision, UTC).
 *
 * @param tp Time point to format
 * @return ISO 8601 formatted string
 */
std::string formatTimestamp(std::chrono::system_clock::time_point tp);

} // namespace tracker
