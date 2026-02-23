// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "telemetry.hpp"

#include "config_loader.hpp"
#include "logger.hpp"

#include <gtest/gtest.h>
#include <opentelemetry/exporters/memory/in_memory_metric_data.h>
#include <opentelemetry/exporters/memory/in_memory_metric_exporter_factory.h>
#include <opentelemetry/metrics/provider.h>
#include <opentelemetry/sdk/metrics/data/point_data.h>
#include <opentelemetry/sdk/metrics/meter_provider.h>
#include <opentelemetry/trace/provider.h>

namespace tracker {
namespace {

namespace metrics_sdk = opentelemetry::sdk::metrics;
namespace memory = opentelemetry::exporter::memory;

/**
 * @brief Helper to build a minimal ServiceConfig with telemetry settings.
 */
ServiceConfig make_config(bool metrics_enabled, bool tracing_enabled,
                          const std::string& endpoint = "localhost:4317") {
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";

    config.observability.metrics.enabled = metrics_enabled;
    config.observability.metrics.export_interval_s = 60;
    config.observability.tracing.enabled = tracing_enabled;
    config.observability.tracing.export_interval_s = 5;

    if (metrics_enabled || tracing_enabled) {
        OtlpConfig otlp;
        otlp.endpoint = endpoint;
        otlp.insecure = true;
        config.infrastructure.otlp = otlp;
    }

    return config;
}

/**
 * @brief Helper to create a metrics config suitable for in-memory testing.
 *
 * Uses short export interval (1s) and no OTLP endpoint since the exporter
 * is injected directly.
 */
ServiceConfig make_inmemory_config() {
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";
    config.observability.metrics.enabled = true;
    config.observability.metrics.export_interval_s = 1;
    config.observability.tracing.enabled = false;
    // No OTLP config needed — exporter is injected
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
 * @brief Ensure clean state after each test by shutting down telemetry.
 */
class TelemetryTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override {
        Telemetry::shutdown();
        Logger::shutdown();
    }
};

// ============================================================================
// OTel SDK lifecycle
// ============================================================================

TEST_F(TelemetryTest, DisabledByDefault) {
    auto config = make_config(false, false);
    Telemetry::init(config);

    EXPECT_FALSE(Telemetry::metrics_enabled());
    EXPECT_FALSE(Telemetry::tracing_enabled());
}

TEST_F(TelemetryTest, MetricsEnabledSetsGlobalProvider) {
    auto config = make_config(true, false);
    Telemetry::init(config);

    EXPECT_TRUE(Telemetry::metrics_enabled());
    EXPECT_FALSE(Telemetry::tracing_enabled());

    // Global provider should be set (non-null)
    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    EXPECT_NE(provider, nullptr);
}

TEST_F(TelemetryTest, TracingEnabledSetsGlobalProvider) {
    auto config = make_config(false, true);
    Telemetry::init(config);

    EXPECT_FALSE(Telemetry::metrics_enabled());
    EXPECT_TRUE(Telemetry::tracing_enabled());

    // Global provider should be set (non-null)
    auto provider = opentelemetry::trace::Provider::GetTracerProvider();
    EXPECT_NE(provider, nullptr);
}

TEST_F(TelemetryTest, BothEnabled) {
    auto config = make_config(true, true);
    Telemetry::init(config);

    EXPECT_TRUE(Telemetry::metrics_enabled());
    EXPECT_TRUE(Telemetry::tracing_enabled());
}

TEST_F(TelemetryTest, ShutdownResetsState) {
    auto config = make_config(true, true);
    Telemetry::init(config);

    ASSERT_TRUE(Telemetry::metrics_enabled());
    ASSERT_TRUE(Telemetry::tracing_enabled());

    Telemetry::shutdown();

    EXPECT_FALSE(Telemetry::metrics_enabled());
    EXPECT_FALSE(Telemetry::tracing_enabled());
}

TEST_F(TelemetryTest, ShutdownWithoutInitIsSafe) {
    // Should not throw or crash
    Telemetry::shutdown();

    EXPECT_FALSE(Telemetry::metrics_enabled());
    EXPECT_FALSE(Telemetry::tracing_enabled());
}

TEST_F(TelemetryTest, DoubleInitThrows) {
    auto config = make_config(true, true);
    Telemetry::init(config);
    // Second init should throw — init() must only be called once
    EXPECT_THROW(Telemetry::init(config), std::runtime_error);

    EXPECT_TRUE(Telemetry::metrics_enabled());
    EXPECT_TRUE(Telemetry::tracing_enabled());
}

TEST_F(TelemetryTest, MetricsEnabledWithoutOtlpDisabled) {
    // Metrics enabled but no OTLP config → should warn and stay disabled
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";
    config.observability.metrics.enabled = true;
    // No otlp configured

    Telemetry::init(config);

    EXPECT_FALSE(Telemetry::metrics_enabled());
}

TEST_F(TelemetryTest, TracingEnabledWithoutOtlpDisabled) {
    // Tracing enabled but no OTLP config → should warn and stay disabled
    ServiceConfig config;
    config.infrastructure.mqtt.host = "localhost";
    config.infrastructure.mqtt.port = 1883;
    config.infrastructure.mqtt.insecure = true;
    config.scenes.source = SceneSource::File;
    config.scenes.file_path = "scenes.json";
    config.observability.tracing.enabled = true;
    // No otlp configured

    Telemetry::init(config);

    EXPECT_FALSE(Telemetry::tracing_enabled());
}

// ============================================================================
// Metric data assertions via InMemoryMetricExporter
// ============================================================================

TEST_F(TelemetryTest, CounterRecordedViaInMemoryExporter) {
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_inmemory_config();
    Telemetry::init(config, std::move(exporter));

    // Create a counter and record a value
    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto counter = meter->CreateUInt64Counter("test.counter", "test counter", "{count}");
    counter->Add(5);

    // Force flush to export data
    Telemetry::shutdown();

    // Assert the counter value was exported
    auto& points = data->Get("test_meter", "test.counter");
    ASSERT_FALSE(points.empty()) << "Expected counter data to be exported";

    // Check that the sum point data contains our value
    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr) << "Expected SumPointData for counter";
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, 5);
    }
}

TEST_F(TelemetryTest, HistogramRecordedViaInMemoryExporter) {
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_inmemory_config();
    Telemetry::init(config, std::move(exporter));

    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto histogram = meter->CreateDoubleHistogram("test.histogram", "test histogram", "ms");
    histogram->Record(42.0, {});

    Telemetry::shutdown();

    auto& points = data->Get("test_meter", "test.histogram");
    ASSERT_FALSE(points.empty()) << "Expected histogram data to be exported";

    for (const auto& [attrs, point] : points) {
        auto* hist_data = std::get_if<metrics_sdk::HistogramPointData>(&point);
        ASSERT_NE(hist_data, nullptr) << "Expected HistogramPointData";
        EXPECT_EQ(hist_data->count_, 1);
        EXPECT_DOUBLE_EQ(std::get<double>(hist_data->sum_), 42.0);
    }
}

TEST_F(TelemetryTest, CounterWithAttributesRecorded) {
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_inmemory_config();
    Telemetry::init(config, std::move(exporter));

    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto counter = meter->CreateUInt64Counter("test.attr_counter", "test", "{count}");

    std::map<std::string, std::string> attrs = {{"scene", "s1"}, {"status", "accepted"}};
    counter->Add(1, opentelemetry::common::KeyValueIterableView<decltype(attrs)>(attrs));

    Telemetry::shutdown();

    auto& points = data->Get("test_meter", "test.attr_counter");
    ASSERT_FALSE(points.empty()) << "Expected counter with attributes to be exported";
}

TEST_F(TelemetryTest, MultipleRecordingsAccumulate) {
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_inmemory_config();
    Telemetry::init(config, std::move(exporter));

    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto counter = meter->CreateUInt64Counter("test.accum", "test", "{count}");
    counter->Add(3);
    counter->Add(7);

    Telemetry::shutdown();

    auto& points = data->Get("test_meter", "test.accum");
    ASSERT_FALSE(points.empty()) << "Expected accumulated counter data";

    for (const auto& [attrs, point] : points) {
        auto* sum_data = std::get_if<metrics_sdk::SumPointData>(&point);
        ASSERT_NE(sum_data, nullptr);
        auto value = std::get_if<int64_t>(&sum_data->value_);
        ASSERT_NE(value, nullptr);
        EXPECT_EQ(*value, 10);
    }
}

TEST_F(TelemetryTest, InMemoryExporterDisabledMetrics) {
    // When metrics disabled, injected exporter is ignored
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_config(false, false);
    Telemetry::init(config, std::move(exporter));

    // Use the global (no-op) provider — recordings should be no-ops
    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto counter = meter->CreateUInt64Counter("test.noop", "test", "{count}");
    counter->Add(99);

    Telemetry::shutdown();

    // Nothing should have been exported
    auto& points = data->Get("test_meter", "test.noop");
    EXPECT_TRUE(points.empty()) << "Expected no data when metrics are disabled";
}

TEST_F(TelemetryTest, InjectedExporterOverridesOtlp) {
    // Even with OTLP endpoint configured, injected exporter is used
    auto [exporter, data] = make_in_memory_exporter();
    auto config = make_config(true, false); // Has OTLP endpoint
    Telemetry::init(config, std::move(exporter));

    EXPECT_TRUE(Telemetry::metrics_enabled());

    auto provider = opentelemetry::metrics::Provider::GetMeterProvider();
    auto meter = provider->GetMeter("test_meter");
    auto counter = meter->CreateUInt64Counter("test.override", "test", "{count}");
    counter->Add(42);

    Telemetry::shutdown();

    auto& points = data->Get("test_meter", "test.override");
    ASSERT_FALSE(points.empty()) << "Expected data via injected exporter";
}

} // namespace
} // namespace tracker
