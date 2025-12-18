#include "metrics_manager.h"
#include "logger.h"
#include <chrono>
#include <quill/LogMacros.h>

#include <opentelemetry/exporters/otlp/otlp_http_metric_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_http_metric_exporter_options.h>
#include <opentelemetry/metrics/meter.h>
#include <opentelemetry/metrics/provider.h>
#include <opentelemetry/metrics/sync_instruments.h>
#include <opentelemetry/sdk/metrics/export/periodic_exporting_metric_reader_factory.h>
#include <opentelemetry/sdk/metrics/export/periodic_exporting_metric_reader_options.h>
#include <opentelemetry/sdk/metrics/meter_context_factory.h>
#include <opentelemetry/sdk/metrics/meter_provider.h>
#include <opentelemetry/sdk/metrics/meter_provider_factory.h>
#include <opentelemetry/sdk/resource/resource.h>
#include <opentelemetry/sdk/resource/semantic_conventions.h>

namespace sdk_metrics = opentelemetry::sdk::metrics;
namespace metrics_api = opentelemetry::metrics;
namespace otlp = opentelemetry::exporter::otlp;

MetricsManager::MetricsManager(const MetricsConfig& config)
    : enabled_(config.enabled), otlp_endpoint_(config.otlp_endpoint),
      export_interval_seconds_(config.export_interval_seconds), service_name_(config.service_name) {
    if (enabled_) {
        LOG_DEBUG(logger::get_logger(), "Initializing OpenTelemetry Metrics...");
        initializeOtelProvider();
        initializeMetrics();
        LOG_INFO(logger::get_logger(), "OpenTelemetry Metrics initialized successfully");
    } else {
        LOG_INFO(logger::get_logger(), "OpenTelemetry Metrics disabled by configuration");
    }
}

MetricsManager::~MetricsManager() {
    shutdown();
}

MetricsManager& MetricsManager::getInstance(const MetricsConfig& config) {
    static MetricsManager instance(config);
    return instance;
}

bool MetricsManager::isEnabled() const {
    return enabled_;
}

void MetricsManager::incrementMqttMessagesReceived(uint64_t count) {
    if (!enabled_ || !mqtt_messages_counter_) {
        return;
    }

    mqtt_messages_counter_->Add(count);
}

void MetricsManager::shutdown() {
    if (enabled_) {
        LOG_DEBUG(logger::get_logger(), "OpenTelemetry Metrics shutdown complete");
    }
}

void MetricsManager::recordMqttHandlerDuration(double duration_ms, const std::string& camera,
                                               const std::string& topic) {
    if (!enabled_ || !mqtt_handler_duration_histogram_) {
        return;
    }
    mqtt_handler_duration_histogram_->Record(
        duration_ms, {{"camera", camera}, {"topic", topic}},
        opentelemetry::context::Context{});
}

void MetricsManager::recordTrackingDuration(double duration_ms, const std::string& camera) {
    if (!enabled_ || !tracking_duration_histogram_) {
        return;
    }
    if (!camera.empty()) {
        tracking_duration_histogram_->Record(duration_ms, {{"camera", camera}},
                                             opentelemetry::context::Context{});
    } else {
        tracking_duration_histogram_->Record(duration_ms, {}, opentelemetry::context::Context{});
    }
}

void MetricsManager::recordTrackingDurationByCategory(double duration_ms,
                                                      const std::string& category) {
    if (!enabled_ || !tracking_duration_histogram_) {
        return;
    }
    tracking_duration_histogram_->Record(duration_ms, {{"category", category}},
                                         opentelemetry::context::Context{});
}

void MetricsManager::incrementDropped(const std::string& reason) {
    if (!enabled_ || !dropped_messages_counter_) {
        return;
    }
    dropped_messages_counter_->Add(1, {{"reason", reason}}, opentelemetry::context::Context{});
}

void MetricsManager::incrementControllerMqttMessages(const std::string& camera,
                                                     const std::string& topic, uint64_t count) {
    if (!enabled_ || !controller_mqtt_messages_counter_) {
        return;
    }
    controller_mqtt_messages_counter_->Add(count, {{"camera", camera}, {"topic", topic}},
                                           opentelemetry::context::Context{});
}

void MetricsManager::recordObjectsPerMessage(int64_t count,
                                             const std::string& camera,
                                             const std::string& category,
                                             const std::string& scene) {
    if (!enabled_ || !objects_per_message_histogram_) {
        return;
    }
    // Histogram expects double values; use count as double
    objects_per_message_histogram_->Record(static_cast<double>(count),
                                           {{"camera", camera},
                                            {"category", category},
                                            {"scene", scene}},
                                           opentelemetry::context::Context{});
}

void MetricsManager::recordActiveTracks(int64_t reliable_count, int64_t total_count) {
    if (!enabled_) {
        return;
    }
    
    if (reliable_tracks_gauge_) {
        // UpDownCounter requires deltas, so compute the difference from last value
        int64_t reliable_delta = reliable_count - last_reliable_tracks_;
        reliable_tracks_gauge_->Add(reliable_delta, {}, opentelemetry::context::Context{});
        last_reliable_tracks_ = reliable_count;
    }
    
    if (total_tracks_gauge_) {
        int64_t total_delta = total_count - last_total_tracks_;
        total_tracks_gauge_->Add(total_delta, {}, opentelemetry::context::Context{});
        last_total_tracks_ = total_count;
    }
}

void MetricsManager::initializeOtelProvider() {
    if (otlp_endpoint_.empty()) {
        LOG_ERROR(logger::get_logger(), "OTLP endpoint not configured. Cannot initialize metrics.");
        return;
    }

    LOG_INFO(logger::get_logger(), "Configuring OTLP HTTP exporter with endpoint: {}",
             otlp_endpoint_);

    // Configure OTLP HTTP exporter options
    otlp::OtlpHttpMetricExporterOptions otlp_options;
    otlp_options.url = otlp_endpoint_ + "/v1/metrics";
    otlp_options.timeout = std::chrono::seconds(10);

    // Create OTLP exporter
    auto otlp_exporter = otlp::OtlpHttpMetricExporterFactory::Create(otlp_options);

    // Configure periodic export options
    sdk_metrics::PeriodicExportingMetricReaderOptions reader_options;
    reader_options.export_interval_millis =
        std::chrono::milliseconds(export_interval_seconds_ * 1000);
    reader_options.export_timeout_millis = std::chrono::milliseconds(5000);

    // Create periodic exporting metric reader
    auto otlp_reader = sdk_metrics::PeriodicExportingMetricReaderFactory::Create(
        std::move(otlp_exporter), reader_options);

    // Create resource with service name
    auto resource_attributes = opentelemetry::sdk::resource::ResourceAttributes{
        {opentelemetry::sdk::resource::SemanticConventions::kServiceName, service_name_},
        {opentelemetry::sdk::resource::SemanticConventions::kServiceVersion, "1.0.0"}};
    auto resource = opentelemetry::sdk::resource::Resource::Create(resource_attributes);

    // Create meter context with resource
    // Need to create an empty ViewRegistry, not pass nullptr
    auto views = std::unique_ptr<sdk_metrics::ViewRegistry>(new sdk_metrics::ViewRegistry());
    auto context = sdk_metrics::MeterContextFactory::Create(std::move(views), resource);
    context->AddMetricReader(std::move(otlp_reader));

    // Create meter provider with the context
    auto provider = sdk_metrics::MeterProviderFactory::Create(std::move(context));
    meter_provider_ = std::shared_ptr<opentelemetry::metrics::MeterProvider>(provider.release());

    // Set the global meter provider
    metrics_api::Provider::SetMeterProvider(meter_provider_);

    LOG_INFO(logger::get_logger(), "OpenTelemetry metrics provider initialized with OTLP endpoint");
}

void MetricsManager::initializeMetrics() {
    // Get a meter from the provider
    auto meter_nostd =
        metrics_api::Provider::GetMeterProvider()->GetMeter("tracker_service", // Meter name/scope
                                                            "1.0.0"            // Version
        );

    // Convert nostd::shared_ptr to std::shared_ptr
    meter_ = std::shared_ptr<opentelemetry::metrics::Meter>(
        meter_nostd.get(), [](auto*) {}); // No-op deleter since nostd owns it

    // Create the MQTT messages counter
    mqtt_messages_counter_ = meter_->CreateUInt64Counter(
        "mqtt_messages_received_total",
        "Total number of MQTT messages received by the tracker service", "messages");

    if (!mqtt_messages_counter_) {
        throw std::runtime_error("Failed to create MQTT messages counter metric");
    }

    LOG_DEBUG(logger::get_logger(), "Created MQTT messages received counter metric");

    // Create MQTT handler duration histogram
    mqtt_handler_duration_histogram_ = meter_->CreateDoubleHistogram(
        "scenescape_controller_mqtt_handler_duration", "MQTT handler processing time", "ms");

    if (!mqtt_handler_duration_histogram_) {
        throw std::runtime_error("Failed to create MQTT handler duration histogram");
    }

    LOG_DEBUG(logger::get_logger(), "Created MQTT handler duration histogram metric");

    // Create tracking duration histogram (matching Controller metric name)
    tracking_duration_histogram_ = meter_->CreateDoubleHistogram(
        "scenescape_controller_tracking_duration", "Tracking computation time", "ms");

    if (!tracking_duration_histogram_) {
        throw std::runtime_error("Failed to create tracking duration histogram");
    }

    LOG_DEBUG(logger::get_logger(), "Created tracking duration histogram metric");

    // Create dropped messages counter (matching Controller metric name)
    dropped_messages_counter_ = meter_->CreateUInt64Counter(
        "scenescape_controller_mqtt_messages_dropped", "MQTT messages dropped", "messages");

    if (!dropped_messages_counter_) {
        throw std::runtime_error("Failed to create dropped messages counter");
    }

    LOG_DEBUG(logger::get_logger(), "Created dropped messages counter metric");

    // Create Controller-compatible MQTT messages processed counter
    controller_mqtt_messages_counter_ = meter_->CreateUInt64Counter(
        "scenescape_controller_mqtt_messages", "MQTT messages processed", "messages");

    if (!controller_mqtt_messages_counter_) {
        throw std::runtime_error("Failed to create Controller MQTT messages counter metric");
    }

    LOG_DEBUG(logger::get_logger(), "Created Controller MQTT messages counter metric");

    // Create objects per message histogram (Controller-compatible)
    objects_per_message_histogram_ = meter_->CreateDoubleHistogram(
        "scenescape_controller_objects_in_mqtt_message", "Object count per MQTT message", "1");

    if (!objects_per_message_histogram_) {
        throw std::runtime_error("Failed to create objects per message histogram");
    }

    LOG_DEBUG(logger::get_logger(), "Created objects per message histogram metric");

    // Create reliable tracks gauge
    reliable_tracks_gauge_ = meter_->CreateInt64UpDownCounter(
        "scenescape_tracker_reliable_tracks", "Number of reliable tracks", "tracks");

    if (!reliable_tracks_gauge_) {
        throw std::runtime_error("Failed to create reliable tracks gauge");
    }

    LOG_DEBUG(logger::get_logger(), "Created reliable tracks gauge metric");

    // Create total tracks gauge
    total_tracks_gauge_ = meter_->CreateInt64UpDownCounter(
        "scenescape_tracker_total_tracks", "Total number of active tracks", "tracks");

    if (!total_tracks_gauge_) {
        throw std::runtime_error("Failed to create total tracks gauge");
    }

    LOG_DEBUG(logger::get_logger(), "Created total tracks gauge metric");
}