#pragma once

#include "config.h"
#include <memory>
#include <string>

#include <opentelemetry/trace/tracer.h>
#include <opentelemetry/trace/tracer_provider.h>

namespace trace_api = opentelemetry::trace;

/**
 * Trace Manager for OpenTelemetry integration
 * Handles initialization of OTEL tracer provider and management of distributed tracing
 */
class TraceManager {
public:
    /**
     * Constructor that initializes the tracing system
     * @param config Tracing configuration from the application config
     */
    explicit TraceManager(const TracingConfig& config);

    /**
     * Destructor that cleans up the tracing system
     */
    ~TraceManager();

    /**
     * Get the singleton instance of trace manager
     * @param config Configuration for tracing (only used on first call)
     * @return Reference to the trace manager instance
     */
    static TraceManager& getInstance(const TracingConfig& config = {});

    /**
     * Check if tracing is enabled
     * @return true if tracing is enabled, false otherwise
     */
    bool isEnabled() const;

    /**
     * Get the tracer instance for creating spans
     * @return Shared pointer to the tracer
     */
    std::shared_ptr<trace_api::Tracer> getTracer();

    /**
     * Shutdown the tracing system
     */
    void shutdown();

private:
    bool enabled_;
    std::string otlp_endpoint_;
    std::string service_name_;

    std::shared_ptr<trace_api::TracerProvider> tracer_provider_;
    std::shared_ptr<trace_api::Tracer> tracer_;

    /**
     * Initialize the OpenTelemetry tracer provider
     */
    void initializeOtelProvider();

    /**
     * Initialize the tracer
     */
    void initializeTracer();
};
