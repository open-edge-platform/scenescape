// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "telemetry.hpp"

#include "config_loader.hpp"
#include "logger.hpp"

#include <gtest/gtest.h>
#include <opentelemetry/metrics/provider.h>
#include <opentelemetry/trace/provider.h>

namespace tracker {
namespace {

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

} // namespace
} // namespace tracker
