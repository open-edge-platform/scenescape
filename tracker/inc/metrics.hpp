// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <string>

#include <opentelemetry/common/key_value_iterable_view.h>
#include <opentelemetry/metrics/meter.h>
#include <opentelemetry/metrics/meter_provider.h>
#include <opentelemetry/metrics/provider.h>

namespace tracker {

// Attribute key constants
inline constexpr const char* kAttrScene = "scene";
inline constexpr const char* kAttrCategory = "category";
inline constexpr const char* kAttrCameraId = "camera_id";
inline constexpr const char* kAttrReason = "reason";

// Reason attribute values
inline constexpr const char* kReasonAccepted = "accepted";
inline constexpr const char* kReasonRejectedParse = "rejected_parse";
inline constexpr const char* kReasonRejectedSchema = "rejected_schema";
inline constexpr const char* kReasonRejectedUnknownTopic = "rejected_unknown_topic";
inline constexpr const char* kReasonRejectedLag = "rejected_lag";
inline constexpr const char* kReasonRejectedInvalidCategory = "rejected_invalid_category";
inline constexpr const char* kReasonDroppedQueueFull = "dropped_queue_full";
inline constexpr const char* kReasonDroppedMaxWorkers = "dropped_max_workers";

// Metric name constants
inline constexpr const char* kMetricMqttLatency = "tracker.mqtt.latency";
inline constexpr const char* kMetricMqttMessages = "tracker.mqtt.messages";
inline constexpr const char* kMetricMqttDropped = "tracker.mqtt.dropped";
inline constexpr const char* kMetricTracksActive = "tracker.tracks.active";

// Per-stage latency histograms (informational — pipeline breakdown)
inline constexpr const char* kMetricStageParse = "tracker.stage.parse_duration";
inline constexpr const char* kMetricStageBuffer = "tracker.stage.buffer_duration";
inline constexpr const char* kMetricStageQueue = "tracker.stage.queue_duration";
inline constexpr const char* kMetricStageTransform = "tracker.stage.transform_duration";
inline constexpr const char* kMetricStageTrack = "tracker.stage.track_duration";
inline constexpr const char* kMetricStagePublish = "tracker.stage.publish_duration";

// Meter scope name
inline constexpr const char* kMeterName = "tracker";

/**
 * @brief Type alias for metric attributes.
 *
 * Use with initializer list syntax:
 *   Metrics::inc_messages({{kAttrScene, "s1"}, {kAttrReason, kReasonAccepted}})
 */
using MetricAttributes = std::initializer_list<
    std::pair<opentelemetry::nostd::string_view, opentelemetry::common::AttributeValue>>;

/**
 * @brief Singleton metrics registry for tracker service instrumentation.
 *
 * Provides a static API for recording the 4 core metrics:
 * - tracker.mqtt.latency (histogram, ms)
 * - tracker.mqtt.messages (counter)
 * - tracker.mqtt.dropped (counter)
 * - tracker.tracks.active (observable gauge)
 * - tracker.stage.{parse,buffer,queue,transform,track,publish}_duration (histograms, ms)
 *
 * Instruments are created lazily on first use via the global MeterProvider
 * (set by Telemetry::init()). When metrics are disabled, the default no-op
 * provider ensures all calls are zero-cost.
 *
 * Thread-safe: all methods can be called from any thread.
 */
class Metrics {
public:
    /**
     * @brief Record MQTT message processing latency.
     * @param ms Latency in milliseconds
     * @param attrs Attributes (scene, camera_id, etc.)
     */
    static void record_latency(double ms, MetricAttributes attrs = {});

    /**
     * @brief Record a per-stage latency histogram.
     * @param metric_name One of kMetricStage{Parse,Buffer,Queue,Track,Publish}
     * @param ms Duration in milliseconds
     * @param attrs Attributes (scene, camera_id or category)
     */
    static void record_stage_latency(const char* metric_name, double ms,
                                     MetricAttributes attrs = {});

    /**
     * @brief Increment the received messages counter.
     * @param attrs Attributes (scene, camera_id, status, etc.)
     */
    static void inc_messages(MetricAttributes attrs = {});

    /**
     * @brief Increment the dropped messages counter by 1.
     * @param attrs Attributes (scene, camera_id, status, etc.)
     */
    static void inc_dropped(MetricAttributes attrs = {});

    /**
     * @brief Increment the dropped messages counter by N.
     *
     * Used when an entire chunk (containing multiple camera batches)
     * is dropped due to queue overflow or worker limits.
     *
     * @param count Number of messages dropped
     * @param attrs Attributes (scene, category, reason, etc.)
     */
    static void inc_dropped_n(size_t count, MetricAttributes attrs = {});

    /**
     * @brief Update the active track count for a given scope.
     *
     * Stores the count in a thread-safe registry. The observable gauge
     * callback reads these values at export time.
     *
     * @param scene_id Scene identifier
     * @param category Object category
     * @param count Number of active tracks
     */
    static void set_active_tracks(const std::string& scene_id, const std::string& category,
                                  int64_t count);

    /**
     * @brief Reset all cached instruments and gauge state.
     *
     * Called during testing to ensure clean state between tests.
     * Not needed in production (instruments are process-lifetime).
     */
    static void reset();

private:
    static void ensure_initialized();

    // Gauge callback registry: {scene_id + "/" + category} -> track count
    static std::mutex gauge_mutex_;
    static std::map<std::string, int64_t> active_tracks_;
};

} // namespace tracker
