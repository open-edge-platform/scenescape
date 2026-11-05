// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_dwell.hpp"

#include "ptz_time.hpp"

#include <array>
#include <utility>

namespace tracker::ptz {

namespace {

constexpr std::array<const char*, kReasonDetailCount> kDetailNames = {
    "",
    "no_sample",
    "sample_stale",
    "moving",
    "settling",
    "calibration_missing",
    "calibration_changed",
    "invalid_sample",
    "backlash_unknown",
    "dwell_incomplete",
    "observation_before_dwell",
    "detection_too_old",
    "frame_mismatch",
};

constexpr std::array<InvalidReason, kReasonDetailCount> kDetailReasons = {
    InvalidReason::None,
    InvalidReason::NoPoseAvailable, // no_sample
    InvalidReason::PoseExpired,     // sample_stale
    InvalidReason::InvalidPose,     // moving
    InvalidReason::InvalidPose,     // settling
    InvalidReason::InvalidPose,     // calibration_missing
    InvalidReason::InvalidPose,     // calibration_changed
    InvalidReason::InvalidPose,     // invalid_sample
    InvalidReason::InvalidPose,     // backlash_unknown
    InvalidReason::InvalidPose,     // dwell_incomplete
    InvalidReason::InvalidPose,     // observation_before_dwell
    InvalidReason::PoseExpired,     // detection_too_old
    InvalidReason::InvalidPose,     // frame_mismatch
};

AdmissionDecision reject(ReasonDetail detail, PoseSnapshotPtr pose = nullptr,
                         std::optional<double> dwell_elapsed_s = std::nullopt) {
    return AdmissionDecision{false, canonicalReason(detail), detail, std::move(pose),
                             dwell_elapsed_s};
}

ReasonDetail motionDetail(MotionState state) {
    switch (state) {
        case MotionState::Slewing:
            return ReasonDetail::Moving;
        case MotionState::Settling:
            return ReasonDetail::Settling;
        default:
            return ReasonDetail::NoSample;
    }
}

} // namespace

const char* toString(InvalidReason reason) {
    switch (reason) {
        case InvalidReason::NoPoseAvailable:
            return "no_pose_available";
        case InvalidReason::PoseExpired:
            return "pose_expired";
        case InvalidReason::InvalidPose:
            return "invalid_pose";
        default:
            return "";
    }
}

const char* toString(ReasonDetail detail) {
    return kDetailNames[static_cast<size_t>(detail)];
}

std::optional<InvalidReason> parseInvalidReason(std::string_view text) {
    for (auto reason :
         {InvalidReason::NoPoseAvailable, InvalidReason::PoseExpired, InvalidReason::InvalidPose}) {
        if (text == toString(reason)) {
            return reason;
        }
    }
    return std::nullopt;
}

std::optional<ReasonDetail> parseReasonDetail(std::string_view text) {
    for (size_t i = 1; i < kDetailNames.size(); ++i) {
        if (text == kDetailNames[i]) {
            return static_cast<ReasonDetail>(i);
        }
    }
    return std::nullopt;
}

std::optional<MotionState> parseMotionState(std::string_view text) {
    if (text == "stationary") {
        return MotionState::Stationary;
    }
    if (text == "slewing") {
        return MotionState::Slewing;
    }
    if (text == "settling") {
        return MotionState::Settling;
    }
    if (text == "unknown") {
        return MotionState::Unknown;
    }
    return std::nullopt;
}

InvalidReason canonicalReason(ReasonDetail detail) {
    return kDetailReasons[static_cast<size_t>(detail)];
}

DwellTracker::DwellTracker(std::string source_id, std::string resolver_id, DwellConfig config,
                           std::optional<std::string> expected_frame_id,
                           std::optional<std::string> expected_calibration_version)
    : source_id_(std::move(source_id)), resolver_id_(std::move(resolver_id)), config_(config),
      expected_frame_id_(std::move(expected_frame_id)),
      expected_calibration_version_(std::move(expected_calibration_version)) {}

void DwellTracker::reset() {
    stationary_since_ns_.reset();
    stationary_since_uncertainty_ns_ = 0;
    latest_stationary_.reset();
}

void DwellTracker::setExpectedCalibrationVersion(
    const std::optional<std::string>& calibration_version) {
    if (calibration_version != expected_calibration_version_) {
        expected_calibration_version_ = calibration_version;
        reset();
    }
}

void DwellTracker::onStatus(std::string_view resolver_id, bool online, int64_t session_ns) {
    if (resolver_id != resolver_id_) {
        return;
    }
    const std::optional<int64_t> session =
        online ? std::optional<int64_t>(session_ns) : std::nullopt;
    if (!online || session != session_ns_) {
        reset();
    }
    session_ns_ = session;
}

void DwellTracker::onPose(PoseSnapshotPtr pose) {
    if (!pose) {
        return;
    }
    if (pose->source_id != source_id_) {
        reset();
        return;
    }
    if (latest_ &&
        (pose->sequence != latest_->sequence + 1 || pose->timestamp_ns <= latest_->timestamp_ns)) {
        reset();
    }
    latest_ = pose;

    if (!usableForDwell(*pose)) {
        reset();
        return;
    }
    if (latest_stationary_ &&
        (latest_stationary_->calibration_version != pose->calibration_version ||
         latest_stationary_->frame_id != pose->frame_id)) {
        reset();
    }
    if (!stationary_since_ns_) {
        stationary_since_ns_ = pose->timestamp_ns;
        stationary_since_uncertainty_ns_ = pose->timestamp_uncertainty_ns;
    }
    latest_stationary_ = std::move(pose);
}

bool DwellTracker::usableForDwell(const PoseSnapshot& pose) const {
    return pose.valid && pose.motion_state == MotionState::Stationary && pose.frame_id &&
           (!expected_frame_id_ || pose.frame_id == expected_frame_id_) &&
           (!expected_calibration_version_ ||
            pose.calibration_version == *expected_calibration_version_);
}

AdmissionDecision DwellTracker::evaluate(int64_t observation_timestamp_ns,
                                         int64_t local_now_ns) const {
    if (auto rejection = poseRejection()) {
        return std::move(*rejection);
    }

    const auto& stationary = latest_stationary_;
    if (!stationary || !stationary_since_ns_) {
        return reject(ReasonDetail::DwellIncomplete, latest_);
    }
    const int64_t since = *stationary_since_ns_;
    const int64_t elapsed_ns = stationary->timestamp_ns - since;
    const double elapsed_s = static_cast<double>(elapsed_ns) / static_cast<double>(kNsPerS);

    if (local_now_ns >= stationary->valid_until_ns ||
        local_now_ns - stationary->timestamp_ns >= config_.max_pose_age_ns) {
        return reject(ReasonDetail::SampleStale, stationary, elapsed_s);
    }
    if (local_now_ns - observation_timestamp_ns > config_.max_detection_pipeline_latency_ns) {
        return reject(ReasonDetail::DetectionTooOld, stationary, elapsed_s);
    }
    if (observation_timestamp_ns > stationary->timestamp_ns) {
        return reject(ReasonDetail::NoSample, stationary, elapsed_s);
    }
    if (elapsed_ns - stationary->timestamp_uncertainty_ns - stationary_since_uncertainty_ns_ <
        config_.max_detection_pipeline_latency_ns) {
        return reject(ReasonDetail::DwellIncomplete, stationary, elapsed_s);
    }
    if (observation_timestamp_ns - config_.max_detection_timestamp_uncertainty_ns < since) {
        return reject(ReasonDetail::ObservationBeforeDwell, stationary, elapsed_s);
    }
    return AdmissionDecision{true, InvalidReason::None, ReasonDetail::None, stationary, elapsed_s};
}

std::optional<AdmissionDecision> DwellTracker::poseRejection() const {
    if (!latest_) {
        return reject(ReasonDetail::NoSample);
    }
    const auto& latest = *latest_;
    if (!latest.valid) {
        if (latest.reason_detail != ReasonDetail::None) {
            return reject(latest.reason_detail, latest_);
        }
        const auto reason = latest.invalid_reason != InvalidReason::None
                                ? latest.invalid_reason
                                : InvalidReason::InvalidPose;
        return AdmissionDecision{false, reason, ReasonDetail::None, latest_, std::nullopt};
    }
    if (latest.motion_state != MotionState::Stationary) {
        return reject(motionDetail(latest.motion_state), latest_);
    }
    if (expected_frame_id_ && latest.frame_id != expected_frame_id_) {
        return reject(ReasonDetail::FrameMismatch, latest_);
    }
    if (expected_calibration_version_ &&
        latest.calibration_version != *expected_calibration_version_) {
        return reject(ReasonDetail::CalibrationChanged, latest_);
    }
    return std::nullopt;
}

} // namespace tracker::ptz
