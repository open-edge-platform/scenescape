// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scene_loader.hpp"

#include <array>
#include <cstddef>
#include <optional>
#include <string_view>
#include <utility>

namespace tracker {

std::array<double, 3> convertLlaToEcef(const std::array<double, 3>& lla);
TrsMatrix calculateTrsLocalToEcef(const std::array<std::array<double, 3>, 4>& map_corners,
                                  const std::array<std::array<double, 3>, 4>& lla_corners,
                                  double z_shift = 2.0);
bool isSupportedImageResource(std::string_view resource);
std::optional<std::pair<size_t, size_t>> imageDimensions(std::string_view data);
bool calculateSceneTrsFromImage(Scene& scene, std::string_view image_data);

} // namespace tracker