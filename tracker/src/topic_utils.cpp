// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "topic_utils.hpp"

#include <cctype>

namespace tracker {

bool isValidTopicSegment(std::string_view segment) {
    if (segment.empty()) {
        return false;
    }

    for (char c : segment) {
        // Allow: alphanumeric, hyphen, underscore, dot
        if (std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.') {
            continue;
        }
        // Reject all other characters (including /, +, #, $, null, spaces, etc.)
        return false;
    }

    return true;
}

} // namespace tracker
