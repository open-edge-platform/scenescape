// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scene_loader.hpp"

#include <optional>
#include <string_view>
#include <utility>

namespace tracker {

bool isSupportedImageResource(std::string_view resource);
std::optional<std::pair<size_t, size_t>> imageDimensions(std::string_view data);
bool calculateSceneTrsFromImage(Scene& scene, std::string_view image_data);

} // namespace tracker