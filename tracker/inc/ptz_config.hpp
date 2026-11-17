// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <filesystem>
#include <string>
#include <string_view>
#include <unordered_map>

namespace tracker::ptz {

/// source_id (Manager camera UID) -> resolver_id
using Assignments = std::unordered_map<std::string, std::string>;

/**
 * @brief Validate a parsed assignment manifest (positioning_assignments.parse_assignments).
 *
 * Keys starting with `$` are comments. Every other entry must map a source_id to a
 * resolver_id, each a non-empty MQTT topic segment of at most 256 characters without
 * `/`, `+`, `#`, or NUL.
 *
 * @throws std::runtime_error for a non-object manifest or an invalid entry
 */
[[nodiscard]] Assignments parseAssignments(std::string_view json_text);

/// @throws std::runtime_error when the file is unreadable or invalid
[[nodiscard]] Assignments loadAssignments(const std::filesystem::path& path);

} // namespace tracker::ptz
