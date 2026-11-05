// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "pose_view.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace tracker::ptz {

/// Canonical invalid_reason (shared with the Controller and external sources).
enum class InvalidReason : uint8_t {
    None,
    NoPoseAvailable,
    PoseExpired,
    InvalidPose
};

/// PTZ reason_detail (Resolver-published) and consumer-only dwell admission details.
enum class ReasonDetail : uint8_t {
    None,
    NoSample,
    SampleStale,
    Moving,
    Settling,
    CalibrationMissing,
    CalibrationChanged,
    InvalidSample,
    BacklashUnknown,
    DwellIncomplete,
    ObservationBeforeDwell,
    DetectionTooOld,
    FrameMismatch,
};
inline constexpr size_t kReasonDetailCount = 13;

enum class MotionState : uint8_t {
    Stationary,
    Slewing,
    Settling,
    Unknown
};

[[nodiscard]] const char* toString(InvalidReason reason);
[[nodiscard]] const char* toString(ReasonDetail detail);
[[nodiscard]] std::optional<InvalidReason> parseInvalidReason(std::string_view text);
[[nodiscard]] std::optional<ReasonDetail> parseReasonDetail(std::string_view text);
[[nodiscard]] std::optional<MotionState> parseMotionState(std::string_view text);

/// Canonical invalid_reason of a reason_detail (positioning_reasons.canonical_reason).
[[nodiscard]] InvalidReason canonicalReason(ReasonDetail detail);

/**
 * @brief Fields of a validated PoseContext used for dwell admission and projection.
 *
 * Immutable once built; shared by every batch the pose admits.
 */
struct PoseSnapshot {
    std::string source_id;
    int64_t sequence = 0;
    int64_t timestamp_ns = 0;
    int64_t valid_until_ns = 0;
    int64_t timestamp_uncertainty_ns = 0;
    bool valid = false;
    MotionState motion_state = MotionState::Unknown;
    std::string calibration_version;
    std::optional<std::string> frame_id;
    InvalidReason invalid_reason = InvalidReason::None;
    ReasonDetail reason_detail = ReasonDetail::None;
    std::optional<PoseView> view; ///< Present when valid (rigid scene_from_camera)
};

using PoseSnapshotPtr = std::shared_ptr<const PoseSnapshot>;

struct DwellConfig {
    int64_t max_pose_age_ns = 0;
    int64_t max_detection_pipeline_latency_ns = 0;
    int64_t max_detection_timestamp_uncertainty_ns = 0;
};

struct AdmissionDecision {
    bool admitted = false;
    InvalidReason invalid_reason = InvalidReason::None;
    ReasonDetail reason_detail = ReasonDetail::None;
    PoseSnapshotPtr pose;
    std::optional<double> dwell_elapsed_s;
};

/**
 * @brief Per-source dwell state for one PTZ camera (port of positioning_dwell.DwellTracker).
 *
 * The check order, reset rules, and integer-ns comparisons are normative and identical
 * to the Python Controller implementation; both are verified against
 * tests/data/ptz/dwell_conformance.json. Not thread-safe; evaluate() does not allocate.
 */
class DwellTracker {
public:
    DwellTracker(std::string source_id, std::string resolver_id, DwellConfig config,
                 std::optional<std::string> expected_frame_id = std::nullopt,
                 std::optional<std::string> expected_calibration_version = std::nullopt);

    void reset();

    void setExpectedCalibrationVersion(const std::optional<std::string>& calibration_version);

    /// Resolver status/LWT; any session change or non-online status resets dwell.
    void onStatus(std::string_view resolver_id, bool online, int64_t session_ns);

    void onPose(PoseSnapshotPtr pose);

    [[nodiscard]] AdmissionDecision evaluate(int64_t observation_timestamp_ns,
                                             int64_t local_now_ns) const;

    [[nodiscard]] const PoseSnapshotPtr& latestPose() const { return latest_; }
    [[nodiscard]] std::optional<int64_t> stationarySinceNs() const { return stationary_since_ns_; }
    [[nodiscard]] const std::string& sourceId() const { return source_id_; }
    [[nodiscard]] const std::string& resolverId() const { return resolver_id_; }
    [[nodiscard]] const std::optional<std::string>& expectedFrameId() const {
        return expected_frame_id_;
    }
    [[nodiscard]] const std::optional<std::string>& expectedCalibrationVersion() const {
        return expected_calibration_version_;
    }

private:
    [[nodiscard]] bool usableForDwell(const PoseSnapshot& pose) const;
    [[nodiscard]] std::optional<AdmissionDecision> poseRejection() const;

    std::string source_id_;
    std::string resolver_id_;
    DwellConfig config_;
    std::optional<std::string> expected_frame_id_;
    std::optional<std::string> expected_calibration_version_;
    PoseSnapshotPtr latest_;
    std::optional<int64_t> session_ns_;
    std::optional<int64_t> stationary_since_ns_;
    int64_t stationary_since_uncertainty_ns_ = 0;
    PoseSnapshotPtr latest_stationary_;
};

} // namespace tracker::ptz
