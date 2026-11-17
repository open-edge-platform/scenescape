// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "ptz_config.hpp"
#include "ptz_dwell.hpp"
#include "ptz_pose_parser.hpp"
#include "scene_loader.hpp"

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace tracker::ptz {

inline constexpr const char* kPoseTopicPrefix = "scenescape/positioning/pose/";
inline constexpr const char* kStatusTopicPrefix = "scenescape/positioning/status/";
inline constexpr const char* kPoseTopicPattern = "scenescape/positioning/pose/{}";
inline constexpr const char* kStatusTopicPattern = "scenescape/positioning/status/{}";

struct PtzClockReading {
    int64_t now_ns = 0;        ///< Synchronized local time
    bool synchronized = false; ///< NTP synced and offset within max_clock_offset_s
};

using PtzClock = std::function<PtzClockReading()>;

/// PoseContext frame of a scene (`scene:{scene_uid}`), as published by Positioning.
[[nodiscard]] std::string frameIdForScene(std::string_view scene_uid);

/// Topic segment after @p prefix; empty when the topic does not match or has more levels.
[[nodiscard]] std::string_view topicSegment(std::string_view topic, std::string_view prefix);

[[nodiscard]] DwellConfig dwellConfigFrom(const PtzConfig& config);

/**
 * @brief Outcome of the dwell contract for one PTZ detection message.
 */
struct PtzAdmission {
    bool admitted = false;
    bool managed = true; ///< false when the PTZ camera has no resolver assignment
    InvalidReason invalid_reason = InvalidReason::None;
    ReasonDetail reason_detail = ReasonDetail::None;
    PoseSnapshotPtr pose; ///< Admitting pose, or the pose the rejection refers to
    std::optional<double> pose_age_s;
    std::optional<double> timestamp_uncertainty_s;
    std::optional<double> dwell_elapsed_s;
    std::optional<int64_t> stationary_since_ns;
};

/**
 * @brief Per-source PTZ pose state for the PTZ cameras of the loaded scenes.
 *
 * Holds one DwellTracker per PTZ camera that the deployment assigns to a Resolver.
 * Pose and status payloads are untrusted: they are size-bounded, schema-validated,
 * guarded, and routed by the topic source_id before they touch dwell state. The set of
 * PTZ cameras is fixed at construction (a Manager change restarts the Tracker), so
 * isPtzCamera() is lock-free. Detections are admitted or rejected immediately.
 */
class PtzPoseRegistry {
public:
    PtzPoseRegistry(const std::vector<Scene>& scenes, const Assignments& assignments,
                    DwellConfig dwell_config, PtzMessageParser parser, PtzClock clock);

    [[nodiscard]] bool isPtzCamera(const std::string& camera_id) const {
        return sources_.contains(camera_id);
    }

    /// Apply a PoseContext; returns the rejection stage, or nullopt when applied.
    std::optional<PoseRejectStage> onPoseMessage(std::string_view topic, std::string_view payload);

    /// Apply a resolver status/LWT; returns the rejection stage, or nullopt when applied.
    std::optional<PoseRejectStage> onStatusMessage(std::string_view topic,
                                                   std::string_view payload);

    /// Dwell decision for a detection of a PTZ camera acquired at @p observation_ns.
    [[nodiscard]] PtzAdmission admit(const std::string& camera_id, int64_t observation_ns);

    /// Same as admit() with an explicit clock reading.
    [[nodiscard]] PtzAdmission admitAt(const std::string& camera_id, int64_t observation_ns,
                                       PtzClockReading clock);

    /// Assigned PTZ sources (pose topics to subscribe), sorted.
    [[nodiscard]] std::vector<std::string> poseSourceIds() const;

    /// Resolvers of the assigned sources (status topics to subscribe), sorted.
    [[nodiscard]] std::vector<std::string> resolverIds() const;

private:
    struct SourceState {
        DwellTracker tracker;
        std::string scene_uid;
    };

    std::optional<PoseRejectStage> applyPose(std::string_view topic, std::string_view payload);
    std::optional<PoseRejectStage> applyStatus(std::string_view topic, std::string_view payload);
    void reportUnassigned(const std::string& camera_id);

    PtzMessageParser parser_;
    PtzClock clock_;
    DwellConfig dwell_config_;
    /// camera_id -> state; nullptr for PTZ cameras without a resolver assignment
    std::unordered_map<std::string, std::unique_ptr<SourceState>> sources_;
    mutable std::mutex mutex_;
    std::unordered_set<std::string> reported_unassigned_;
};

} // namespace tracker::ptz
