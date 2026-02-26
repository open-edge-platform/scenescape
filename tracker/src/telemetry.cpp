// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "telemetry.hpp"

#include "logger.hpp"
#include "metrics.hpp"

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
#include <opentelemetry/sdk/metrics/view/instrument_selector_factory.h>
#include <opentelemetry/sdk/metrics/view/meter_selector_factory.h>
#include <opentelemetry/sdk/metrics/view/view_factory.h>
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

void Telemetry::init(const ServiceConfig& config,
                     std::unique_ptr<opentelemetry::sdk::metrics::PushMetricExporter> exporter) {
    // Guard against double initialization — init() must only be called once from main()
    if (metrics_initialized_ || tracing_initialized_) {
        throw std::runtime_error("Telemetry::init() called more than once");
    }

    const auto& obs = config.observability;
    const auto& otlp_config = config.infrastructure.otlp;

    // Metrics initialization
    if (obs.metrics.enabled) {
        // When a custom exporter is injected (testing), use it directly.
        // Otherwise, require OTLP config and create the gRPC exporter.
        if (!exporter && !otlp_config.has_value()) {
            LOG_WARN("Metrics enabled but infrastructure.otlp not configured — metrics disabled");
        } else {
            if (!exporter) {
                otlp::OtlpGrpcMetricExporterOptions exporter_opts;
                exporter_opts.endpoint = otlp_config->endpoint;
                exporter_opts.use_ssl_credentials = !otlp_config->insecure;
                exporter = otlp::OtlpGrpcMetricExporterFactory::Create(exporter_opts);
            }

            metrics_sdk::PeriodicExportingMetricReaderOptions reader_opts;
            reader_opts.export_interval_millis =
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::seconds(obs.metrics.export_interval_s));
            // Timeout must be < interval; OTel SDK silently falls back to
            // defaults (60 s interval) when this constraint is violated.
            auto interval_ms = reader_opts.export_interval_millis.count();
            reader_opts.export_timeout_millis =
                std::chrono::milliseconds(std::min(30000L, interval_ms * 4 / 5));

            auto reader = metrics_sdk::PeriodicExportingMetricReaderFactory::Create(
                std::move(exporter), reader_opts);

            auto provider = metrics_sdk::MeterProviderFactory::Create(
                metrics_sdk::ViewRegistryFactory::Create(), build_resource());

            auto* sdk_provider = dynamic_cast<metrics_sdk::MeterProvider*>(provider.get());
            if (sdk_provider) {
                // Register a View with fine-grained latency buckets for the
                // mqtt.latency histogram.  Default OTel SDK buckets are too
                // coarse (25→50→75 ms gap) for 30 ms / 50 ms SLI targets.
                auto latency_config = std::make_shared<metrics_sdk::HistogramAggregationConfig>();
                latency_config->boundaries_ = {0,  1,  2,   5,   10,  15,  20,  25,   30,   35,  40,
                                               50, 75, 100, 150, 200, 300, 500, 1000, 2500, 5000};
                auto latency_selector = metrics_sdk::InstrumentSelectorFactory::Create(
                    metrics_sdk::InstrumentType::kHistogram, kMetricMqttLatency, "ms");
                auto meter_selector = metrics_sdk::MeterSelectorFactory::Create(kMeterName, "", "");
                auto latency_view = metrics_sdk::ViewFactory::Create(
                    kMetricMqttLatency, "", "ms", metrics_sdk::AggregationType::kHistogram,
                    latency_config);
                sdk_provider->AddView(std::move(latency_selector), std::move(meter_selector),
                                      std::move(latency_view));

                // Register the same fine-grained buckets for per-stage histograms
                const char* stage_metrics[] = {kMetricStageParse, kMetricStageBuffer,
                                               kMetricStageQueue, kMetricStageTrack,
                                               kMetricStagePublish};
                for (const auto* metric_name : stage_metrics) {
                    auto stage_config = std::make_shared<metrics_sdk::HistogramAggregationConfig>();
                    stage_config->boundaries_ = latency_config->boundaries_;
                    auto stage_selector = metrics_sdk::InstrumentSelectorFactory::Create(
                        metrics_sdk::InstrumentType::kHistogram, metric_name, "ms");
                    auto stage_meter_selector =
                        metrics_sdk::MeterSelectorFactory::Create(kMeterName, "", "");
                    auto stage_view = metrics_sdk::ViewFactory::Create(
                        metric_name, "", "ms", metrics_sdk::AggregationType::kHistogram,
                        stage_config);
                    sdk_provider->AddView(std::move(stage_selector),
                                          std::move(stage_meter_selector), std::move(stage_view));
                }

                sdk_provider->AddMetricReader(std::move(reader));
            }

            metrics_api::Provider::SetMeterProvider(
                opentelemetry::nostd::shared_ptr<metrics_api::MeterProvider>(provider.release()));
            metrics_initialized_ = true;

            if (otlp_config.has_value()) {
                LOG_INFO("OpenTelemetry metrics initialized (endpoint={}, interval={}s)",
                         otlp_config->endpoint, obs.metrics.export_interval_s);
            } else {
                LOG_INFO("OpenTelemetry metrics initialized (custom exporter, interval={}s)",
                         obs.metrics.export_interval_s);
            }
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
            auto* sdk_provider = dynamic_cast<metrics_sdk::MeterProvider*>(provider.get());
            if (sdk_provider) {
                sdk_provider->ForceFlush();
                sdk_provider->Shutdown();
            }
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
            auto* sdk_provider = dynamic_cast<trace_sdk::TracerProvider*>(provider.get());
            if (sdk_provider) {
                sdk_provider->ForceFlush();
                sdk_provider->Shutdown();
            }
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
