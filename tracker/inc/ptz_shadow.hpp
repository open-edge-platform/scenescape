// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "ptz_registry.hpp"

#include <array>
#include <bitset>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace tracker::ptz {

inline constexpr const char* kShadowRecordType = "ptz_shadow";
inline constexpr const char* kShadowProfile = "tracker";
inline constexpr size_t kMaxRecordDetections = 50;
inline constexpr size_t kMaxSummarySamples = 10000;
inline constexpr double kTranslationReportM = 0.001;

/// Candidate (PoseContext) versus static (home pose) projection of one detection.
struct ShadowDetection {
    std::string type;
    std::array<double, 3> static_xyz{};
    std::array<double, 3> candidate_xyz{};
    double residual_m = 0.0;
};

using ShadowDetections = std::vector<ShadowDetection>;

/// Lazily computes residuals; recorders call it only for decisions they keep.
class ResidualSource {
public:
    virtual ~ResidualSource() = default;
    [[nodiscard]] virtual ShadowDetections compute() const = 0;
};

/// What a recorder needs to know about the detection message a decision refers to.
struct DecisionContext {
    std::string_view mode; ///< "enforce" or "shadow"
    std::string_view scene_id;
    std::string_view source_id;
    std::string_view observation_timestamp; ///< Acquisition timestamp as received
    std::optional<int64_t> observation_ns;
    size_t detection_count = 0;
    const PoseView* home_pose = nullptr; ///< Static camera pose, for the summary offset
};

using LineSink = std::function<void(std::string_view)>;

class DecisionRecorder {
public:
    virtual ~DecisionRecorder() = default;

    /**
     * @brief Account for one admission decision.
     * @param residuals Candidate residual source (shadow mode, admitted), or nullptr
     * @return Whether a line was written
     */
    virtual bool record(const DecisionContext& context, const PtzAdmission& admission,
                        const ResidualSource* residuals) = 0;
};

/**
 * @brief Sampled per-decision JSONL records (Controller `ShadowRecorder` parity).
 *
 * Per source: every Nth decision, plus the first occurrence of each distinct decision
 * within that window of N. Records start with `{"record_type":"ptz_shadow"` and are
 * collected from stdout by run_id; the service never writes artifact files.
 */
class ShadowRecorder : public DecisionRecorder {
public:
    ShadowRecorder(std::string run_id, int sample_every_n, LineSink sink = {});

    bool record(const DecisionContext& context, const PtzAdmission& admission,
                const ResidualSource* residuals) override;

    [[nodiscard]] std::string formatRecord(const DecisionContext& context,
                                           const PtzAdmission& admission,
                                           const ShadowDetections& detections) const;

private:
    bool shouldEmit(std::string_view source_id, bool admitted, ReasonDetail detail);

    struct SourceWindow {
        uint64_t count = 0;
        std::bitset<2 * kReasonDetailCount> seen;
    };

    std::string run_id_;
    uint64_t sample_every_n_;
    LineSink sink_;
    std::mutex mutex_;
    std::unordered_map<std::string, SourceWindow> windows_;
};

/**
 * @brief One log line per source each time a new parked pose is first applied
 *        (Controller `SummaryRecorder` parity).
 *
 * The line describes the applied pose and summarizes every decision since the previous
 * line. Residual statistics use every Nth admitted decision, which bounds the extra
 * projection cost on the MQTT thread.
 */
class SummaryRecorder : public DecisionRecorder {
public:
    explicit SummaryRecorder(int sample_every_n, LineSink sink = {});

    bool record(const DecisionContext& context, const PtzAdmission& admission,
                const ResidualSource* residuals) override;

private:
    struct Period {
        std::optional<int64_t> first_ns;
        std::optional<int64_t> last_ns;
        std::vector<std::pair<std::string, uint64_t>> decisions; ///< Insertion order
        std::deque<double> residuals;
        uint64_t detections = 0;
        uint64_t admitted_detections = 0;
        uint64_t admitted_decisions = 0;

        [[nodiscard]] std::string describe() const;
    };

    [[nodiscard]] std::string summary(const DecisionContext& context, const PtzAdmission& admission,
                                      const Period& period) const;
    void add(Period& period, const DecisionContext& context, const PtzAdmission& admission,
             const ResidualSource* residuals) const;

    uint64_t sample_every_n_;
    LineSink sink_;
    std::mutex mutex_;
    std::unordered_map<std::string, Period> periods_;
    std::unordered_map<std::string, int64_t> applied_;
};

/// Rotation (deg) and translation (m) of @p applied relative to @p home.
[[nodiscard]] std::pair<double, double> offsetFromHome(const PoseView& home,
                                                       const PoseView& applied);

/// Linear-interpolated percentile of sorted values (numpy default), q in [0, 1].
[[nodiscard]] double percentile(const std::vector<double>& sorted, double q);

} // namespace tracker::ptz
