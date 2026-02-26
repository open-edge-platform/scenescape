// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <string_view>

namespace tracker {

/**
 * @brief Validate that a string is safe for use in MQTT topic segments.
 *
 * MQTT topics have reserved characters that must not appear in topic segments:
 * - '/' (topic level separator)
 * - '+' (single-level wildcard)
 * - '#' (multi-level wildcard)
 * - '$' (system topic prefix)
 * - '\0' (null byte)
 *
 * This function uses a strict allowlist approach, permitting only:
 * - Alphanumeric characters (a-z, A-Z, 0-9)
 * - Hyphens (-)
 * - Underscores (_)
 * - Dots (.)
 *
 * @param segment The string to validate (typically a UID, camera_id, or category)
 * @return true if the segment contains only allowed characters and is non-empty
 * @return false if the segment is empty or contains disallowed characters
 *
 * @note This validation should be performed at subscription/worker creation time,
 *       not on every message, to avoid per-frame overhead.
 */
bool isValidTopicSegment(std::string_view segment);

} // namespace tracker
