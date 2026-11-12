// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_consumer.hpp"

#include "logger.hpp"
#include "metrics.hpp"
#include "ptz_time.hpp"

#include <cmath>
#include <format>
#include <span>

namespace tracker::ptz {

namespace {

class MessageResiduals : public ResidualSource {
public:
    MessageResiduals(const PtzConsumer& consumer, const std::string& camera_id,
                     const CameraMessage& message, const PoseView& candidate)
        : consumer_(consumer), camera_id_(camera_id), message_(message), candidate_(candidate) {}

    [[nodiscard]] ShadowDetections compute() const override {
        return consumer_.residuals(camera_id_, message_, candidate_);
    }

private:
    const PtzConsumer& consumer_;
    const std::string& camera_id_;
    const CameraMessage& message_;
    const PoseView& candidate_;
};

size_t detectionCount(const CameraMessage& message) {
    size_t count = 0;
    for (const auto& [category, detections] : message.objects) {
        count += detections.size();
    }
    return count;
}

} // namespace

const char* toString(PtzMode mode) {
    switch (mode) {
        case PtzMode::Enforce:
            return "enforce";
        case PtzMode::Shadow:
            return "shadow";
        default:
            return "off";
    }
}

PtzConsumer::PtzConsumer(PtzMode mode, std::shared_ptr<PtzPoseRegistry> registry,
                         std::unique_ptr<DecisionRecorder> recorder,
                         const std::vector<Scene>& scenes, ObjectClassMap object_classes)
    : mode_(mode), registry_(std::move(registry)), recorder_(std::move(recorder)),
      object_classes_(std::move(object_classes)) {
    for (const auto& scene : scenes) {
        for (const auto& camera : scene.cameras) {
            if (!camera.ptz.has_value()) {
                continue;
            }
            cameras_.emplace(camera.uid, camera);
            home_poses_.emplace(
                camera.uid,
                CoordinateTransformer(camera.intrinsics, camera.extrinsics).staticPose());
        }
    }
}

GateResult PtzConsumer::gate(const Scene& scene, const std::string& camera_id,
                             const CameraMessage& message,
                             std::chrono::system_clock::time_point acquisition_time) {
    const int64_t observation_ns =
        parseIsoTimestampNs(message.timestamp).value_or(toNs(acquisition_time));
    const auto admission = registry_->admit(camera_id, observation_ns);

    const char* mode = toString(mode_);
    if (admission.admitted) {
        Metrics::inc_ptz_admitted({{kAttrMode, mode}});
    } else {
        const char* detail = admission.reason_detail == ReasonDetail::None
                                 ? "none"
                                 : toString(admission.reason_detail);
        Metrics::inc_ptz_rejected({{kAttrMode, mode}, {kAttrReasonDetail, detail}});
    }

    if (recorder_) {
        auto home = home_poses_.find(camera_id);
        const DecisionContext context{
            mode,
            scene.uid,
            camera_id,
            message.timestamp,
            observation_ns,
            detectionCount(message),
            home == home_poses_.end() ? nullptr : &home->second,
        };
        const bool with_residuals = mode_ == PtzMode::Shadow && admission.admitted &&
                                    admission.pose && admission.pose->view;
        if (with_residuals) {
            const MessageResiduals residual_source(*this, camera_id, message,
                                                   *admission.pose->view);
            recorder_->record(context, admission, &residual_source);
        } else {
            recorder_->record(context, admission, nullptr);
        }
    }

    if (mode_ != PtzMode::Enforce) {
        return {};
    }
    if (!admission.admitted) {
        return {GateAction::Gated, nullptr};
    }
    return {GateAction::Project, admission.pose};
}

void PtzConsumer::onPositioningMessage(std::string_view topic, std::string_view payload) {
    std::optional<PoseRejectStage> stage;
    if (topic.starts_with(kPoseTopicPrefix)) {
        stage = registry_->onPoseMessage(topic, payload);
    } else if (topic.starts_with(kStatusTopicPrefix)) {
        stage = registry_->onStatusMessage(topic, payload);
    } else {
        return;
    }
    if (stage) {
        LOG_DEBUG("Rejected positioning message on {} at stage {}", topic, toString(*stage));
    }
}

std::vector<std::string> PtzConsumer::subscriptionTopics() const {
    std::vector<std::string> topics;
    for (const auto& source_id : registry_->poseSourceIds()) {
        topics.push_back(std::format(kPoseTopicPattern, source_id));
    }
    for (const auto& resolver_id : registry_->resolverIds()) {
        topics.push_back(std::format(kStatusTopicPattern, resolver_id));
    }
    return topics;
}

const CoordinateTransformer* PtzConsumer::staticTransformer(const std::string& camera_id,
                                                            const std::string& category) const {
    auto camera = cameras_.find(camera_id);
    if (camera == cameras_.end()) {
        return nullptr;
    }
    std::string key = camera_id;
    key.push_back('\0');
    key += category;
    std::lock_guard lock(transformers_mutex_);
    auto it = transformers_.find(key);
    if (it == transformers_.end()) {
        const auto object_class = lookupObjectClass(object_classes_, category);
        it = transformers_
                 .emplace(std::move(key), CoordinateTransformer(
                                              camera->second.intrinsics, camera->second.extrinsics,
                                              object_class.shift_type, object_class.footprint_half))
                 .first;
    }
    return &it->second;
}

ShadowDetections PtzConsumer::residuals(const std::string& camera_id, const CameraMessage& message,
                                        const PoseView& candidate) const {
    ShadowDetections results;
    for (const auto& [category, detections] : message.objects) {
        const size_t budget = kMaxRecordDetections - results.size();
        if (budget == 0) {
            break;
        }
        if (detections.empty()) {
            continue;
        }
        const auto* transformer = staticTransformer(camera_id, category);
        if (transformer == nullptr) {
            continue;
        }
        const std::span<const Detection> sample(detections.data(),
                                                std::min(budget, detections.size()));
        const auto static_objects = transformer->transformDetections(sample);
        const auto candidate_objects = transformer->transformDetections(sample, candidate);
        const size_t count = std::min(static_objects.size(), candidate_objects.size());
        for (size_t i = 0; i < count; ++i) {
            const auto& s = static_objects[i];
            const auto& c = candidate_objects[i];
            results.push_back({category,
                               {s.x, s.y, s.z},
                               {c.x, c.y, c.z},
                               std::sqrt((c.x - s.x) * (c.x - s.x) + (c.y - s.y) * (c.y - s.y) +
                                         (c.z - s.z) * (c.z - s.z))});
        }
    }
    return results;
}

} // namespace tracker::ptz
