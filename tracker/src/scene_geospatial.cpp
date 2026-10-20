// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "scene_geospatial.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <numbers>
#include <stdexcept>
#include <vector>

#include <opencv2/calib3d.hpp>

namespace tracker {

namespace {

constexpr double kEquatorialRadius = 6378137.0;
constexpr double kPolarRadius = 6356752.314245;
constexpr double kMatrixEpsilon = 1e-12;

bool finite(const std::array<double, 3>& values) {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return std::isfinite(value); });
}

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

std::array<double, 3> convertLlaToEcef(const std::array<double, 3>& lla) {
    if (!finite(lla) || lla[0] < -90.0 || lla[0] > 90.0 || lla[1] < -180.0 || lla[1] > 180.0) {
        throw std::invalid_argument("Invalid WGS84 latitude, longitude, or altitude");
    }
    const double latitude = lla[0] * std::numbers::pi / 180.0;
    const double longitude = lla[1] * std::numbers::pi / 180.0;
    const double eccentricity_squared =
        1.0 - (kPolarRadius * kPolarRadius) / (kEquatorialRadius * kEquatorialRadius);
    const double normal = kEquatorialRadius /
                          std::sqrt(1.0 - eccentricity_squared * std::pow(std::sin(latitude), 2.0));
    return {(normal + lla[2]) * std::cos(latitude) * std::cos(longitude),
            (normal + lla[2]) * std::cos(latitude) * std::sin(longitude),
            ((1.0 - eccentricity_squared) * normal + lla[2]) * std::sin(latitude)};
}

TrsMatrix calculateTrsLocalToEcef(const std::array<std::array<double, 3>, 4>& map_corners,
                                  const std::array<std::array<double, 3>, 4>& lla_corners,
                                  double z_shift) {
    if (!std::isfinite(z_shift) || z_shift <= 0.0) {
        throw std::invalid_argument("Geospatial z-shift must be finite and greater than zero");
    }

    std::vector<cv::Point3d> map_points;
    std::vector<cv::Point3d> ecef_points;
    map_points.reserve(8);
    ecef_points.reserve(8);
    for (size_t index = 0; index < map_corners.size(); ++index) {
        if (!finite(map_corners[index]) || std::abs(map_corners[index][2]) > kMatrixEpsilon) {
            throw std::invalid_argument("Map corners must be finite and lie on z=0");
        }
        const auto ecef = convertLlaToEcef(lla_corners[index]);
        map_points.emplace_back(map_corners[index][0], map_corners[index][1], 0.0);
        ecef_points.emplace_back(ecef[0], ecef[1], ecef[2]);
    }
    for (size_t index = 0; index < map_corners.size(); ++index) {
        auto elevated_lla = lla_corners[index];
        elevated_lla[2] += z_shift;
        const auto elevated_ecef = convertLlaToEcef(elevated_lla);
        map_points.emplace_back(map_corners[index][0], map_corners[index][1], z_shift);
        ecef_points.emplace_back(elevated_ecef[0], elevated_ecef[1], elevated_ecef[2]);
    }

    double scale = 1.0;
    const cv::Mat affine = cv::estimateAffine3D(map_points, ecef_points, &scale, false);
    if (affine.empty() || affine.rows != 3 || affine.cols != 4 || !std::isfinite(scale) ||
        scale <= kMatrixEpsilon || !cv::checkRange(affine)) {
        throw std::runtime_error("Unable to calculate scene geospatial transformation");
    }

    TrsMatrix result{};
    for (int row = 0; row < 3; ++row) {
        for (int column = 0; column < 3; ++column) {
            result[static_cast<size_t>(row)][static_cast<size_t>(column)] =
                affine.at<double>(row, column) * scale;
        }
        result[static_cast<size_t>(row)][3] = affine.at<double>(row, 3);
    }
    result[3][3] = 1.0;
    return result;
}

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