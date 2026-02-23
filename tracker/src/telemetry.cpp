// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "telemetry.hpp"

#include "logger.hpp"

#include <opentelemetry/exporters/otlp/otlp_grpc_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_grpc_exporter_options.h>
#include <opentelemetry/exporters/otlp/otlp_grpc_metric_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_grpc_metric_exporter_options.h>
#include <opentelemetry/metrics/noop.h>
#include <opentelemetry/metrics/provider.h>
#include <opentelemetry/sdk/metrics/export/periodic_exporting_metric_reader_factory.h>
#include <opentelemetry/sdk/metrics/export/periodic_exporting_metric_reader_options.h>
#include <opentelemetry/sdk/metrics/meter_provider.h>
#include <opentelemetry/sdk/metrics/meter_provider_factory.h>
#include <opentelemetry/sdk/metrics/view/view_registry_factory.h>
#include <opentelemetry/sdk/resource/semantic_conventions.h>
#include <opentelemetry/sdk/trace/batch_span_processor_factory.h>
#include <opentelemetry/sdk/trace/batch_span_processor_options.h>
#include <opentelemetry/sdk/trace/tracer_provider.h>
#include <opentelemetry/sdk/trace/tracer_provider_factory.h>
#include <opentelemetry/trace/noop.h>
#include <opentelemetry/trace/provider.h>

#include <opentelemetry/sdk/resource/resource.h>

namespace tracker {

namespace {
namespace resource = opentelemetry::sdk::resource;
namespace metrics_sdk = opentelemetry::sdk::metrics;
namespace trace_sdk = opentelemetry::sdk::trace;
namespace otlp = opentelemetry::exporter::otlp;
namespace metrics_api = opentelemetry::metrics;
namespace trace_api = opentelemetry::trace;

constexpr const char* kServiceName = "scenescape-tracker";

resource::Resource build_resource() {
    return resource::Resource::Create({
        {resource::SemanticConventions::kServiceName, kServiceName},
        {resource::SemanticConventions::kServiceVersion, TRACKER_SERVICE_VERSION},
    });
}
} // namespace

std::atomic<bool> Telemetry::metrics_initialized_{false};
std::atomic<bool> Telemetry::tracing_initialized_{false};

void Telemetry::init(const ServiceConfig& config) {
    // Guard against double initialization — init() must only be called once from main()
    if (metrics_initialized_ || tracing_initialized_) {
        throw std::runtime_error("Telemetry::init() called more than once");
    }

    const auto& obs = config.observability;
    const auto& otlp_config = config.infrastructure.otlp;

    // Metrics initialization
    if (obs.metrics.enabled) {
        if (!otlp_config.has_value()) {
            LOG_WARN("Metrics enabled but infrastructure.otlp not configured — metrics disabled");
        } else {
            otlp::OtlpGrpcMetricExporterOptions exporter_opts;
            exporter_opts.endpoint = otlp_config->endpoint;
            exporter_opts.use_ssl_credentials = !otlp_config->insecure;

            auto exporter = otlp::OtlpGrpcMetricExporterFactory::Create(exporter_opts);

            metrics_sdk::PeriodicExportingMetricReaderOptions reader_opts;
            reader_opts.export_interval_millis =
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::seconds(obs.metrics.export_interval_s));
            reader_opts.export_timeout_millis = std::chrono::milliseconds(30000);

            auto reader = metrics_sdk::PeriodicExportingMetricReaderFactory::Create(
                std::move(exporter), reader_opts);

            auto provider = metrics_sdk::MeterProviderFactory::Create(
                metrics_sdk::ViewRegistryFactory::Create(), build_resource());

            auto* sdk_provider = static_cast<metrics_sdk::MeterProvider*>(provider.get());
            sdk_provider->AddMetricReader(std::move(reader));

            metrics_api::Provider::SetMeterProvider(
                opentelemetry::nostd::shared_ptr<metrics_api::MeterProvider>(provider.release()));
            metrics_initialized_ = true;

            LOG_INFO("OpenTelemetry metrics initialized (endpoint={}, interval={}s)",
                     otlp_config->endpoint, obs.metrics.export_interval_s);
        }
    }

    // Tracing initialization
    if (obs.tracing.enabled) {
        if (!otlp_config.has_value()) {
            LOG_WARN("Tracing enabled but infrastructure.otlp not configured — tracing disabled");
        } else {
            otlp::OtlpGrpcExporterOptions exporter_opts;
            exporter_opts.endpoint = otlp_config->endpoint;
            exporter_opts.use_ssl_credentials = !otlp_config->insecure;

            auto exporter = otlp::OtlpGrpcExporterFactory::Create(exporter_opts);

            trace_sdk::BatchSpanProcessorOptions processor_opts;
            processor_opts.max_queue_size = 2048;
            processor_opts.schedule_delay_millis =
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::seconds(obs.tracing.export_interval_s));
            processor_opts.max_export_batch_size = 512;

            auto processor =
                trace_sdk::BatchSpanProcessorFactory::Create(std::move(exporter), processor_opts);

            auto provider =
                trace_sdk::TracerProviderFactory::Create(std::move(processor), build_resource());

            trace_api::Provider::SetTracerProvider(
                opentelemetry::nostd::shared_ptr<trace_api::TracerProvider>(provider.release()));
            tracing_initialized_ = true;

            LOG_INFO("OpenTelemetry tracing initialized (endpoint={}, interval={}s)",
                     otlp_config->endpoint, obs.tracing.export_interval_s);
        }
    }

    if (!obs.metrics.enabled && !obs.tracing.enabled) {
        LOG_INFO("OpenTelemetry disabled (metrics={}, tracing={})", obs.metrics.enabled,
                 obs.tracing.enabled);
    }
}

void Telemetry::shutdown() {
    if (metrics_initialized_) {
        auto provider = metrics_api::Provider::GetMeterProvider();
        if (provider) {
            auto* sdk_provider = static_cast<metrics_sdk::MeterProvider*>(provider.get());
            sdk_provider->ForceFlush();
            sdk_provider->Shutdown();
        }
        // Reset to no-op provider
        metrics_api::Provider::SetMeterProvider(
            opentelemetry::nostd::shared_ptr<metrics_api::MeterProvider>(
                new metrics_api::NoopMeterProvider()));
        metrics_initialized_ = false;
        LOG_INFO("OpenTelemetry metrics shut down");
    }

    if (tracing_initialized_) {
        auto provider = trace_api::Provider::GetTracerProvider();
        if (provider) {
            auto* sdk_provider = static_cast<trace_sdk::TracerProvider*>(provider.get());
            sdk_provider->ForceFlush();
            sdk_provider->Shutdown();
        }
        // Reset to no-op provider
        trace_api::Provider::SetTracerProvider(
            opentelemetry::nostd::shared_ptr<trace_api::TracerProvider>(
                new trace_api::NoopTracerProvider()));
        tracing_initialized_ = false;
        LOG_INFO("OpenTelemetry tracing shut down");
    }
}

bool Telemetry::metrics_enabled() {
    return metrics_initialized_;
}

bool Telemetry::tracing_enabled() {
    return tracing_initialized_;
}

} // namespace tracker
