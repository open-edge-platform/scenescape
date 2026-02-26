// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "config_loader.hpp"

#include <atomic>
#include <memory>

#include <opentelemetry/sdk/metrics/push_metric_exporter.h>

namespace tracker {

/**
 * @brief Manages OpenTelemetry SDK lifecycle (metrics and tracing providers).
 *
 * Initializes global MeterProvider and TracerProvider based on configuration.
 * When disabled, leaves the default no-op providers in place so all OTel API
 * calls throughout the codebase become zero-cost no-ops.
 *
 * Threading: init() and shutdown() are NOT thread-safe and must be called
 * from a single thread (the main thread). After init() completes, the global
 * providers and the query methods (metrics_enabled(), tracing_enabled()) are
 * safe to use from any thread.
 */
class Telemetry {
public:
    /**
     * @brief Initialize OpenTelemetry SDK based on configuration.
     *
     * - If metrics enabled: creates MeterProvider with PeriodicExportingMetricReader
     *   and OtlpGrpcMetricExporter, sets as global provider.
     * - If tracing enabled: creates TracerProvider with BatchSpanProcessor
     *   and OtlpGrpcSpanExporter, sets as global provider.
     * - If neither enabled: no-op (default providers remain).
     *
     * @param config Service configuration containing observability and OTLP settings.
     * @param exporter Optional custom metric exporter (for testing). When null, creates
     *                 the default OtlpGrpcMetricExporter. When provided, uses the injected
     *                 exporter instead, enabling in-memory testing of the metrics pipeline.
     * @throws std::runtime_error if init() has already been called.
     */
    static void
    init(const ServiceConfig& config,
         std::unique_ptr<opentelemetry::sdk::metrics::PushMetricExporter> exporter = nullptr);

    /**
     * @brief Gracefully shut down OpenTelemetry SDK.
     *
     * Flushes pending telemetry data and resets global providers to no-op.
     * Safe to call even if init() was not called or telemetry was disabled.
     */
    static void shutdown();

    /// @return true if metrics provider was initialized
    static bool metrics_enabled();

    /// @return true if tracing provider was initialized
    static bool tracing_enabled();

private:
    static std::atomic<bool> metrics_initialized_;
    static std::atomic<bool> tracing_initialized_;
};

} // namespace tracker
