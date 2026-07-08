// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "metrics.hpp"

#include <cstring>
#include <mutex>

#include <opentelemetry/metrics/meter.h>
#include <opentelemetry/metrics/provider.h>

namespace tracker {

namespace metrics_api = opentelemetry::metrics;

namespace {

// Instrument pointers (lazily initialized, process-lifetime)
std::once_flag init_flag;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> latency_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> messages_counter;
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> dropped_counter;
opentelemetry::nostd::shared_ptr<metrics_api::ObservableInstrument> active_tracks_gauge;

// Time-chunking performance counters
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> tc_duplicated_cameras_counter;
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> tc_unique_cameras_counter;
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> tc_non_empty_chunks_counter;
opentelemetry::nostd::unique_ptr<metrics_api::Counter<uint64_t>> tc_empty_chunks_counter;

// Per-stage latency histograms
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_parse_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_buffer_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_queue_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_transform_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_track_histogram;
opentelemetry::nostd::unique_ptr<metrics_api::Histogram<double>> stage_publish_histogram;

/**
 * @brief Get the histogram for a given metric name.
 * @param metric_name One of kMetricStageXxx constants
 * @return Reference to the corresponding histogram unique_ptr
 * @throws std::invalid_argument if metric_name is not recognized
 */
metrics_api::Histogram<double>& get_histogram(const char* metric_name) {
    if (std::strcmp(metric_name, kMetricStageParse) == 0) {
        return *stage_parse_histogram;
    } else if (std::strcmp(metric_name, kMetricStageBuffer) == 0) {
        return *stage_buffer_histogram;
    } else if (std::strcmp(metric_name, kMetricStageQueue) == 0) {
        return *stage_queue_histogram;
    } else if (std::strcmp(metric_name, kMetricStageTransform) == 0) {
        return *stage_transform_histogram;
    } else if (std::strcmp(metric_name, kMetricStageTrack) == 0) {
        return *stage_track_histogram;
    } else if (std::strcmp(metric_name, kMetricStagePublish) == 0) {
        return *stage_publish_histogram;
    }
    throw std::invalid_argument("Invalid metric name: " + std::string(metric_name));
}

} // namespace

// Static member definitions
std::mutex Metrics::gauge_mutex_;
std::map<std::string, int64_t> Metrics::active_tracks_;

void Metrics::ensure_initialized() {
    std::call_once(init_flag, []() {
        auto provider = metrics_api::Provider::GetMeterProvider();
#ifdef TRACKER_SERVICE_VERSION
        auto meter = provider->GetMeter(kMeterName, TRACKER_SERVICE_VERSION);
#else
    auto meter = provider->GetMeter(kMeterName);
#endif

        latency_histogram = meter->CreateDoubleHistogram(kMetricMqttLatency,
                                                         "MQTT message processing latency", "ms");

        messages_counter =
            meter->CreateUInt64Counter(kMetricMqttMessages, "MQTT messages received", "{message}");

        dropped_counter =
            meter->CreateUInt64Counter(kMetricMqttDropped, "MQTT messages dropped", "{message}");

        tc_duplicated_cameras_counter = meter->CreateUInt64Counter(
            kMetricTimeChunkingDuplicatedCameras,
            "Time-chunking buffered camera frames overwritten before dispatch", "{message}");
        tc_unique_cameras_counter = meter->CreateUInt64Counter(
            kMetricTimeChunkingUniqueCameras, "Time-chunking unique cameras dispatched per chunk",
            "{camera}");
        tc_non_empty_chunks_counter = meter->CreateUInt64Counter(
            kMetricTimeChunkingNonEmptyChunks,
            "Time-chunking dispatch intervals with buffered data", "{chunk}");
        tc_empty_chunks_counter = meter->CreateUInt64Counter(
            kMetricTimeChunkingEmptyChunks,
            "Time-chunking dispatch intervals with no buffered data", "{chunk}");

        active_tracks_gauge = meter->CreateInt64ObservableGauge(
            kMetricTracksActive, "Currently active tracks", "{track}");

        // Per-stage latency histograms
        stage_parse_histogram = meter->CreateDoubleHistogram(
            kMetricStageParse, "JSON parse and schema validation duration", "ms");
        stage_buffer_histogram = meter->CreateDoubleHistogram(
            kMetricStageBuffer, "Scene lookup, lag check, buffer insertion duration", "ms");
        stage_queue_histogram = meter->CreateDoubleHistogram(
            kMetricStageQueue, "Time waiting in chunk buffer for scheduler", "ms");
        stage_transform_histogram = meter->CreateDoubleHistogram(
            kMetricStageTransform, "Coordinate transformation duration", "ms");
        stage_track_histogram = meter->CreateDoubleHistogram(
            kMetricStageTrack, "Hungarian matching and Kalman filter duration", "ms");
        stage_publish_histogram = meter->CreateDoubleHistogram(
            kMetricStagePublish, "MQTT serialize and publish duration", "ms");

        active_tracks_gauge->AddCallback(
            [](metrics_api::ObserverResult result, void* /* state */) {
                std::lock_guard<std::mutex> lock(gauge_mutex_);
                for (const auto& [key, count] : active_tracks_) {
                    // Parse "scene_id/category" back to attributes
                    auto sep = key.find('/');
                    if (sep != std::string::npos) {
                        std::string scene_id = key.substr(0, sep);
                        std::string category = key.substr(sep + 1);

                        auto observer = opentelemetry::nostd::get<opentelemetry::nostd::shared_ptr<
                            metrics_api::ObserverResultT<int64_t>>>(result);
                        if (observer) {
                            observer->Observe(count, {{kAttrScene, scene_id.c_str()},
                                                      {kAttrCategory, category.c_str()}});
                        }
                    }
                }
            },
            nullptr);
    });
}

void Metrics::record_latency(double ms, MetricAttributes attrs) {
    ensure_initialized();
    if (latency_histogram) {
        latency_histogram->Record(
            ms, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
            opentelemetry::context::Context{});
    }
}

void Metrics::record_stage_latency(const char* metric_name, double ms, MetricAttributes attrs) {
    ensure_initialized();

    try {
        auto& hist = get_histogram(metric_name);
        hist.Record(ms, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
                    opentelemetry::context::Context{});
    } catch (const std::invalid_argument&) {
        // Silently ignore invalid metric names in production
    }
}

void Metrics::inc_messages(MetricAttributes attrs) {
    ensure_initialized();
    if (messages_counter) {
        messages_counter->Add(1,
                              opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
                              opentelemetry::context::Context{});
    }
}

void Metrics::inc_dropped(MetricAttributes attrs) {
    ensure_initialized();
    if (dropped_counter) {
        dropped_counter->Add(1,
                             opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
                             opentelemetry::context::Context{});
    }
}

void Metrics::inc_dropped_n(size_t count, MetricAttributes attrs) {
    if (count == 0) {
        return;
    }
    ensure_initialized();
    if (dropped_counter) {
        dropped_counter->Add(count,
                             opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
                             opentelemetry::context::Context{});
    }
}

void Metrics::inc_time_chunking_duplicated_cameras(MetricAttributes attrs) {
    ensure_initialized();
    if (tc_duplicated_cameras_counter) {
        tc_duplicated_cameras_counter->Add(
            1, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
            opentelemetry::context::Context{});
    }
}

void Metrics::inc_time_chunking_unique_cameras_n(size_t count, MetricAttributes attrs) {
    if (count == 0) {
        return;
    }
    ensure_initialized();
    if (tc_unique_cameras_counter) {
        tc_unique_cameras_counter->Add(
            count, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
            opentelemetry::context::Context{});
    }
}

void Metrics::inc_time_chunking_non_empty_chunks(MetricAttributes attrs) {
    ensure_initialized();
    if (tc_non_empty_chunks_counter) {
        tc_non_empty_chunks_counter->Add(
            1, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
            opentelemetry::context::Context{});
    }
}

void Metrics::inc_time_chunking_empty_chunks(MetricAttributes attrs) {
    ensure_initialized();
    if (tc_empty_chunks_counter) {
        tc_empty_chunks_counter->Add(
            1, opentelemetry::common::KeyValueIterableView<MetricAttributes>(attrs),
            opentelemetry::context::Context{});
    }
}

void Metrics::set_active_tracks(const std::string& scene_id, const std::string& category,
                                int64_t count) {
    ensure_initialized();
    std::string key = scene_id + "/" + category;
    std::lock_guard<std::mutex> lock(gauge_mutex_);
    active_tracks_[key] = count;
}

void Metrics::reset() {
    // Reset the once_flag using std::destroy_at and std::construct_at for safety
    std::destroy_at(&init_flag);
    std::construct_at(&init_flag);

    // Clear instrument pointers
    latency_histogram = nullptr;
    messages_counter = nullptr;
    dropped_counter = nullptr;
    active_tracks_gauge = nullptr;
    tc_duplicated_cameras_counter = nullptr;
    tc_unique_cameras_counter = nullptr;
    tc_non_empty_chunks_counter = nullptr;
    tc_empty_chunks_counter = nullptr;
    stage_parse_histogram = nullptr;
    stage_buffer_histogram = nullptr;
    stage_queue_histogram = nullptr;
    stage_track_histogram = nullptr;
    stage_publish_histogram = nullptr;

    // Clear gauge state
    std::lock_guard<std::mutex> lock(gauge_mutex_);
    active_tracks_.clear();
}

} // namespace tracker
