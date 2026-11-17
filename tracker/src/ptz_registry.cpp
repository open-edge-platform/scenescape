// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_registry.hpp"

#include "logger.hpp"
#include "metrics.hpp"
#include "ptz_time.hpp"

#include <algorithm>
#include <set>

namespace tracker::ptz {

namespace {

PtzAdmission rejection(ReasonDetail detail, bool managed = true) {
    PtzAdmission admission;
    admission.managed = managed;
    admission.invalid_reason = canonicalReason(detail);
    admission.reason_detail = detail;
    return admission;
}

void fillPoseFields(PtzAdmission& admission, int64_t now_ns) {
    if (!admission.pose) {
        return;
    }
    const auto age_ns = std::max<int64_t>(0, now_ns - admission.pose->timestamp_ns);
    admission.pose_age_s = static_cast<double>(age_ns) / static_cast<double>(kNsPerS);
    admission.timestamp_uncertainty_s =
        static_cast<double>(admission.pose->timestamp_uncertainty_ns) /
        static_cast<double>(kNsPerS);
}

} // namespace

std::string frameIdForScene(std::string_view scene_uid) {
    return "scene:" + std::string(scene_uid);
}

std::string_view topicSegment(std::string_view topic, std::string_view prefix) {
    if (!topic.starts_with(prefix)) {
        return {};
    }
    auto segment = topic.substr(prefix.size());
    if (segment.find('/') != std::string_view::npos) {
        return {};
    }
    return segment;
}

DwellConfig dwellConfigFrom(const PtzConfig& config) {
    return DwellConfig{
        secondsToNs(config.max_pose_age_s.value_or(0.0)),
        secondsToNs(config.max_detection_pipeline_latency_s.value_or(0.0)),
        secondsToNs(config.max_detection_timestamp_uncertainty_s.value_or(0.0)),
    };
}

PtzPoseRegistry::PtzPoseRegistry(const std::vector<Scene>& scenes, const Assignments& assignments,
                                 DwellConfig dwell_config, PtzMessageParser parser, PtzClock clock)
    : parser_(std::move(parser)), clock_(std::move(clock)), dwell_config_(dwell_config) {
    for (const auto& scene : scenes) {
        for (const auto& camera : scene.cameras) {
            if (!camera.ptz.has_value()) {
                continue;
            }
            auto resolver = assignments.find(camera.uid);
            if (resolver == assignments.end()) {
                sources_.emplace(camera.uid, nullptr);
                continue;
            }
            sources_.emplace(camera.uid, std::make_unique<SourceState>(SourceState{
                                             DwellTracker(camera.uid, resolver->second,
                                                          dwell_config_, frameIdForScene(scene.uid),
                                                          camera.ptz->calibration_version),
                                             scene.uid}));
        }
    }
}

std::optional<PoseRejectStage> PtzPoseRegistry::onPoseMessage(std::string_view topic,
                                                              std::string_view payload) {
    auto stage = applyPose(topic, payload);
    if (stage) {
        Metrics::inc_ptz_pose_rejected({{kAttrStage, toString(*stage)}});
    }
    return stage;
}

std::optional<PoseRejectStage> PtzPoseRegistry::applyPose(std::string_view topic,
                                                          std::string_view payload) {
    auto parsed = parser_.parsePose(payload);
    if (parsed.stage) {
        return parsed.stage;
    }
    auto source_id = topicSegment(topic, kPoseTopicPrefix);
    if (source_id.empty()) {
        return PoseRejectStage::Topic;
    }
    // Routed by topic; a payload naming another source resets that source's dwell.
    std::lock_guard lock(mutex_);
    auto it = sources_.find(std::string(source_id));
    if (it == sources_.end() || !it->second) {
        return PoseRejectStage::Unmanaged;
    }
    it->second->tracker.onPose(std::move(parsed.pose));
    return std::nullopt;
}

std::optional<PoseRejectStage> PtzPoseRegistry::onStatusMessage(std::string_view topic,
                                                                std::string_view payload) {
    auto stage = applyStatus(topic, payload);
    if (stage) {
        Metrics::inc_ptz_pose_rejected({{kAttrStage, toString(*stage)}});
    }
    return stage;
}

std::optional<PoseRejectStage> PtzPoseRegistry::applyStatus(std::string_view topic,
                                                            std::string_view payload) {
    auto parsed = parser_.parseStatus(payload);
    if (parsed.stage) {
        return parsed.stage;
    }
    const auto& status = *parsed.status;
    if (topicSegment(topic, kStatusTopicPrefix) != status.resolver_id) {
        return PoseRejectStage::Topic;
    }
    std::lock_guard lock(mutex_);
    for (auto& [camera_id, state] : sources_) {
        if (state) {
            state->tracker.onStatus(status.resolver_id, status.online, status.session_ns);
        }
    }
    return std::nullopt;
}

PtzAdmission PtzPoseRegistry::admit(const std::string& camera_id, int64_t observation_ns) {
    return admitAt(camera_id, observation_ns, clock_());
}

PtzAdmission PtzPoseRegistry::admitAt(const std::string& camera_id, int64_t observation_ns,
                                      PtzClockReading clock) {
    std::lock_guard lock(mutex_);
    auto it = sources_.find(camera_id);
    if (it == sources_.end() || !it->second) {
        reportUnassigned(camera_id);
        return rejection(ReasonDetail::NoSample, false);
    }
    const auto& tracker = it->second->tracker;
    auto decision = tracker.evaluate(observation_ns, clock.now_ns);

    PtzAdmission admission;
    admission.dwell_elapsed_s = decision.dwell_elapsed_s;
    admission.pose = std::move(decision.pose);
    if (decision.admitted && !clock.synchronized) {
        admission.invalid_reason = canonicalReason(ReasonDetail::SampleStale);
        admission.reason_detail = ReasonDetail::SampleStale;
    } else if (decision.admitted) {
        admission.admitted = true;
        admission.stationary_since_ns = tracker.stationarySinceNs();
    } else {
        admission.invalid_reason = decision.invalid_reason;
        admission.reason_detail = decision.reason_detail;
    }
    fillPoseFields(admission, clock.now_ns);
    return admission;
}

void PtzPoseRegistry::reportUnassigned(const std::string& camera_id) {
    if (!reported_unassigned_.insert(camera_id).second) {
        return;
    }
    LOG_ERROR("PTZ camera {} has no resolver in the positioning assignment manifest; its "
              "detections are dropped",
              camera_id);
}

std::vector<std::string> PtzPoseRegistry::poseSourceIds() const {
    std::vector<std::string> ids;
    for (const auto& [camera_id, state] : sources_) {
        if (state) {
            ids.push_back(camera_id);
        }
    }
    std::sort(ids.begin(), ids.end());
    return ids;
}

std::vector<std::string> PtzPoseRegistry::resolverIds() const {
    std::set<std::string> ids;
    for (const auto& [camera_id, state] : sources_) {
        if (state) {
            ids.insert(state->tracker.resolverId());
        }
    }
    return {ids.begin(), ids.end()};
}

} // namespace tracker::ptz
