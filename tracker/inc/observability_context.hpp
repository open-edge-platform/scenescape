// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <chrono>
#include <optional>
#include <string>

namespace tracker {

/**
 * @brief Per-message observability context propagated through the pipeline.
 *
 * Carries stage timestamps through the processing pipeline:
 *   receive → parse → buffer → dispatch → track → publish
 *
 * End-to-end latency is recorded at pipeline completion via finalize(),
 * or drop metrics are recorded via abort() when a message is rejected.
 *
 * Tracing fields (trace_id, span_id, spans) are declared as stubs for
 * next phase with distributed tracing — only timestamp recording and metric
 * emission are implemented now.
 *
 * Default-constructed context is a valid no-op: finalize() and abort()
 * are safe to call and produce no metrics if receive_time is unset.
 *
 * Thread-safety: not thread-safe. Each context is owned by a single
 * DetectionBatch or Chunk and accessed from one thread at a time.
 */
struct ObservabilityContext {
    // ---- W3C Trace Context stubs (Phase 4) ----
    std::array<uint8_t, 16> trace_id{};
    std::array<uint8_t, 8> span_id{};
    std::string tracestate;

    // ---- Stage timestamps ----
    std::optional<std::chrono::steady_clock::time_point> receive_time;
    std::optional<std::chrono::steady_clock::time_point> parse_time;
    std::optional<std::chrono::steady_clock::time_point> buffer_time;
    std::optional<std::chrono::steady_clock::time_point> dispatch_time;
    std::optional<std::chrono::steady_clock::time_point> transform_time;
    std::optional<std::chrono::steady_clock::time_point> track_time;
    std::optional<std::chrono::steady_clock::time_point> publish_time;

    // ---- Attributes for metric emission ----
    std::string scene_id;
    std::string camera_id;
    std::string category;

    // ---- Timestamp capture helpers ----
    void captureReceiveTime() { receive_time = std::chrono::steady_clock::now(); }
    void captureParseTime() { parse_time = std::chrono::steady_clock::now(); }
    void captureBufferTime() { buffer_time = std::chrono::steady_clock::now(); }
    void captureDispatchTime() { dispatch_time = std::chrono::steady_clock::now(); }
    void captureTransformTime() { transform_time = std::chrono::steady_clock::now(); }
    void captureTrackTime() { track_time = std::chrono::steady_clock::now(); }
    void capturePublishTime() { publish_time = std::chrono::steady_clock::now(); }

    /**
     * @brief Record end-to-end latency metric after successful publish.
     *
     * Computes (publish_time - receive_time) and records it on the
     * tracker.mqtt.latency histogram. No-op if receive_time or
     * publish_time is unset.
     */
    void finalize() const;

    /**
     * @brief Record drop metric when a message is rejected.
     *
     * Increments tracker.mqtt.dropped with the given reason.
     * No-op if receive_time is unset (context was never started).
     *
     * @param reason Drop reason (e.g., kReasonRejectedParse)
     */
    void abort(const char* reason) const;
};

} // namespace tracker
