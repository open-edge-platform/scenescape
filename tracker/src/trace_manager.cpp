#include "trace_manager.h"
#include "logger.h"
#include <chrono>
#include <quill/LogMacros.h>

#include <opentelemetry/exporters/otlp/otlp_http_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_http_exporter_options.h>
#include <opentelemetry/sdk/resource/resource.h>
#include <opentelemetry/sdk/resource/semantic_conventions.h>
#include <opentelemetry/sdk/trace/batch_span_processor_factory.h>
#include <opentelemetry/sdk/trace/batch_span_processor_options.h>
#include <opentelemetry/sdk/trace/processor.h>
#include <opentelemetry/sdk/trace/tracer_provider.h>
#include <opentelemetry/sdk/trace/tracer_provider_factory.h>
#include <opentelemetry/trace/provider.h>

namespace sdk_trace = opentelemetry::sdk::trace;
namespace trace_api = opentelemetry::trace;
namespace otlp = opentelemetry::exporter::otlp;
namespace resource = opentelemetry::sdk::resource;

TraceManager::TraceManager(const TracingConfig& config)
    : enabled_(config.enabled), otlp_endpoint_(config.otlp_endpoint),
      service_name_(config.service_name) {
    if (enabled_) {
        LOG_DEBUG(logger::get_logger(), "Initializing OpenTelemetry Tracing...");
        initializeOtelProvider();
        initializeTracer();
        LOG_INFO(logger::get_logger(), "OpenTelemetry Tracing initialized successfully");
    } else {
        LOG_INFO(logger::get_logger(), "OpenTelemetry Tracing disabled by configuration");
    }
}

TraceManager::~TraceManager() {
    shutdown();
}

TraceManager& TraceManager::getInstance(const TracingConfig& config) {
    static TraceManager instance(config);
    return instance;
}

bool TraceManager::isEnabled() const {
    return enabled_;
}

std::shared_ptr<trace_api::Tracer> TraceManager::getTracer() {
    return tracer_;
}

void TraceManager::shutdown() {
    if (enabled_ && tracer_provider_) {
        // Cast to SDK provider to call Shutdown
        auto sdk_provider = std::static_pointer_cast<sdk_trace::TracerProvider>(tracer_provider_);
        if (sdk_provider) {
            sdk_provider->Shutdown();
            LOG_DEBUG(logger::get_logger(), "OpenTelemetry Tracing shutdown complete");
        }
    }
}

void TraceManager::initializeOtelProvider() {
    if (otlp_endpoint_.empty()) {
        LOG_ERROR(logger::get_logger(), "OTLP endpoint not configured. Cannot initialize tracing.");
        return;
    }

    LOG_INFO(logger::get_logger(), "Configuring OTLP HTTP trace exporter with endpoint: {}",
             otlp_endpoint_);

    // Configure OTLP HTTP exporter options
    otlp::OtlpHttpExporterOptions otlp_options;
    otlp_options.url = otlp_endpoint_ + "/v1/traces";
    otlp_options.timeout = std::chrono::seconds(10);

    // Create OTLP exporter
    auto otlp_exporter = otlp::OtlpHttpExporterFactory::Create(otlp_options);

    // Configure batch span processor options
    sdk_trace::BatchSpanProcessorOptions processor_options;
    processor_options.max_queue_size = 2048;
    processor_options.schedule_delay_millis = std::chrono::milliseconds(1000);
    processor_options.max_export_batch_size = 512;

    // Create batch span processor
    auto processor =
        sdk_trace::BatchSpanProcessorFactory::Create(std::move(otlp_exporter), processor_options);

    // Create resource with service name
    auto resource_attributes =
        resource::ResourceAttributes{{resource::SemanticConventions::kServiceName, service_name_},
                                     {resource::SemanticConventions::kServiceVersion, "1.0.0"}};
    auto resource = resource::Resource::Create(resource_attributes);

    // Create tracer provider with processor and resource
    auto provider = sdk_trace::TracerProviderFactory::Create(std::move(processor), resource);
    tracer_provider_ = std::shared_ptr<opentelemetry::trace::TracerProvider>(provider.release());

    // Set the global tracer provider
    trace_api::Provider::SetTracerProvider(tracer_provider_);

    LOG_INFO(logger::get_logger(), "OpenTelemetry tracer provider initialized with OTLP endpoint");
}

void TraceManager::initializeTracer() {
    // Get a tracer from the provider
    auto tracer_nostd =
        trace_api::Provider::GetTracerProvider()->GetTracer(service_name_, // Tracer name/scope
                                                            "1.0.0"        // Version
        );

    // Convert nostd::shared_ptr to std::shared_ptr
    tracer_ = std::shared_ptr<trace_api::Tracer>(tracer_nostd.get(),
                                                 [](auto*) {}); // No-op deleter since nostd owns it

    if (!tracer_) {
        throw std::runtime_error("Failed to create tracer");
    }

    LOG_DEBUG(logger::get_logger(), "Created tracer for service: {}", service_name_);
}
