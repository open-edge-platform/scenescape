// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "metrics.hpp"

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

        active_tracks_gauge = meter->CreateInt64ObservableGauge(
            kMetricTracksActive, "Currently active tracks", "{track}");

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

void Metrics::set_active_tracks(const std::string& scene_id, const std::string& category,
                                int64_t count) {
    ensure_initialized();
    std::string key = scene_id + "/" + category;
    std::lock_guard<std::mutex> lock(gauge_mutex_);
    active_tracks_[key] = count;
}

void Metrics::reset() {
    // Reset the once_flag by replacing it (C++ doesn't allow resetting std::once_flag,
    // so we use placement new to reconstruct it in-place)
    init_flag.~once_flag();
    new (&init_flag) std::once_flag();

    // Clear instrument pointers
    latency_histogram = nullptr;
    messages_counter = nullptr;
    dropped_counter = nullptr;
    active_tracks_gauge = nullptr;

    // Clear gauge state
    std::lock_guard<std::mutex> lock(gauge_mutex_);
    active_tracks_.clear();
}

} // namespace tracker
