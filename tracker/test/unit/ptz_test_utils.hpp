// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "ptz_registry.hpp"
#include "ptz_time.hpp"
#include "scene_loader.hpp"

#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <optional>
#include <string>
#include <vector>

#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker::ptz::test {

inline constexpr const char* kSceneUid = "scene-1";
inline constexpr const char* kSourceId = "ptz-cam";
inline constexpr const char* kResolverId = "positioning";
inline constexpr const char* kCalibration = "cal-v1";
inline constexpr int64_t kBaseNs = 1'790'000'000'000'000'000; // 2026-09-21T...Z

/// Format ns since the epoch as an ISO-8601 UTC string with microsecond precision.
inline std::string iso(int64_t ns) {
    using namespace std::chrono;
    const sys_time<nanoseconds> tp{nanoseconds{ns}};
    const auto day = floor<days>(tp);
    const year_month_day ymd{day};
    const hh_mm_ss hms{floor<microseconds>(tp - day)};
    char buffer[40];
    std::snprintf(buffer, sizeof(buffer), "%04d-%02u-%02uT%02lld:%02lld:%02lld.%06lldZ",
                  static_cast<int>(ymd.year()), static_cast<unsigned>(ymd.month()),
                  static_cast<unsigned>(ymd.day()), static_cast<long long>(hms.hours().count()),
                  static_cast<long long>(hms.minutes().count()),
                  static_cast<long long>(hms.seconds().count()),
                  static_cast<long long>(hms.subseconds().count()));
    return buffer;
}

inline int64_t ms(int64_t value) {
    return value * 1'000'000;
}

/// Rigid scene_from_camera matrix: yaw about Z then translation (row-major 4x4).
inline std::array<double, 16> yawMatrix(double yaw_deg, std::array<double, 3> t = {0, 0, 3}) {
    const double r = yaw_deg * 3.14159265358979323846 / 180.0;
    const double c = std::cos(r);
    const double s = std::sin(r);
    return {c, -s, 0, t[0], s, c, 0, t[1], 0, 0, 1, t[2], 0, 0, 0, 1};
}

/// Downward-looking camera (Rz(yaw) * Rx(180)) at @p height: yaw 0 equals test::camera()'s pose.
inline std::array<double, 16> lookDownMatrix(double yaw_deg, double height = 3.0) {
    const double r = yaw_deg * 3.14159265358979323846 / 180.0;
    const double c = std::cos(r);
    const double s = std::sin(r);
    return {c, s, 0, 0, s, -c, 0, 0, 0, 0, -1, height, 0, 0, 0, 1};
}

struct PoseJson {
    std::string source_id = kSourceId;
    int64_t sequence = 1;
    int64_t timestamp_ns = kBaseNs;
    int64_t valid_for_ns = ms(1000);
    bool valid = true;
    std::string motion_state = "stationary";
    double uncertainty_s = 0.01;
    std::string calibration_version = kCalibration;
    std::string frame_id = std::string("scene:") + kSceneUid;
    std::array<double, 16> matrix = yawMatrix(0.0);
    std::string invalid_reason;
    std::string reason_detail;

    [[nodiscard]] std::string json() const {
        rapidjson::StringBuffer buffer;
        rapidjson::Writer<rapidjson::StringBuffer> w(buffer);
        w.StartObject();
        w.Key("schema_version");
        w.Int(1);
        w.Key("source_id");
        w.String(source_id.c_str());
        w.Key("timestamp");
        w.String(iso(timestamp_ns).c_str());
        w.Key("valid_until");
        w.String(iso(timestamp_ns + valid_for_ns).c_str());
        w.Key("sequence");
        w.Int64(sequence);
        w.Key("valid");
        w.Bool(valid);
        w.Key("motion_state");
        w.String(motion_state.c_str());
        w.Key("sample_age_s");
        w.Double(0.0);
        w.Key("timestamp_uncertainty_s");
        w.Double(uncertainty_s);
        w.Key("calibration_version");
        w.String(calibration_version.c_str());
        if (valid) {
            w.Key("pose");
            w.StartObject();
            w.Key("frame_id");
            w.String(frame_id.c_str());
            w.Key("transform_direction");
            w.String("scene_from_camera");
            w.Key("matrix_layout");
            w.String("row_major");
            w.Key("matrix_4x4");
            w.StartArray();
            for (int r = 0; r < 4; ++r) {
                w.StartArray();
                for (int c = 0; c < 4; ++c) {
                    w.Double(matrix[static_cast<size_t>(r * 4 + c)]);
                }
                w.EndArray();
            }
            w.EndArray();
            w.Key("translation_unit");
            w.String("m");
            w.EndObject();
            w.Key("quality");
            w.StartObject();
            w.Key("score");
            w.Double(0.9);
            w.Key("temporal_score");
            w.Double(0.9);
            w.Key("calibration_score");
            w.Double(0.9);
            w.Key("reprojection_rms_px");
            w.Double(1.5);
            w.EndObject();
        } else {
            w.Key("invalid_reason");
            w.String(invalid_reason.empty() ? "invalid_pose" : invalid_reason.c_str());
            if (!reason_detail.empty()) {
                w.Key("reason_detail");
                w.String(reason_detail.c_str());
            }
        }
        w.EndObject();
        return buffer.GetString();
    }
};

inline std::string statusJson(const std::string& resolver_id, const std::string& status,
                              int64_t session_ns) {
    return R"({"resolver_id":")" + resolver_id + R"(","status":")" + status +
           R"(","timestamp":")" + iso(session_ns) + R"("})";
}

inline std::string poseTopic(const std::string& source_id = kSourceId) {
    return std::string(kPoseTopicPrefix) + source_id;
}

inline std::string statusTopic(const std::string& resolver_id = kResolverId) {
    return std::string(kStatusTopicPrefix) + resolver_id;
}

/// Camera at 3 m height looking straight down, with optional PTZ calibration.
inline Camera camera(const std::string& uid, bool ptz,
                     std::optional<std::string> calibration_version = kCalibration) {
    Camera cam;
    cam.uid = uid;
    cam.name = uid;
    cam.intrinsics = CameraIntrinsics{500.0, 500.0, 320.0, 240.0, {}};
    cam.extrinsics.translation = {0.0, 0.0, 3.0};
    cam.extrinsics.rotation = {180.0, 0.0, 0.0};
    if (ptz) {
        cam.ptz = PtzCalibrationRef{std::move(calibration_version)};
    }
    return cam;
}

inline Scene scene(std::vector<Camera> cameras, const std::string& uid = kSceneUid) {
    return Scene{uid, "PTZ scene", std::move(cameras)};
}

inline DwellConfig dwellConfig(double max_pose_age_s = 0.5, double latency_s = 0.2,
                               double observation_uncertainty_s = 0.0) {
    return DwellConfig{secondsToNs(max_pose_age_s), secondsToNs(latency_s),
                       secondsToNs(observation_uncertainty_s)};
}

} // namespace tracker::ptz::test
