// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <optional>
#include <string>

namespace tracker {

/**
 * @brief Scene configuration source type.
 */
enum class SceneSource {
    File, ///< Load scenes from external JSON file (scenes.file_path)
    Api   ///< Fetch scenes from Manager REST API
};

/**
 * @brief Scene configuration source settings.
 */
struct ScenesConfig {
    SceneSource source = SceneSource::Api; ///< Scene source type
    std::optional<std::string> file_path;  ///< Path to scene file (when source=File)
};

} // namespace tracker
