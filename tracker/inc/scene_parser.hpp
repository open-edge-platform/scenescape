// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scene_loader.hpp"

#include "json_utils.hpp"

#include <array>
#include <stdexcept>
#include <string>

#include <rapidjson/document.h>
#include <rapidjson/pointer.h>

namespace tracker {
namespace detail {

using Pointer = rapidjson::Pointer;

/**
 * @brief Get required JSON array by pointer.
 */
inline const rapidjson::Value::ConstArray
require_array(const rapidjson::Value& doc, const char* pointer, const std::string& context) {
    if (auto* val = Pointer(pointer).Get(doc)) {
        if (val->IsArray()) {
            return val->GetArray();
        }
    }
    throw std::runtime_error("Missing required " + context + " array: " + pointer);
}

/**
 * @brief Get required 3-element array from JSON.
 */
inline std::array<double, 3> require_array3(const rapidjson::Value& doc, const char* pointer,
                                            const std::string& context) {
    if (auto* val = Pointer(pointer).Get(doc)) {
        if (val->IsArray() && val->Size() == 3) {
            std::array<double, 3> result;
            for (rapidjson::SizeType i = 0; i < 3; ++i) {
                if (!(*val)[i].IsNumber()) {
                    throw std::runtime_error(context + ": " + pointer + "[" + std::to_string(i) +
                                             "] must be a number");
                }
                result[i] = (*val)[i].GetDouble();
            }
            return result;
        }
    }
    throw std::runtime_error("Missing required " + context + " array: " + pointer);
}

/**
 * @brief Parse a single scene JSON value into a Scene struct.
 *
 * Expects the canonical schema format (intrinsics nested, extrinsics nested).
 * Used by both FileSceneLoader and ApiSceneLoader.
 * See scene.schema.json.
 */
inline Scene parse_scene(const rapidjson::Value& scene_val) {
    Scene scene;
    scene.uid = require_value<std::string>(scene_val, scene_json::SCENE_UID, "scene");
    scene.name = require_value<std::string>(scene_val, scene_json::SCENE_NAME, "scene");

    for (const auto& cam_val : require_array(scene_val, scene_json::SCENE_CAMERAS, "scene")) {
        Camera camera;
        camera.uid = require_value<std::string>(cam_val, scene_json::CAMERA_UID, "camera");
        camera.name = require_value<std::string>(cam_val, scene_json::CAMERA_NAME, "camera");

        // Parse intrinsics (optional, default to 0.0)
        camera.intrinsics.fx =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_FX).value_or(0.0);
        camera.intrinsics.fy =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_FY).value_or(0.0);
        camera.intrinsics.cx =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_CX).value_or(0.0);
        camera.intrinsics.cy =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_CY).value_or(0.0);

        // Parse distortion (optional, default to 0.0)
        camera.intrinsics.distortion.k1 =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_K1).value_or(0.0);
        camera.intrinsics.distortion.k2 =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_K2).value_or(0.0);
        camera.intrinsics.distortion.p1 =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_P1).value_or(0.0);
        camera.intrinsics.distortion.p2 =
            get_value<double>(cam_val, scene_json::CAMERA_INTRINSICS_DISTORTION_P2).value_or(0.0);

        // Parse extrinsics (required)
        std::string cam_context = "camera '" + camera.uid + "'";
        camera.extrinsics.translation =
            require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_TRANSLATION, cam_context);
        camera.extrinsics.rotation =
            require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_ROTATION, cam_context);
        camera.extrinsics.scale =
            require_array3(cam_val, scene_json::CAMERA_EXTRINSICS_SCALE, cam_context);

        scene.cameras.push_back(std::move(camera));
    }

    return scene;
}

} // namespace detail
} // namespace tracker
