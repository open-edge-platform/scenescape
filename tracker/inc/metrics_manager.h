#pragma once

#include "config.h"
#include <memory>
#include <string>

#include <opentelemetry/metrics/meter.h>
#include <opentelemetry/metrics/sync_instruments.h>
#include <opentelemetry/nostd/unique_ptr.h>

// Forward declarations for OpenTelemetry types
namespace opentelemetry {
namespace metrics {
class MeterProvider;
}
} // namespace opentelemetry

/**
 * Metrics Manager for OpenTelemetry integration
 * Handles initialization of OTEL meter provider and management of metrics
 */
class MetricsManager {
public:
    /**
     * Constructor that initializes the metrics system
     * @param config Metrics configuration from the application config
     */
    explicit MetricsManager(const MetricsConfig& config);

    /**
     * Destructor that cleans up the metrics system
     */
    ~MetricsManager();

    /**
     * Get the singleton instance of metrics manager
     * @param config Configuration for metrics (only used on first call)
     * @return Reference to the metrics manager instance
     */
    static MetricsManager& getInstance(const MetricsConfig& config = {});

    /**
     * Check if metrics collection is enabled
     * @return true if metrics are enabled, false otherwise
     */
    bool isEnabled() const;

    /**
     * Increment the MQTT messages received counter
     * @param count Number of messages to add to the counter (default: 1)
     */
    void incrementMqttMessagesReceived(uint64_t count = 1);

    /**
     * Increment Controller-compatible MQTT messages counter with labels
     * @param camera Camera ID label
     * @param topic MQTT topic label
     * @param count Number of messages to add (default: 1)
     */
    void incrementControllerMqttMessages(const std::string& camera,
                                         const std::string& topic,
                                         uint64_t count = 1);

    /**
     * Record MQTT handler processing duration
     * @param duration_ms Duration in milliseconds
     * @param camera Camera ID for metric attribute
     */
    void recordMqttHandlerDuration(double duration_ms, const std::string& camera,
                                   const std::string& topic);

    /**
     * Record tracking duration metric.
     * Reuses existing histogram for either per-detection or per-batch timing.
     * When camera is provided, records with camera attribute for per-camera series.
     * @param duration_ms Duration in milliseconds
     * @param camera Optional camera ID label (empty for unlabeled aggregate)
     */
    void recordTrackingDuration(double duration_ms, const std::string& camera = "");

    /**
     * Record tracking duration with category label (Controller-compatible)
     * @param duration_ms Duration in milliseconds
     * @param category Category label (e.g., "person")
     */
    void recordTrackingDurationByCategory(double duration_ms, const std::string& category);

    /**
     * Increment dropped messages counter
     * @param reason Reason for dropping ("fell_behind" or "tracker_busy")
     */
    void incrementDropped(const std::string& reason);
    /**
     * Record objects per MQTT message (Controller-compatible)
     * @param count Number of objects in the message
     * @param camera Camera ID label
     * @param category Category label
     * @param scene Scene identifier label
     */
    void recordObjectsPerMessage(int64_t count,
                                 const std::string& camera,
                                 const std::string& category,
                                 const std::string& scene);

    /**
     * Record active tracks gauge
     * @param reliable_count Number of reliable tracks
     * @param total_count Total number of tracks (reliable + unreliable)
     */
    void recordActiveTracks(int64_t reliable_count, int64_t total_count);

    /**
     * Shutdown the metrics system
     */
    void shutdown();

private:
    bool enabled_;
    std::string otlp_endpoint_;
    int export_interval_seconds_;
    std::string service_name_;

    std::shared_ptr<opentelemetry::metrics::MeterProvider> meter_provider_;
    std::shared_ptr<opentelemetry::metrics::Meter> meter_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Counter<uint64_t>>
        mqtt_messages_counter_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Counter<uint64_t>>
        controller_mqtt_messages_counter_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Histogram<double>>
        mqtt_handler_duration_histogram_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Histogram<double>>
        tracking_duration_histogram_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Histogram<double>>
        objects_per_message_histogram_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::Counter<uint64_t>>
        dropped_messages_counter_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::UpDownCounter<int64_t>>
        reliable_tracks_gauge_;
    opentelemetry::nostd::unique_ptr<opentelemetry::metrics::UpDownCounter<int64_t>>
        total_tracks_gauge_;
    
    // Track previous values for computing deltas
    int64_t last_reliable_tracks_ = 0;
    int64_t last_total_tracks_ = 0;

    /**
     * Initialize the OpenTelemetry metrics provider
     */
    void initializeOtelProvider();

    /**
     * Initialize the meters and metrics
     */
    void initializeMetrics();
};