// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_geospatial.hpp"

#include "external_source.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace tracker {

namespace {

uint16_t readBigEndian16(std::string_view data, size_t offset) {
    return static_cast<uint16_t>((static_cast<uint8_t>(data[offset]) << 8U) |
                                 static_cast<uint8_t>(data[offset + 1]));
}

uint32_t readBigEndian32(std::string_view data, size_t offset) {
    return (static_cast<uint32_t>(static_cast<uint8_t>(data[offset])) << 24U) |
           (static_cast<uint32_t>(static_cast<uint8_t>(data[offset + 1])) << 16U) |
           (static_cast<uint32_t>(static_cast<uint8_t>(data[offset + 2])) << 8U) |
           static_cast<uint32_t>(static_cast<uint8_t>(data[offset + 3]));
}

bool isJpegStartOfFrame(uint8_t marker) {
    return (marker >= 0xC0 && marker <= 0xC3) || (marker >= 0xC5 && marker <= 0xC7) ||
           (marker >= 0xC9 && marker <= 0xCB) || (marker >= 0xCD && marker <= 0xCF);
}

} // namespace

bool isSupportedImageResource(std::string_view resource) {
    const size_t query = resource.find_first_of("?#");
    const auto path = resource.substr(0, query);
    const size_t dot = path.find_last_of('.');
    if (dot == std::string_view::npos) {
        return false;
    }
    std::string extension(path.substr(dot));
    std::transform(
        extension.begin(), extension.end(), extension.begin(),
        [](unsigned char character) { return static_cast<char>(std::tolower(character)); });
    return extension == ".png" || extension == ".jpg" || extension == ".jpeg";
}

std::optional<std::pair<size_t, size_t>> imageDimensions(std::string_view data) {
    constexpr std::array<uint8_t, 8> png_signature = {0x89, 0x50, 0x4E, 0x47,
                                                      0x0D, 0x0A, 0x1A, 0x0A};
    if (data.size() >= 24 && std::equal(png_signature.begin(), png_signature.end(), data.begin(),
                                        [](uint8_t expected, char actual) {
                                            return expected == static_cast<uint8_t>(actual);
                                        })) {
        const size_t width = readBigEndian32(data, 16);
        const size_t height = readBigEndian32(data, 20);
        if (width > 0 && height > 0) {
            return std::pair{width, height};
        }
        return std::nullopt;
    }

    if (data.size() < 4 || static_cast<uint8_t>(data[0]) != 0xFF ||
        static_cast<uint8_t>(data[1]) != 0xD8) {
        return std::nullopt;
    }
    size_t offset = 2;
    while (offset + 4 <= data.size()) {
        if (static_cast<uint8_t>(data[offset]) != 0xFF) {
            ++offset;
            continue;
        }
        while (offset < data.size() && static_cast<uint8_t>(data[offset]) == 0xFF) {
            ++offset;
        }
        if (offset >= data.size()) {
            return std::nullopt;
        }
        const uint8_t marker = static_cast<uint8_t>(data[offset++]);
        if (marker == 0xD8 || marker == 0xD9) {
            continue;
        }
        if (data.size() - offset < 2) {
            return std::nullopt;
        }
        const size_t segment_length = readBigEndian16(data, offset);
        if (segment_length < 2 || segment_length > data.size() - offset) {
            return std::nullopt;
        }
        if (isJpegStartOfFrame(marker) && segment_length >= 7) {
            const size_t height = readBigEndian16(data, offset + 3);
            const size_t width = readBigEndian16(data, offset + 5);
            if (width > 0 && height > 0) {
                return std::pair{width, height};
            }
            return std::nullopt;
        }
        offset += segment_length;
    }
    return std::nullopt;
}

bool calculateSceneTrsFromImage(Scene& scene, std::string_view image_data) {
    if (!scene.output_lla || !scene.map_corners_lla.has_value() || !scene.map_scale.has_value()) {
        return false;
    }
    if (!std::isfinite(*scene.map_scale) || *scene.map_scale <= 0.0) {
        throw std::invalid_argument("Scene map scale must be finite and greater than zero");
    }
    const auto dimensions = imageDimensions(image_data);
    if (!dimensions.has_value()) {
        return false;
    }

    const double width = static_cast<double>(dimensions->first) / *scene.map_scale;
    const double height = static_cast<double>(dimensions->second) / *scene.map_scale;
    const std::array<std::array<double, 3>, 4> map_corners = {
        std::array<double, 3>{0.0, 0.0, 0.0}, std::array<double, 3>{width, 0.0, 0.0},
        std::array<double, 3>{width, height, 0.0}, std::array<double, 3>{0.0, height, 0.0}};
    scene.trs_matrix = calculateTrsLocalToEcef(map_corners, *scene.map_corners_lla);
    return true;
}

} // namespace tracker