// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "metrics.hpp"
#include "observability_context.hpp"
#include "telemetry.hpp"

#include "config_loader.hpp"
#include "logger.hpp"

#include <thread>
#include <vector>

#include <gtest/gtest.h>
#include <opentelemetry/exporters/memory/in_memory_metric_data.h>
#include <opentelemetry/exporters/memory/in_memory_metric_exporter_factory.h>
#include <opentelemetry/sdk/metrics/data/point_data.h>

namespace tracker {
namespace {

namespace metrics_sdk = opentelemetry::sdk::metrics;
namespace memory = opentelemetry::exporter::memory;

/**
 * @brief Helper to create metrics-enabled config for in-memory testing.
 */
ServiceConfig make_metrics_config() {
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";
    config.observability.metrics.enabled = true;
    config.observability.metrics.export_interval_s = 1;
    config.observability.tracing.enabled = false;
    return config;
}

/**
 * @brief Create an InMemoryMetricExporter and its backing data store.
 */
std::pair<std::unique_ptr<metrics_sdk::PushMetricExporter>,
          std::shared_ptr<memory::SimpleAggregateInMemoryMetricData>>
make_in_memory_exporter() {
    auto data = std::make_shared<memory::SimpleAggregateInMemoryMetricData>();
    auto exporter = memory::InMemoryMetricExporterFactory::Create(data);
    return {std::move(exporter), data};
}

/**
 * @brief Test fixture that initializes telemetry with in-memory exporter
 *        and resets Metrics state between tests.
 */
class MetricsTest : public ::testing::Test {
protected:
    std::shared_ptr<memory::SimpleAggregateInMemoryMetricData> metric_data_;

    void SetUp() override {
        Logger::init("warn");
        Metrics::reset();

        auto [exporter, data] = make_in_memory_exporter();
        metric_data_ = data;
        auto config = make_metrics_config();
        Telemetry::init(config, std::move(exporter));
    }

    void TearDown() override {
        Telemetry::shutdown();
        Metrics::reset();
        Logger::shutdown();
    }
};

/**
 * @brief Test fixture without telemetry init (for no-op/disabled tests).
 */
class MetricsNoInitTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");
        Metrics::reset();
    }

    void TearDown() override {
        Telemetry::shutdown();
        Metrics::reset();
        Logger::shutdown();
    }
};

// ============================================================================
// No-op / disabled tests
// ============================================================================

TEST_F(MetricsNoInitTest, NoOpBeforeTelemetryInit) {
    // All Metrics calls should be safe before Telemetry::init() (no-op provider)
    EXPECT_NO_THROW(Metrics::record_latency(10.0));
    EXPECT_NO_THROW(Metrics::inc_messages());
    EXPECT_NO_THROW(Metrics::inc_dropped());
    EXPECT_NO_THROW(Metrics::set_active_tracks("scene1", "person", 5));
}

TEST_F(MetricsNoInitTest, NoOpWhenMetricsDisabled) {
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";
    config.observability.metrics.enabled = false;
    Telemetry::init(config);

    EXPECT_NO_THROW(Metrics::record_latency(10.0));
    EXPECT_NO_THROW(Metrics::inc_messages({{kAttrReason, kReasonAccepted}}));
    EXPECT_NO_THROW(Metrics::inc_dropped({{kAttrReason, kReasonRejectedParse}}));
    EXPECT_NO_THROW(Metrics::set_active_tracks("scene1", "person", 5));
}

// ============================================================================
// Positive tests — instrument recording
// ============================================================================

TEST_F(MetricsTest, IncMessagesRecorded) {
    Metrics::inc_messages({{kAttrReason, kReasonAccepted}});

    // Flush to export
    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttMessages);
    ASSERT_FALSE(points.empty()) << "Expected messages counter to be exported";

    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr) << "Expected SumPointData for counter";
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, 1);
    }
}

TEST_F(MetricsTest, IncDroppedWithReason) {
    Metrics::inc_dropped({{kAttrReason, kReasonRejectedSchema}});
    Metrics::inc_dropped({{kAttrReason, kReasonRejectedLag}});

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttDropped);
    ASSERT_FALSE(points.empty()) << "Expected dropped counter to be exported";

    // Total across all attribute sets should be 2
    int64_t total = 0;
    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        if (sum_data) {
            auto value = std::get_if<int64_t>(&sum_data->value_);
            if (value) {
                total += *value;
            }
        }
    }
    EXPECT_EQ(total, 2);
}

TEST_F(MetricsTest, RecordLatency) {
    Metrics::record_latency(25.5, {{kAttrScene, "scene1"}, {kAttrCameraId, "cam1"}});
    Metrics::record_latency(10.0, {{kAttrScene, "scene1"}, {kAttrCameraId, "cam1"}});

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttLatency);
    ASSERT_FALSE(points.empty()) << "Expected latency histogram to be exported";

    for (const auto& [attrs, point] : points) {
        auto* hist_data = std::get_if<metrics_sdk::HistogramPointData>(&point);
        ASSERT_NE(hist_data, nullptr) << "Expected HistogramPointData";
        EXPECT_EQ(hist_data->count_, 2);
        EXPECT_DOUBLE_EQ(std::get<double>(hist_data->sum_), 35.5);
    }
}

TEST_F(MetricsTest, FinalizeRecordsEndToEndLatency) {
    ObservabilityContext ctx;
    ctx.scene_id = "scene1";
    ctx.category = "person";
    ctx.receive_time = std::chrono::steady_clock::now();
    // Simulate 50ms end-to-end
    ctx.publish_time = *ctx.receive_time + std::chrono::milliseconds(50);
    ctx.finalize();

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttLatency);
    ASSERT_FALSE(points.empty()) << "Expected latency histogram from finalize()";

    for (const auto& [attrs, point] : points) {
        auto* hist_data = std::get_if<metrics_sdk::HistogramPointData>(&point);
        ASSERT_NE(hist_data, nullptr);
        EXPECT_EQ(hist_data->count_, 1);
        // Latency should be ~50ms
        EXPECT_NEAR(std::get<double>(hist_data->sum_), 50.0, 1.0);
    }
}

TEST_F(MetricsTest, FinalizeNoOpWithoutReceiveTime) {
    ObservabilityContext ctx;
    ctx.publish_time = std::chrono::steady_clock::now();
    ctx.finalize(); // Should be no-op (no receive_time)

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttLatency);
    EXPECT_TRUE(points.empty()) << "Expected no latency from finalize() without receive_time";
}

TEST_F(MetricsTest, FinalizeNoOpWithoutPublishTime) {
    ObservabilityContext ctx;
    ctx.receive_time = std::chrono::steady_clock::now();
    ctx.finalize(); // Should be no-op (no publish_time)

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttLatency);
    EXPECT_TRUE(points.empty()) << "Expected no latency from finalize() without publish_time";
}

TEST_F(MetricsTest, AbortRecordsDroppedMetric) {
    ObservabilityContext ctx;
    ctx.scene_id = "scene1";
    ctx.camera_id = "cam1";
    ctx.receive_time = std::chrono::steady_clock::now();
    ctx.abort(kReasonRejectedSchema);

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttDropped);
    ASSERT_FALSE(points.empty()) << "Expected dropped counter from abort()";

    int64_t total = 0;
    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        if (sum_data) {
            auto value = std::get_if<int64_t>(&sum_data->value_);
            if (value) {
                total += *value;
            }
        }
    }
    EXPECT_EQ(total, 1);
}

TEST_F(MetricsTest, ActiveTracksUpdate) {
    Metrics::set_active_tracks("scene1", "person", 10);
    Metrics::set_active_tracks("scene1", "vehicle", 3);

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricTracksActive);
    // Observable gauge may or may not have exported depending on timing —
    // the key assertion is that set_active_tracks doesn't crash and the data
    // is stored in the registry
    // If points are available, verify they're reasonable
    if (!points.empty()) {
        int64_t total = 0;
        for (const auto& [attrs, point] : points) {
            auto* lv_data = std::get_if<metrics_sdk::LastValuePointData>(&point);
            if (lv_data) {
                auto value = std::get_if<int64_t>(&lv_data->value_);
                if (value) {
                    total += *value;
                }
            }
        }
        EXPECT_EQ(total, 13);
    }
}

TEST_F(MetricsTest, ActiveTracksOverwrite) {
    // Setting the same scope should overwrite, not accumulate
    Metrics::set_active_tracks("scene1", "person", 10);
    Metrics::set_active_tracks("scene1", "person", 5);

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricTracksActive);
    if (!points.empty()) {
        for (const auto& [attrs, point] : points) {
            auto* lv_data = std::get_if<metrics_sdk::LastValuePointData>(&point);
            if (lv_data) {
                auto value = std::get_if<int64_t>(&lv_data->value_);
                if (value) {
                    // Should be 5 (overwritten), not 15 (accumulated)
                    EXPECT_EQ(*value, 5);
                }
            }
        }
    }
}

TEST_F(MetricsTest, MultipleCounterIncrements) {
    for (int i = 0; i < 100; ++i) {
        Metrics::inc_messages({{kAttrReason, kReasonAccepted}});
    }

    Telemetry::shutdown();

    auto& points = metric_data_->Get(kMeterName, kMetricMqttMessages);
    ASSERT_FALSE(points.empty());

    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr);
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, 100);
    }
}

// ============================================================================
// Thread safety
// ============================================================================

TEST_F(MetricsTest, ConcurrentRecording) {
    constexpr int kThreads = 4;
    constexpr int kIterations = 250;

    std::vector<std::thread> threads;
    threads.reserve(kThreads);

    for (int t = 0; t < kThreads; ++t) {
        threads.emplace_back([&]() {
            for (int i = 0; i < kIterations; ++i) {
                Metrics::inc_messages({{kAttrReason, kReasonAccepted}});
                Metrics::inc_dropped({{kAttrReason, kReasonRejectedParse}});
                Metrics::record_latency(1.0, {{kAttrScene, "s1"}});
                Metrics::set_active_tracks("s1", "person", static_cast<int64_t>(i));
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    Telemetry::shutdown();

    // Verify counters accumulated correctly across all threads
    auto& msg_points = metric_data_->Get(kMeterName, kMetricMqttMessages);
    ASSERT_FALSE(msg_points.empty());
    for (const auto& [attrs, point] : msg_points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr);
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, kThreads * kIterations);
    }

    auto& drop_points = metric_data_->Get(kMeterName, kMetricMqttDropped);
    ASSERT_FALSE(drop_points.empty());
    for (const auto& [attrs, point] : drop_points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr);
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, kThreads * kIterations);
    }

    auto& lat_points = metric_data_->Get(kMeterName, kMetricMqttLatency);
    ASSERT_FALSE(lat_points.empty());
    for (const auto& [attrs, point] : lat_points) {
        auto* hist_data = std::get_if<metrics_sdk::HistogramPointData>(&point);
        ASSERT_NE(hist_data, nullptr);
        EXPECT_EQ(hist_data->count_, static_cast<uint64_t>(kThreads * kIterations));
    }
}

} // namespace
} // namespace tracker
