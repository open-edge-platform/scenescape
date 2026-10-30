// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_shadow.hpp"

#include "logger.hpp"

#include <algorithm>
#include <cmath>
#include <format>
#include <numbers>

#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker::ptz {

namespace {

constexpr const char* kAdmittedKey = "admitted";

LineSink defaultRawSink() {
    return [](std::string_view line) { Logger::raw_line(line); };
}

LineSink defaultInfoSink() {
    return [](std::string_view line) { LOG_INFO("{}", line); };
}

using JsonWriter = rapidjson::Writer<rapidjson::StringBuffer>;

void writeString(JsonWriter& writer, std::string_view value) {
    writer.String(value.data(), static_cast<rapidjson::SizeType>(value.size()));
}

void writeOptional(JsonWriter& writer, const std::optional<double>& value) {
    if (value) {
        writer.Double(*value);
    } else {
        writer.Null();
    }
}

void writeXyz(JsonWriter& writer, const std::array<double, 3>& xyz) {
    writer.StartArray();
    for (double v : xyz) {
        writer.Double(v);
    }
    writer.EndArray();
}

void writeDetections(JsonWriter& writer, const ShadowDetections& detections) {
    writer.StartArray();
    const size_t count = std::min(detections.size(), kMaxRecordDetections);
    for (size_t i = 0; i < count; ++i) {
        const auto& d = detections[i];
        writer.StartObject();
        writer.Key("type");
        writeString(writer, d.type);
        writer.Key("static_xyz");
        writeXyz(writer, d.static_xyz);
        writer.Key("candidate_xyz");
        writeXyz(writer, d.candidate_xyz);
        writer.Key("residual_m");
        writer.Double(d.residual_m);
        writer.EndObject();
    }
    writer.EndArray();
}

std::string decisionKey(const PtzAdmission& admission) {
    if (admission.admitted) {
        return kAdmittedKey;
    }
    return admission.reason_detail == ReasonDetail::None ? "None"
                                                         : toString(admission.reason_detail);
}

std::string number(const std::optional<double>& value, int digits) {
    if (!value) {
        return "?";
    }
    return digits == 1 ? std::format("{:.1f}", *value) : std::format("{:.2f}", *value);
}

} // namespace

ShadowRecorder::ShadowRecorder(std::string run_id, int sample_every_n, LineSink sink)
    : run_id_(std::move(run_id)),
      sample_every_n_(static_cast<uint64_t>(std::max(sample_every_n, 1))),
      sink_(sink ? std::move(sink) : defaultRawSink()) {}

bool ShadowRecorder::shouldEmit(std::string_view source_id, bool admitted, ReasonDetail detail) {
    auto& window = windows_[std::string(source_id)];
    const size_t key = (admitted ? kReasonDetailCount : 0) + static_cast<size_t>(detail);
    const uint64_t count = window.count++;
    if (count % sample_every_n_ == 0) {
        window.seen.reset();
        window.seen.set(key);
        return true;
    }
    if (window.seen.test(key)) {
        return false;
    }
    window.seen.set(key);
    return true;
}

bool ShadowRecorder::record(const DecisionContext& context, const PtzAdmission& admission,
                            const ResidualSource* residuals) {
    {
        std::lock_guard lock(mutex_);
        if (!shouldEmit(context.source_id, admission.admitted, admission.reason_detail)) {
            return false;
        }
    }
    const ShadowDetections detections = residuals ? residuals->compute() : ShadowDetections{};
    sink_(formatRecord(context, admission, detections));
    return true;
}

std::string ShadowRecorder::formatRecord(const DecisionContext& context,
                                         const PtzAdmission& admission,
                                         const ShadowDetections& detections) const {
    rapidjson::StringBuffer buffer;
    JsonWriter writer(buffer);
    writer.StartObject();
    writer.Key("record_type");
    writer.String(kShadowRecordType);
    writer.Key("profile");
    writer.String(kShadowProfile);
    writer.Key("mode");
    writeString(writer, context.mode);
    writer.Key("run_id");
    writeString(writer, run_id_);
    writer.Key("scene_id");
    writeString(writer, context.scene_id);
    writer.Key("source_id");
    writeString(writer, context.source_id);
    writer.Key("sequence");
    if (admission.pose) {
        writer.Int64(admission.pose->sequence);
    } else {
        writer.Null();
    }
    writer.Key("calibration_version");
    if (admission.pose) {
        writeString(writer, admission.pose->calibration_version);
    } else {
        writer.Null();
    }
    writer.Key("observation_timestamp");
    writeString(writer, context.observation_timestamp);
    writer.Key("pose_age_s");
    writeOptional(writer, admission.pose_age_s);
    writer.Key("timestamp_uncertainty_s");
    writeOptional(writer, admission.timestamp_uncertainty_s);
    writer.Key("dwell_elapsed_s");
    writeOptional(writer, admission.dwell_elapsed_s);
    writer.Key("admitted");
    writer.Bool(admission.admitted);
    writer.Key("managed");
    writer.Bool(admission.managed);
    writer.Key("invalid_reason");
    if (admission.invalid_reason == InvalidReason::None) {
        writer.Null();
    } else {
        writer.String(toString(admission.invalid_reason));
    }
    writer.Key("reason_detail");
    if (admission.reason_detail == ReasonDetail::None) {
        writer.Null();
    } else {
        writer.String(toString(admission.reason_detail));
    }
    writer.Key("detections");
    writeDetections(writer, detections);
    writer.EndObject();
    return {buffer.GetString(), buffer.GetSize()};
}

SummaryRecorder::SummaryRecorder(int sample_every_n, LineSink sink)
    : sample_every_n_(static_cast<uint64_t>(std::max(sample_every_n, 1))),
      sink_(sink ? std::move(sink) : defaultInfoSink()) {}

bool SummaryRecorder::record(const DecisionContext& context, const PtzAdmission& admission,
                             const ResidualSource* residuals) {
    std::string line;
    {
        std::lock_guard lock(mutex_);
        const std::string source_id(context.source_id);
        const auto since_ns = admission.stationary_since_ns;
        auto applied = applied_.find(source_id);
        if (admission.admitted && since_ns &&
            (applied == applied_.end() || applied->second != *since_ns)) {
            applied_[source_id] = *since_ns;
            line = summary(context, admission, periods_[source_id]);
            periods_[source_id] = Period{};
        }
        add(periods_[source_id], context, admission, residuals);
    }
    if (line.empty()) {
        return false;
    }
    sink_(line);
    return true;
}

void SummaryRecorder::add(Period& period, const DecisionContext& context,
                          const PtzAdmission& admission, const ResidualSource* residuals) const {
    if (context.observation_ns) {
        if (!period.first_ns) {
            period.first_ns = context.observation_ns;
        }
        period.last_ns = context.observation_ns;
    }
    const std::string key = decisionKey(admission);
    auto it = std::find_if(period.decisions.begin(), period.decisions.end(),
                           [&key](const auto& entry) { return entry.first == key; });
    if (it == period.decisions.end()) {
        period.decisions.emplace_back(key, 1);
    } else {
        ++it->second;
    }
    period.detections += context.detection_count;
    if (!admission.admitted) {
        return;
    }
    period.admitted_detections += context.detection_count;
    if (residuals && period.admitted_decisions++ % sample_every_n_ == 0) {
        for (const auto& detection : residuals->compute()) {
            if (period.residuals.size() == kMaxSummarySamples) {
                period.residuals.pop_front();
            }
            period.residuals.push_back(detection.residual_m);
        }
    }
}

std::string SummaryRecorder::summary(const DecisionContext& context, const PtzAdmission& admission,
                                     const Period& period) const {
    std::string offset = "offset from home unknown";
    if (context.home_pose && admission.pose && admission.pose->view) {
        const auto [rotation, translation] =
            offsetFromHome(*context.home_pose, *admission.pose->view);
        offset = std::format("{:.2f} deg from home", rotation);
        if (translation >= kTranslationReportM) {
            offset += std::format(", {:.3f} m from home position", translation);
        }
    }
    const std::string calibration = admission.pose ? admission.pose->calibration_version : "None";
    return std::format("PTZ camera {}: pose applied ({}); {}, dwell {} s, pose age {} s; "
                       "calibration={}; {}",
                       context.source_id, context.mode, offset,
                       number(admission.dwell_elapsed_s, 1), number(admission.pose_age_s, 2),
                       calibration, period.describe());
}

std::string SummaryRecorder::Period::describe() const {
    uint64_t total = 0;
    uint64_t admitted = 0;
    for (const auto& [key, count] : decisions) {
        total += count;
        if (key == kAdmittedKey) {
            admitted = count;
        }
    }
    if (total == 0) {
        return "no earlier decisions";
    }
    std::string duration;
    if (first_ns && last_ns) {
        duration = std::format(" {:.1f} s", static_cast<double>(*last_ns - *first_ns) / 1e9);
    }
    std::string text =
        std::format("previous{}: {} decisions, {:.0f}% admitted", duration, total,
                    100.0 * static_cast<double>(admitted) / static_cast<double>(total));

    auto ordered = decisions;
    std::stable_sort(ordered.begin(), ordered.end(),
                     [](const auto& a, const auto& b) { return a.second > b.second; });
    std::string rejected;
    for (const auto& [key, count] : ordered) {
        if (key == kAdmittedKey) {
            continue;
        }
        rejected += (rejected.empty() ? "" : ", ") + std::format("{} {}", key, count);
    }
    if (!rejected.empty()) {
        text += " (rejected: " + rejected + ")";
    }
    text += std::format(", {} detections ({} admitted)", detections, admitted_detections);
    if (!residuals.empty()) {
        std::vector<double> sorted(residuals.begin(), residuals.end());
        std::sort(sorted.begin(), sorted.end());
        text += std::format(", residual median {:.2f} m, p95 {:.2f} m, max {:.2f} m",
                            percentile(sorted, 0.5), percentile(sorted, 0.95), sorted.back());
    }
    return text;
}

std::pair<double, double> offsetFromHome(const PoseView& home, const PoseView& applied) {
    const cv::Matx33d relative = home.rotation.t() * applied.rotation;
    const double trace = relative(0, 0) + relative(1, 1) + relative(2, 2);
    const double cosine = std::clamp((trace - 1.0) / 2.0, -1.0, 1.0);
    const double rotation_deg = std::acos(cosine) * 180.0 / std::numbers::pi;
    const cv::Point3d delta = applied.origin - home.origin;
    return {rotation_deg, std::sqrt(delta.dot(delta))};
}

double percentile(const std::vector<double>& sorted, double q) {
    if (sorted.empty()) {
        return 0.0;
    }
    const double position = q * static_cast<double>(sorted.size() - 1);
    const auto lower = static_cast<size_t>(std::floor(position));
    const auto upper = static_cast<size_t>(std::ceil(position));
    return sorted[lower] +
           (sorted[upper] - sorted[lower]) * (position - static_cast<double>(lower));
}

} // namespace tracker::ptz
