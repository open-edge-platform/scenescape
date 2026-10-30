// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"
#include "coordinate_transformer.hpp"
#include "object_class.hpp"
#include "ptz_registry.hpp"
#include "ptz_shadow.hpp"
#include "scene_loader.hpp"
#include "tracking_types.hpp"

#include <chrono>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace tracker::ptz {

inline constexpr const char* kPositioningTopicPrefix = "scenescape/positioning/";

/// How a PTZ camera's detection message continues after the dwell gate.
enum class GateAction {
    Static,  ///< Not a PTZ decision that changes tracking (static camera or shadow mode)
    Gated,   ///< Rejected: buffered as a detection-less heartbeat; tracks keep aging
    Project, ///< Admitted: buffered with the admitting pose
};

struct GateResult {
    GateAction action = GateAction::Static;
    PoseSnapshotPtr pose; ///< Admitting pose (Project only)
};

[[nodiscard]] const char* toString(PtzMode mode);

/**
 * @brief Tracker side of the PTZ PoseContext contract.
 *
 * Owns the pose registry and the decision recorder. All entry points run on the MQTT
 * callback thread and never block or queue: a detection is admitted or rejected at once.
 * Enforcing mode gates batches; shadow mode only observes and records, computing the
 * candidate projection for sampled admitted decisions here so that tracking workers and
 * MOT are never involved.
 */
class PtzConsumer {
public:
    PtzConsumer(PtzMode mode, std::shared_ptr<PtzPoseRegistry> registry,
                std::unique_ptr<DecisionRecorder> recorder, const std::vector<Scene>& scenes,
                ObjectClassMap object_classes = {});

    [[nodiscard]] PtzMode mode() const { return mode_; }

    [[nodiscard]] bool isPtzCamera(const std::string& camera_id) const {
        return registry_->isPtzCamera(camera_id);
    }

    /**
     * @brief Apply the dwell contract to one PTZ camera message.
     *
     * The observation time is the message's acquisition timestamp (ns precision); the
     * parsed @p acquisition_time is used only when the text cannot be parsed exactly.
     */
    [[nodiscard]] GateResult gate(const Scene& scene, const std::string& camera_id,
                                  const CameraMessage& message,
                                  std::chrono::system_clock::time_point acquisition_time);

    /// Route a scenescape/positioning/{pose,status}/... message to the registry.
    void onPositioningMessage(std::string_view topic, std::string_view payload);

    /// Pose topics of the assigned PTZ sources and status topics of their resolvers.
    [[nodiscard]] std::vector<std::string> subscriptionTopics() const;

    /// Candidate versus static projection of a message's detections (bounded).
    [[nodiscard]] ShadowDetections residuals(const std::string& camera_id,
                                             const CameraMessage& message,
                                             const PoseView& candidate) const;

private:
    const CoordinateTransformer* staticTransformer(const std::string& camera_id,
                                                   const std::string& category) const;

    PtzMode mode_;
    std::shared_ptr<PtzPoseRegistry> registry_;
    std::unique_ptr<DecisionRecorder> recorder_;
    ObjectClassMap object_classes_;
    std::unordered_map<std::string, Camera> cameras_;      ///< PTZ cameras by id
    std::unordered_map<std::string, PoseView> home_poses_; ///< Static pose by camera id
    mutable std::mutex transformers_mutex_;
    mutable std::unordered_map<std::string, CoordinateTransformer> transformers_;
};

} // namespace tracker::ptz
